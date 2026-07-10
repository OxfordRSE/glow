#!/usr/bin/env python3
"""
Simplified Glow AWS deployment script.

This script handles:
- AMI building using local Packer
- One-pass Terraform apply for infrastructure
- SSM-based in-place updates for subsequent releases
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
AWS_DEPLOY_DIR = REPO_ROOT / "deploy" / "aws"
TERRAFORM_DIR = AWS_DEPLOY_DIR / "terraform"
PACKER_DIR = AWS_DEPLOY_DIR / "runner"


class DeployError(RuntimeError):
    """Raised when deployment cannot continue."""


@dataclass
class Config:
    domain_name: str
    certificate_arn: str
    git_repo_url: str
    git_ref: str
    git_commit: str
    aws_region: str
    app_name: str
    runner_instance_type: str
    runner_root_volume_size_gb: int
    dry_run: bool
    force_rebuild_ami: bool


def require_command(command: str) -> None:
    """Check that a required command is available."""
    if not subprocess.run(["which", command], capture_output=True).returncode == 0:
        raise DeployError(f"required command not found: {command}")


def run_command(args: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if check and result.returncode != 0:
        raise DeployError(f"command failed: {' '.join(args)}\n{result.stderr}")
    return result


def write_inline(message: str) -> None:
    """Write a message that overwrites the current line."""
    sys.stderr.write(f"\r\033[K{message}")
    sys.stderr.flush()


def write_line(message: str) -> None:
    """Write a message on a new line."""
    sys.stderr.write(f"\r\033[K{message}\n")
    sys.stderr.flush()


def resolve_git_commit(repo_url: str, ref: str) -> str:
    """Resolve a git ref to a commit SHA."""
    if ref and len(ref) == 40 and all(c in "0123456789abcdef" for c in ref):
        return ref
    
    result = run_command([
        "git", "ls-remote", repo_url, ref, f"refs/tags/{ref}", f"refs/heads/{ref}"
    ])
    
    for line in result.stdout.splitlines():
        if line.strip():
            sha, _ = line.split("\t", 1)
            return sha
    
    raise DeployError(f"could not resolve git ref: {ref}")


def find_ami_in_account(region: str, git_commit: str) -> str | None:
    """Find an existing AMI in the AWS account for the given commit."""
    import boto3
    
    ec2 = boto3.client("ec2", region_name=region)
    response = ec2.describe_images(
        Owners=["self"],
        Filters=[
            {"Name": "tag:Component", "Values": ["glow-runner"]},
            {"Name": "tag:GitCommit", "Values": [git_commit]},
        ],
    )
    
    images = sorted(response.get("Images", []), key=lambda i: i.get("CreationDate", ""), reverse=True)
    if images:
        return images[0]["ImageId"]
    return None


def build_ami_with_packer(region: str, git_commit: str) -> str:
    """Build the runner AMI using Packer."""
    write_line("[deploy] Building runner AMI with Packer")
    
    packer_vars = [
        f"-var", f"aws_region={region}",
        f"-var", f"git_commit={git_commit}",
    ]
    
    run_command(["packer", "init", "packer.pkr.hcl"], cwd=PACKER_DIR)
    
    result = run_command(
        ["packer", "build"] + packer_vars + ["packer.pkr.hcl"],
        cwd=PACKER_DIR,
    )
    
    # Extract AMI ID from packer output
    for line in result.stdout.splitlines():
        if "AMI:" in line and "ami-" in line:
            ami_id = line.split("ami-")[1].split()[0]
            return f"ami-{ami_id}"
    
    raise DeployError("could not extract AMI ID from packer output")


def ensure_state_bucket(region: str, domain_name: str) -> str:
    """Ensure the Terraform state bucket exists."""
    import boto3
    
    sts = boto3.client("sts", region_name=region)
    account_id = sts.get_caller_identity()["Account"]
    
    bucket_name = f"{domain_name.replace('.', '-')}-glow-deploy-state-{account_id}"[:63].rstrip("-")
    
    s3 = boto3.client("s3", region_name=region)
    
    try:
        s3.head_bucket(Bucket=bucket_name)
        write_line(f"[deploy] State bucket exists: {bucket_name}")
        return bucket_name
    except Exception:
        pass
    
    write_line(f"[deploy] Creating state bucket: {bucket_name}")
    
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket_name)
    else:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    
    s3.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={"Status": "Enabled"},
    )
    
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    
    return bucket_name


def terraform_init(bucket: str, region: str) -> None:
    """Initialize Terraform."""
    run_command([
        "terraform", "init",
        f"-backend-config=bucket={bucket}",
        f"-backend-config=key=main.tfstate",
        f"-backend-config=region={region}",
        "-reconfigure",
    ], cwd=TERRAFORM_DIR)


def terraform_apply(config: Config, ami_id: str) -> dict[str, Any]:
    """Apply Terraform configuration."""
    tfvars = {
        "app_name": config.app_name,
        "aws_region": config.aws_region,
        "certificate_arn": config.certificate_arn,
        "domain_name": config.domain_name,
        "git_repo_url": config.git_repo_url,
        "git_checkout_ref": config.git_commit,
        "runner_ami_id": ami_id,
        "runner_instance_type": config.runner_instance_type,
        "runner_root_volume_size_gb": config.runner_root_volume_size_gb,
    }
    
    fd, tfvars_path = tempfile.mkstemp(suffix=".tfvars.json")
    try:
        Path(tfvars_path).write_text(json.dumps(tfvars, indent=2))
        
        if config.dry_run:
            run_command(
                ["terraform", "plan", f"-var-file={tfvars_path}"],
                cwd=TERRAFORM_DIR,
            )
            return {}
        
        run_command(
            ["terraform", "apply", "-auto-approve", f"-var-file={tfvars_path}"],
            cwd=TERRAFORM_DIR,
        )
        
        result = run_command(["terraform", "output", "-json"], cwd=TERRAFORM_DIR)
        raw = json.loads(result.stdout)
        return {name: details["value"] for name, details in raw.items()}
    finally:
        os.close(fd)
        Path(tfvars_path).unlink(missing_ok=True)


def wait_with_spinner(message: str, check_fn, timeout: int = 600) -> None:
    """Wait for a condition with a spinner."""
    spinner = ["|", "/", "-", "\\"]
    idx = 0
    start = time.time()
    
    while True:
        elapsed = int(time.time() - start)
        write_inline(f"[deploy] {message} {spinner[idx % len(spinner)]} ({elapsed}s)")
        
        if check_fn():
            write_line(f"[deploy] {message} ✓")
            return
        
        if elapsed > timeout:
            write_line("")
            raise DeployError(f"timeout waiting for: {message}")
        
        time.sleep(1)
        idx += 1


def wait_for_ssm_online(instance_id: str, region: str) -> None:
    """Wait for SSM to become available on the instance."""
    import boto3
    
    ssm = boto3.client("ssm", region_name=region)
    
    def check():
        response = ssm.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        for item in response.get("InstanceInformationList", []):
            if item.get("PingStatus") == "Online":
                return True
        return False
    
    wait_with_spinner("Waiting for SSM online", check, timeout=300)


def run_ssm_command(instance_id: str, region: str, commands: list[str], comment: str, timeout: int = 1800) -> None:
    """Run a command via SSM and wait for completion."""
    import boto3
    from botocore.exceptions import ClientError
    
    ssm = boto3.client("ssm", region_name=region)
    
    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Comment=comment,
        TimeoutSeconds=timeout,
        Parameters={"commands": commands},
    )
    
    command_id = response["Command"]["CommandId"]
    
    def check():
        try:
            invocation = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "InvocationDoesNotExist":
                return False
            raise
        
        status = invocation.get("Status", "Unknown")
        
        if status == "Success" and int(invocation.get("ResponseCode", 1)) == 0:
            return True
        
        if status in {"Cancelled", "TimedOut", "Failed", "Cancelling"}:
            stderr = invocation.get("StandardErrorContent", "").strip()
            stdout = invocation.get("StandardOutputContent", "").strip()
            details = stderr or stdout or status
            raise DeployError(f"remote command failed: {details}")
        
        return False
    
    wait_with_spinner(comment, check, timeout=timeout)


def rerun_runner_userdata(instance_id: str, region: str) -> None:
    """Rerun the instance userdata script via SSM."""
    run_ssm_command(
        instance_id,
        region,
        [
            "if test -f /var/lib/cloud/instance/user-data.txt; then "
            "sudo bash /var/lib/cloud/instance/user-data.txt; "
            "elif test -f /var/lib/cloud/instance/scripts/part-001; then "
            "sudo bash /var/lib/cloud/instance/scripts/part-001; "
            "else echo 'userdata script not found' >&2; exit 1; fi"
        ],
        "rerun runner userdata",
        timeout=3600,
    )


def verify_alb_routing(alb_dns: str, domain_name: str) -> None:
    """Verify ALB routing works with Host headers."""
    import http.client
    
    write_line("[deploy] Verifying ALB routing")
    
    endpoints = [
        (domain_name, "/en", "Dashboard"),
        (f"api.{domain_name}", "/health", "API"),
        (f"odk.{domain_name}", "/", "ODK"),
    ]
    
    for host, path, name in endpoints:
        conn = http.client.HTTPSConnection(alb_dns, timeout=10)
        try:
            conn.request("GET", path, headers={"Host": host})
            response = conn.getresponse()
            if response.status in (200, 301, 302):
                write_line(f"[deploy]   {name} routing ✓")
            else:
                raise DeployError(f"{name} routing failed: HTTP {response.status}")
        finally:
            conn.close()


def provision(config: Config) -> None:
    """Initial provision: build AMI, apply Terraform, activate stack."""
    write_line(f"[deploy] Provisioning {config.domain_name}")
    write_line(f"[deploy] Git reference: {config.git_ref} ({config.git_commit[:8]})")
    
    bucket = ensure_state_bucket(config.aws_region, config.domain_name)
    
    ami_id = None if config.force_rebuild_ami else find_ami_in_account(config.aws_region, config.git_commit)
    
    if ami_id:
        write_line(f"[deploy] Using existing AMI: {ami_id}")
    else:
        ami_id = build_ami_with_packer(config.aws_region, config.git_commit)
        write_line(f"[deploy] Built AMI: {ami_id}")
    
    terraform_init(bucket, config.aws_region)
    
    write_line("[deploy] Applying Terraform")
    outputs = terraform_apply(config, ami_id)
    
    if config.dry_run:
        write_line("[deploy] Dry-run complete")
        return
    
    instance_id = outputs["runner_instance_id"]
    alb_dns = outputs["alb_dns_name"]
    
    wait_for_ssm_online(instance_id, config.aws_region)
    
    run_ssm_command(
        instance_id,
        config.aws_region,
        ["timeout 1800 bash -c 'until test -f /opt/glow-runner/bootstrap.ready; do sleep 1; done'"],
        "wait for bootstrap",
        timeout=1800,
    )

    rerun_runner_userdata(instance_id, config.aws_region)

    run_ssm_command(
        instance_id,
        config.aws_region,
        ["curl -fsS http://127.0.0.1:8000/health"],
        "verify API health",
    )
    
    run_ssm_command(
        instance_id,
        config.aws_region,
        ["curl -fsS http://127.0.0.1:3000/en"],
        "verify dashboard health",
    )
    
    run_ssm_command(
        instance_id,
        config.aws_region,
        ["curl -fsS http://127.0.0.1:8080/"],
        "verify ODK health",
    )
    
    write_line(f"[deploy] Deployment complete!")
    write_line(f"[deploy] Instance ID: {instance_id}")
    write_line(f"[deploy] ALB DNS: {alb_dns}")
    write_line(f"[deploy] Dashboard: https://{config.domain_name}")
    write_line(f"[deploy] API: https://api.{config.domain_name}")
    write_line(f"[deploy] ODK: https://odk.{config.domain_name}")


def update(config: Config) -> None:
    """Update existing instance via SSM."""
    write_line(f"[deploy] Updating to {config.git_ref} ({config.git_commit[:8]})")
    
    bucket = ensure_state_bucket(config.aws_region, config.domain_name)
    terraform_init(bucket, config.aws_region)
    
    result = run_command(["terraform", "output", "-json"], cwd=TERRAFORM_DIR)
    raw = json.loads(result.stdout)
    outputs = {name: details["value"] for name, details in raw.items()}
    
    instance_id = outputs["runner_instance_id"]
    
    wait_for_ssm_online(instance_id, config.aws_region)
    
    update_command = (
        f"sudo "
        f"GIT_REF={shlex.quote(config.git_commit)} "
        f"DOMAIN_NAME={shlex.quote(config.domain_name)} "
        f"bash /opt/glow/deploy/aws/runtime/update-instance.sh"
    )
    
    run_ssm_command(
        instance_id,
        config.aws_region,
        [update_command],
        f"update to {config.git_ref}",
        timeout=3600,
    )
    
    write_line(f"[deploy] Update complete!")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, dest="domain_name")
    parser.add_argument("--certificate-arn", default="")
    parser.add_argument("--git-ref", default="")
    parser.add_argument("--git-repo-url", default="https://github.com/OxfordRSE/glow.git")
    parser.add_argument("--aws-region", default=os.environ.get("AWS_REGION", "eu-west-2"))
    parser.add_argument("--app-name", default="glow-core")
    parser.add_argument("--runner-instance-type", default="t3.medium")
    parser.add_argument("--runner-root-volume-size-gb", type=int, default=100)
    parser.add_argument("--force-rebuild-ami", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--update", action="store_true", help="Update existing instance instead of provision")
    
    args = parser.parse_args()
    
    try:
        require_command("git")
        require_command("terraform")
        require_command("packer")
        
        git_ref = args.git_ref or "main"
        git_commit = resolve_git_commit(args.git_repo_url, git_ref)
        
        config = Config(
            domain_name=args.domain_name,
            certificate_arn=args.certificate_arn,
            git_repo_url=args.git_repo_url,
            git_ref=git_ref,
            git_commit=git_commit,
            aws_region=args.aws_region,
            app_name=args.app_name,
            runner_instance_type=args.runner_instance_type,
            runner_root_volume_size_gb=args.runner_root_volume_size_gb,
            dry_run=args.dry_run,
            force_rebuild_ami=args.force_rebuild_ami,
        )
        
        if args.update:
            update(config)
        else:
            provision(config)
        
        return 0
    
    except DeployError as exc:
        write_line(f"[deploy] ERROR: {exc}")
        return 1
    except KeyboardInterrupt:
        write_line("\n[deploy] Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

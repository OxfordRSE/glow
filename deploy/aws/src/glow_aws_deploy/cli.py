from __future__ import annotations

import argparse
import os
from typing import Any

import boto3

from .builds import ensure_runner_ami
from .certificates import resolve_issued_certificate
from .common import Console, DeploymentConfig, DeploymentError, render_dns_instructions, require_command, resolve_requested_git_ref, resolve_runner_ami_version, validate_domain_name
from .cutover import perform_cutover
from .terraform import apply_bootstrap, apply_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="deploy.py")
    parser.add_argument("--domain", required=True, dest="domain_name")
    parser.add_argument("--certificate-arn", default="")
    parser.add_argument("--git-ref", default="")
    parser.add_argument("--git-repo-url", default="https://github.com/OxfordRSE/glow.git")
    parser.add_argument("--aws-region", default=os.environ.get("AWS_REGION", "eu-west-2"))
    parser.add_argument("--app-name", default="glow-core")
    parser.add_argument("--runner-instance-type", default="t3.medium")
    parser.add_argument("--runner-root-volume-size-gb", type=int, default=30)
    parser.add_argument("--data-volume-size-gb", type=int, default=100)
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    console = Console(verbose=args.verbose)
    try:
        require_command("git")
        require_command("terraform")
        validate_domain_name(args.domain_name)

        console.step("Resolving deployment git reference")
        resolved_ref = resolve_requested_git_ref(console, args.git_repo_url, args.git_ref)
        console.info(
            f"Deploying {resolved_ref.resolved_ref} at commit {resolved_ref.commit_sha}"
        )

        console.step("Resolving runner AMI version")
        runner_ami_version = resolve_runner_ami_version(args.git_repo_url, resolved_ref.commit_sha)
        console.info(f"Runner AMI version: {runner_ami_version}")

        session = boto3.Session(region_name=args.aws_region)
        sts_client = session.client("sts")
        caller = sts_client.get_caller_identity()
        account_id = caller["Account"]
        console.info(f"Authenticated to AWS account {account_id} in {args.aws_region}")

        acm_client = session.client("acm")
        console.step("Resolving ACM certificate")
        certificate = resolve_issued_certificate(
            console,
            acm_client,
            domain_name=args.domain_name,
            certificate_arn=args.certificate_arn,
            dry_run=args.dry_run,
        )
        console.info(f"Using ACM certificate {certificate['CertificateArn']}")

        config = DeploymentConfig(
            app_name=args.app_name,
            aws_region=args.aws_region,
            domain_name=args.domain_name,
            certificate_arn=str(certificate["CertificateArn"]),
            git_repo_url=args.git_repo_url,
            git_ref=resolved_ref,
            runner_ami_version=runner_ami_version,
            runner_instance_type=args.runner_instance_type,
            runner_root_volume_size_gb=args.runner_root_volume_size_gb,
            data_volume_size_gb=args.data_volume_size_gb,
            dry_run=args.dry_run,
            force_rebuild=args.force_rebuild,
            verbose=args.verbose,
        )

        bucket_name = ensure_state_bucket(console, session, config, account_id)

        console.step("Applying bootstrap Terraform")
        bootstrap = apply_bootstrap(console, config, bucket=bucket_name)

        ec2_client = session.client("ec2")
        codebuild_client = session.client("codebuild")
        elbv2_client = session.client("elbv2")
        ssm_client = session.client("ssm")

        console.step("Ensuring runner AMI exists")
        ensure_runner_ami(
            console,
            config,
            ec2_client=ec2_client,
            codebuild_client=codebuild_client,
            bootstrap_outputs=bootstrap.outputs,
        )

        console.step("Applying main Terraform (HTTPS ALB)")
        main = apply_main(console, config, bucket=bucket_name)
        if config.dry_run:
            console.info("Dry-run complete. No AWS resources were changed after the planning steps.")
            return 0
        outputs = main.outputs

        console.step("Launching new runner and cutting over data volume")
        perform_cutover(
            console,
            config,
            ec2_client=ec2_client,
            elbv2_client=elbv2_client,
            ssm_client=ssm_client,
            outputs=outputs,
        )

        final_certificate_status = describe_certificate_status(acm_client, config.certificate_arn)
        console.step("DNS handoff instructions")
        print(
            render_dns_instructions(
                domain_name=config.domain_name,
                alb_dns_name=str(outputs["alb_dns_name"]),
                certificate_status=final_certificate_status,
            )
        )

        console.info("")
        console.info(f"ALB DNS name: {outputs['alb_dns_name']}")
        console.info(f"Certificate ARN: {config.certificate_arn}")
        console.info(f"Current certificate status: {final_certificate_status}")
        console.info(f"Dashboard URL: https://{config.domain_name}")
        console.info(f"API URL: https://api.{config.domain_name}")
        console.info(f"ODK URL: https://odk.{config.domain_name}")
    except DeploymentError as exc:
        console.error(str(exc))
        return 1
    return 0


def ensure_state_bucket(
    console: Console,
    session: boto3.Session,
    config: DeploymentConfig,
    account_id: str,
) -> str:
    bucket_name = f"{config.backend_bucket_prefix}-{account_id}"[:63].rstrip("-")
    s3_client = session.client("s3")
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        console.info(f"Terraform state bucket already exists: {bucket_name}")
        return bucket_name
    except Exception:
        pass

    console.info(f"Creating Terraform state bucket: {bucket_name}")
    if config.aws_region == "us-east-1":
        s3_client.create_bucket(Bucket=bucket_name)
    else:
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": config.aws_region},
        )
    s3_client.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={"Status": "Enabled"},
    )
    s3_client.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    return bucket_name


def describe_certificate_status(acm_client: Any, certificate_arn: str) -> str:
    response = acm_client.describe_certificate(CertificateArn=certificate_arn)
    return str(response["Certificate"]["Status"])

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .common import AWS_DEPLOY_DIR, Console, DeploymentConfig, TerraformResult, run_command, run_live_command

BOOTSTRAP_DIR = AWS_DEPLOY_DIR / "terraform_bootstrap"
MAIN_DIR = AWS_DEPLOY_DIR / "terraform"


def bootstrap_payload(config: DeploymentConfig) -> dict[str, Any]:
    return {
        "app_name": config.app_name,
        "aws_region": config.aws_region,
    }


def main_payload(config: DeploymentConfig) -> dict[str, Any]:
    return {
        "app_name": config.app_name,
        "aws_region": config.aws_region,
        "certificate_arn": config.certificate_arn,
        "domain_name": config.domain_name,
        "git_repo_url": config.git_repo_url,
        "git_checkout_ref": config.git_ref.commit_sha,
        "runner_ami_version": config.runner_ami_version,
        "runner_instance_type": config.runner_instance_type,
        "runner_root_volume_size_gb": config.runner_root_volume_size_gb,
        "data_volume_size_gb": config.data_volume_size_gb,
    }


def write_tfvars(payload: dict[str, Any]) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="glow-aws-", suffix=".tfvars.json")
    path = Path(raw_path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def terraform_init(console: Console, *, directory: Path, bucket: str, key: str, region: str) -> None:
    run_live_command(
        console,
        [
            "terraform",
            f"-chdir={directory}",
            "init",
            f"-backend-config=bucket={bucket}",
            f"-backend-config=key={key}",
            f"-backend-config=region={region}",
            "-reconfigure",
        ],
        label=f"terraform init ({directory.name})",
    )


def terraform_apply(
    console: Console,
    *,
    directory: Path,
    payload: dict[str, Any],
    dry_run: bool,
) -> TerraformResult:
    tfvars = write_tfvars(payload)
    try:
        if dry_run:
            run_live_command(
                console,
                [
                    "terraform",
                    f"-chdir={directory}",
                    "plan",
                    f"-var-file={tfvars}",
                    "-compact-warnings",
                ],
                label=f"terraform plan ({directory.name})",
            )
            return TerraformResult(outputs={})

        run_live_command(
            console,
            [
                "terraform",
                f"-chdir={directory}",
                "apply",
                "-auto-approve",
                f"-var-file={tfvars}",
                "-compact-warnings",
            ],
            label=f"terraform apply ({directory.name})",
        )
        return TerraformResult(outputs=terraform_outputs(directory))
    finally:
        tfvars.unlink(missing_ok=True)


def terraform_outputs(directory: Path) -> dict[str, Any]:
    completed = run_command(["terraform", f"-chdir={directory}", "output", "-json"])
    raw = json.loads(completed.stdout)
    return {name: details["value"] for name, details in raw.items()}


def apply_bootstrap(console: Console, config: DeploymentConfig, *, bucket: str) -> TerraformResult:
    terraform_init(console, directory=BOOTSTRAP_DIR, bucket=bucket, key="bootstrap.tfstate", region=config.aws_region)
    return terraform_apply(console, directory=BOOTSTRAP_DIR, payload=bootstrap_payload(config), dry_run=config.dry_run)


def apply_main(
    console: Console,
    config: DeploymentConfig,
    *,
    bucket: str,
) -> TerraformResult:
    terraform_init(console, directory=MAIN_DIR, bucket=bucket, key="main.tfstate", region=config.aws_region)
    return terraform_apply(
        console,
        directory=MAIN_DIR,
        payload=main_payload(config),
        dry_run=config.dry_run,
    )

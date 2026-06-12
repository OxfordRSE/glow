from __future__ import annotations

import time
from typing import Any

from .common import Console, DeploymentConfig, DeploymentError


def latest_runner_ami(ec2_client: Any, *, runner_ami_version: str) -> dict[str, Any] | None:
    response = ec2_client.describe_images(
        Owners=["self"],
        Filters=[
            {"Name": "tag:Component", "Values": ["glow-runner"]},
            {"Name": "tag:Version", "Values": [runner_ami_version]},
        ],
    )
    images = sorted(response.get("Images", []), key=lambda item: item.get("CreationDate", ""), reverse=True)
    return images[0] if images else None


def ensure_runner_ami(
    console: Console,
    config: DeploymentConfig,
    *,
    ec2_client: Any,
    codebuild_client: Any,
    bootstrap_outputs: dict[str, Any],
) -> dict[str, Any] | None:
    existing = latest_runner_ami(ec2_client, runner_ami_version=config.runner_ami_version)
    if existing and not config.force_rebuild:
        console.info(
            f"Reusing runner AMI {existing['ImageId']} for version {config.runner_ami_version}"
        )
        return existing

    if config.dry_run:
        console.info(
            f"Dry-run: would build runner AMI version {config.runner_ami_version} from {config.git_ref.commit_sha}"
        )
        return existing

    project_name = str(bootstrap_outputs["runner_codebuild_project_name"])
    console.info(
        f"Starting CodeBuild runner AMI build for version {config.runner_ami_version}"
    )
    response = codebuild_client.start_build(
        projectName=project_name,
        environmentVariablesOverride=[
            {"name": "GIT_REPO_URL", "value": config.git_repo_url, "type": "PLAINTEXT"},
            {"name": "GIT_REF", "value": config.git_ref.commit_sha, "type": "PLAINTEXT"},
            {
                "name": "RUNNER_AMI_VERSION",
                "value": config.runner_ami_version,
                "type": "PLAINTEXT",
            },
        ],
    )
    build_id = response["build"]["id"]
    wait_for_codebuild(console, codebuild_client, build_id)

    for _ in range(60):
        image = latest_runner_ami(ec2_client, runner_ami_version=config.runner_ami_version)
        if image:
            console.info(f"Runner AMI available: {image['ImageId']}")
            return image
        time.sleep(10)
    raise DeploymentError("runner AMI build succeeded but no AMI with the requested version became visible")


def wait_for_codebuild(console: Console, codebuild_client: Any, build_id: str) -> None:
    terminal_states = {"SUCCEEDED", "FAILED", "FAULT", "STOPPED", "TIMED_OUT"}
    previous_status: tuple[str, str] | None = None
    started = time.monotonic()
    while True:
        response = codebuild_client.batch_get_builds(ids=[build_id])
        builds = response.get("builds", [])
        if not builds:
            raise DeploymentError(f"codebuild did not return status for build {build_id}")
        build = builds[0]
        status = build.get("buildStatus", "UNKNOWN")
        phase = build.get("currentPhase", "UNKNOWN")
        pair = (status, phase)
        if pair != previous_status:
            console.info(
                f"CodeBuild {build_id}: status={status} phase={phase} elapsed={int(time.monotonic() - started)}s"
            )
            previous_status = pair
        if status in terminal_states:
            if status != "SUCCEEDED":
                raise DeploymentError(
                    f"runner AMI build failed with status {status}; see CloudWatch logs for CodeBuild"
                )
            return
        time.sleep(10)

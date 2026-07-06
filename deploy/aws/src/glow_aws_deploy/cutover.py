from __future__ import annotations

import shlex
import time
from typing import Any, Iterable

from botocore.exceptions import ClientError

from .common import Console, DeploymentConfig, DeploymentError


def perform_cutover(
    console: Console,
    config: DeploymentConfig,
    *,
    ec2_client: Any,
    elbv2_client: Any,
    ssm_client: Any,
    outputs: dict[str, Any],
) -> None:
    if config.dry_run:
        console.info("Dry-run: would launch a new runner, move the data volume, activate the stack, and switch ALB targets")
        return

    target_group_arns = [str(item) for item in outputs["target_group_arns"]]
    primary_target_group = str(outputs["primary_target_group_arn"])
    launch_template_id = str(outputs["runner_launch_template_id"])
    launch_template_version = str(outputs["runner_launch_template_latest_version"])
    subnet_id = str(outputs["runner_subnet_id"])
    volume_id = str(outputs["data_volume_id"])

    old_instance_id = current_volume_holder(ec2_client, volume_id)
    if not old_instance_id:
        current_targets = current_target_ids(elbv2_client, primary_target_group)
        old_instance_id = current_targets[0] if current_targets else None

    console.info(f"Current volume holder: {old_instance_id or 'none'}")

    new_instance_id = launch_runner(
        ec2_client,
        launch_template_id=launch_template_id,
        launch_template_version=launch_template_version,
        subnet_id=subnet_id,
        domain_name=config.domain_name,
        runner_ami_version=config.runner_ami_version,
    )
    volume_attached_to_new = False
    old_deregistered = False
    old_stopped = False
    new_registered = False

    checkpoint = "Begin cutover"

    def verbose_log(msg: str, fn=console.info) -> str:
        if config.verbose:
            fn(msg)
        return msg

    try:
        checkpoint = verbose_log("Wait for instance running")
        wait_for_instance_running(console, ec2_client, new_instance_id)
        verbose_log("\tok.")
        checkpoint = verbose_log("Wait for ssm online")
        wait_for_ssm_online(console, ssm_client, new_instance_id)
        verbose_log("\tok.")
        checkpoint = verbose_log("Wait for runner bootstrap")
        wait_for_remote_check(
            console,
            ssm_client,
            new_instance_id,
            comment="wait for runner bootstrap",
            commands=["test -f /opt/glow-runner/bootstrap.ready"],
        )
        verbose_log("\tok.")

        if old_instance_id:
            console.info(f"Draining old runner {old_instance_id}")
            deregister_instance_from_target_groups(elbv2_client, target_group_arns, old_instance_id)
            old_deregistered = True
            wait_for_target_absence(console, elbv2_client, target_group_arns, old_instance_id)

            wait_for_remote_check(
                console,
                ssm_client,
                old_instance_id,
                comment="stop old stack",
                commands=["sudo bash /opt/glow/deploy/aws/runtime/stop-stack.sh"],
            )
            old_stopped = True

            detach_volume(console, ec2_client, volume_id, old_instance_id)

        checkpoint = verbose_log(f"Attaching volume {volume_id} to {new_instance_id}")
        attach_volume(console, ec2_client, volume_id, new_instance_id)
        volume_attached_to_new = True

        checkpoint = verbose_log("Activating stack")
        env_prefix = shell_env({"DOMAIN_NAME": config.domain_name})
        wait_for_remote_check(
            console,
            ssm_client,
            new_instance_id,
            comment="activate stack on new runner",
            commands=[f"{env_prefix} sudo bash /opt/glow/deploy/aws/runtime/activate-stack.sh"],
            timeout_seconds=5400,
        )

        verbose_log("\tok.")
        checkpoint = verbose_log("Heathcheck")
        wait_for_remote_check(
            console,
            ssm_client,
            new_instance_id,
            comment="runner healthcheck",
            commands=["sudo /opt/glow-runner/healthcheck.sh"],
            timeout_seconds=1200,
        )
        verbose_log("\tok.")

        register_instance_with_target_groups(elbv2_client, target_group_arns, new_instance_id)
        new_registered = True
        wait_for_target_health(console, elbv2_client, target_group_arns, new_instance_id)

        if old_instance_id and old_instance_id != new_instance_id:
            console.info(f"Terminating old runner {old_instance_id}")
            ec2_client.terminate_instances(InstanceIds=[old_instance_id])

        console.info(f"Cutover complete: {new_instance_id}")
    except Exception as exc:
        console.warn(f"Cutover failed at {checkpoint}: {exc}")
        if config.verbose:
            for commands in [
                ["echo /opt", "ls -la /opt"],
                ["echo /opt/glow-runner", "ls -la /opt/glow-runner"],
                ["echo /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d",
                 "ls -la /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d"],
                # ["echo /var/log/cloud-init.log", "sudo cat /var/log/cloud-init.log"],
                ["echo /var/log/glow-runner-bootstrap.log", "sudo cat /var/log/glow-runner-bootstrap.log"]
            ]:
                try:
                    wait_for_remote_check(
                        console=console,
                        ssm_client=ssm_client,
                        instance_id=new_instance_id,
                        comment="debugging info for failed cutover",
                        commands=commands,
                        timeout_seconds=100
                    )
                except Exception:
                    console.warn(f"Verbose debugging query failed {commands[0]}.")
        rollback_cutover(
            console,
            ec2_client=ec2_client,
            elbv2_client=elbv2_client,
            ssm_client=ssm_client,
            old_instance_id=old_instance_id,
            new_instance_id=new_instance_id,
            volume_id=volume_id,
            target_group_arns=target_group_arns,
            volume_attached_to_new=volume_attached_to_new,
            old_deregistered=old_deregistered,
            old_stopped=old_stopped,
            new_registered=new_registered,
            domain_name=config.domain_name,
        )
        raise


def shell_env(values: dict[str, str]) -> str:
    return " ".join(f"{key}={shlex.quote(value)}" for key, value in values.items())


def current_target_ids(elbv2_client: Any, target_group_arn: str) -> list[str]:
    response = elbv2_client.describe_target_health(TargetGroupArn=target_group_arn)
    ids: list[str] = []
    for item in response.get("TargetHealthDescriptions", []):
        target_id = item.get("Target", {}).get("Id")
        if isinstance(target_id, str):
            ids.append(target_id)
    return ids


def current_volume_holder(ec2_client: Any, volume_id: str) -> str | None:
    response = ec2_client.describe_volumes(VolumeIds=[volume_id])
    volumes = response.get("Volumes", [])
    if not volumes:
        raise DeploymentError(f"volume not found: {volume_id}")
    attachments = volumes[0].get("Attachments", [])
    if not attachments:
        return None
    return attachments[0].get("InstanceId")


def launch_runner(
    ec2_client: Any,
    *,
    launch_template_id: str,
    launch_template_version: str,
    subnet_id: str,
    domain_name: str,
    runner_ami_version: str,
) -> str:
    response = ec2_client.run_instances(
        MinCount=1,
        MaxCount=1,
        LaunchTemplate={"LaunchTemplateId": launch_template_id, "Version": launch_template_version},
        SubnetId=subnet_id,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"{domain_name}-runner"},
                    {"Key": "Domain", "Value": domain_name},
                    {"Key": "Component", "Value": "glow-runner"},
                    {"Key": "Version", "Value": runner_ami_version},
                ],
            },
            {
                "ResourceType": "volume",
                "Tags": [
                    {"Key": "Domain", "Value": domain_name},
                    {"Key": "Component", "Value": "glow-runner-root"},
                    {"Key": "Version", "Value": runner_ami_version},
                ],
            },
        ],
    )
    return response["Instances"][0]["InstanceId"]


def wait_for_instance_running(console: Console, ec2_client: Any, instance_id: str) -> None:
    console.info(f"Waiting for EC2 instance {instance_id} to enter running state")
    ec2_client.get_waiter("instance_running").wait(InstanceIds=[instance_id])


def wait_for_ssm_online(console: Console, ssm_client: Any, instance_id: str) -> None:
    started = time.monotonic()
    while True:
        response = ssm_client.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        for item in response.get("InstanceInformationList", []):
            if item.get("PingStatus") == "Online":
                console.info(f"SSM is online for {instance_id}")
                return
        elapsed = int(time.monotonic() - started)
        console.info(f"Waiting for SSM on {instance_id} ({elapsed}s elapsed)")
        time.sleep(10)


def send_ssm_commands(
    ssm_client: Any,
    *,
    instance_id: str,
    comment: str,
    commands: list[str],
    timeout_seconds: int,
) -> str:
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Comment=comment,
        TimeoutSeconds=timeout_seconds,
        Parameters={"commands": commands},
    )
    return response["Command"]["CommandId"]


def wait_for_remote_check(
    console: Console,
    ssm_client: Any,
    instance_id: str,
    *,
    comment: str,
    commands: list[str],
    timeout_seconds: int = 1800,
) -> None:
    command_id = send_ssm_commands(
        ssm_client,
        instance_id=instance_id,
        comment=comment,
        commands=commands,
        timeout_seconds=timeout_seconds,
    )

    seen_stdout: list[str] = []
    seen_stderr: list[str] = []
    started = time.monotonic()
    while True:
        try:
            invocation = ssm_client.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "InvocationDoesNotExist":
                time.sleep(3)
                continue
            raise

        stdout_lines = invocation.get("StandardOutputContent", "").splitlines()
        stderr_lines = invocation.get("StandardErrorContent", "").splitlines()

        for line in stdout_lines[len(seen_stdout):]:
            if line.strip():
                console.info(line)
        for line in stderr_lines[len(seen_stderr):]:
            if line.strip():
                console.warn(line)
        seen_stdout = stdout_lines
        seen_stderr = stderr_lines

        status = invocation.get("Status", "Unknown")
        if status == "Success" and int(invocation.get("ResponseCode", 1)) == 0:
            return
        if status in {"Cancelled", "TimedOut", "Failed", "Cancelling"}:
            stderr = invocation.get("StandardErrorContent", "").strip()
            stdout = invocation.get("StandardOutputContent", "").strip()
            details = stderr or stdout or status
            raise DeploymentError(f"remote command failed on {instance_id}: {details}")

        elapsed = int(time.monotonic() - started)
        console.info(f"Waiting for {comment} on {instance_id} ({elapsed}s elapsed, status={status})")
        time.sleep(5)


def deregister_instance_from_target_groups(elbv2_client: Any, target_group_arns: Iterable[str], instance_id: str) -> None:
    for arn in target_group_arns:
        elbv2_client.deregister_targets(TargetGroupArn=arn, Targets=[{"Id": instance_id}])


def register_instance_with_target_groups(elbv2_client: Any, target_group_arns: Iterable[str], instance_id: str) -> None:
    for arn in target_group_arns:
        elbv2_client.register_targets(TargetGroupArn=arn, Targets=[{"Id": instance_id}])


def wait_for_target_absence(console: Console, elbv2_client: Any, target_group_arns: Iterable[str], instance_id: str) -> None:
    deadline = time.monotonic() + 300
    while True:
        all_absent = True
        for arn in target_group_arns:
            response = elbv2_client.describe_target_health(TargetGroupArn=arn)
            states = [
                item.get("TargetHealth", {}).get("State", "unknown")
                for item in response.get("TargetHealthDescriptions", [])
                if item.get("Target", {}).get("Id") == instance_id
            ]
            if states and any(state not in {"unused", "draining"} for state in states):
                all_absent = False
        if all_absent:
            return
        if time.monotonic() >= deadline:
            raise DeploymentError(f"timed out waiting for target deregistration of {instance_id}")
        console.info(f"Waiting for old runner {instance_id} to leave target groups")
        time.sleep(5)


def wait_for_target_health(console: Console, elbv2_client: Any, target_group_arns: Iterable[str], instance_id: str) -> None:
    deadline = time.monotonic() + 1200
    while True:
        all_healthy = True
        for arn in target_group_arns:
            response = elbv2_client.describe_target_health(TargetGroupArn=arn)
            state = None
            for item in response.get("TargetHealthDescriptions", []):
                if item.get("Target", {}).get("Id") == instance_id:
                    state = item.get("TargetHealth", {}).get("State")
                    break
            if state != "healthy":
                all_healthy = False
        if all_healthy:
            return
        if time.monotonic() >= deadline:
            raise DeploymentError(f"timed out waiting for target group health on {instance_id}")
        console.info(f"Waiting for ALB target health on {instance_id}")
        time.sleep(10)


def detach_volume(console: Console, ec2_client: Any, volume_id: str, instance_id: str) -> None:
    console.info(f"Detaching volume {volume_id} from {instance_id}")
    ec2_client.detach_volume(VolumeId=volume_id, InstanceId=instance_id)
    ec2_client.get_waiter("volume_available").wait(VolumeIds=[volume_id])


def attach_volume(console: Console, ec2_client: Any, volume_id: str, instance_id: str) -> None:
    console.info(f"Attaching volume {volume_id} to {instance_id}")
    ec2_client.attach_volume(VolumeId=volume_id, InstanceId=instance_id, Device="/dev/xvdf")
    ec2_client.get_waiter("volume_in_use").wait(VolumeIds=[volume_id])


def rollback_cutover(
    console: Console,
    *,
    ec2_client: Any,
    elbv2_client: Any,
    ssm_client: Any,
    old_instance_id: str | None,
    new_instance_id: str,
    volume_id: str,
    target_group_arns: list[str],
    volume_attached_to_new: bool,
    old_deregistered: bool,
    old_stopped: bool,
    new_registered: bool,
    domain_name: str,
) -> None:
    if new_registered:
        try:
            deregister_instance_from_target_groups(elbv2_client, target_group_arns, new_instance_id)
        except Exception as exc:
            console.warn(f"Failed to deregister new runner during rollback: {exc}")

    if volume_attached_to_new:
        try:
            wait_for_remote_check(
                console,
                ssm_client,
                new_instance_id,
                comment="stop new stack for rollback",
                commands=["sudo bash /opt/glow/deploy/aws/runtime/stop-stack.sh"],
            )
        except Exception as exc:
            console.warn(f"Failed to stop new stack during rollback: {exc}")

        try:
            detach_volume(console, ec2_client, volume_id, new_instance_id)
        except Exception as exc:
            console.warn(f"Failed to detach volume from new runner during rollback: {exc}")

    if old_instance_id:
        try:
            attach_volume(console, ec2_client, volume_id, old_instance_id)
            env_prefix = shell_env({"DOMAIN_NAME": domain_name})
            wait_for_remote_check(
                console,
                ssm_client,
                old_instance_id,
                comment="restart old stack during rollback",
                commands=[f"{env_prefix} sudo bash /opt/glow/deploy/aws/runtime/activate-stack.sh"],
                timeout_seconds=5400,
            )
            register_instance_with_target_groups(elbv2_client, target_group_arns, old_instance_id)
            wait_for_target_health(console, elbv2_client, target_group_arns, old_instance_id)
        except Exception as exc:
            console.warn(f"Rollback to old runner failed: {exc}")

    try:
        ec2_client.terminate_instances(InstanceIds=[new_instance_id])
    except Exception as exc:
        console.warn(f"Failed to terminate new runner after rollback: {exc}")

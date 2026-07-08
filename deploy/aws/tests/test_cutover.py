from __future__ import annotations

import pytest

from glow_aws_deploy.common import DeploymentConfig, DeploymentError, ResolvedGitRef
from glow_aws_deploy.cutover import perform_cutover


class FakeConsole:
    def info(self, message: str) -> None:
        pass

    def warn(self, message: str) -> None:
        pass


class FakeWaiter:
    def __init__(self, events: list[tuple[str, ...]], name: str) -> None:
        self.events = events
        self.name = name

    def wait(self, **kwargs: object) -> None:
        volume_ids = tuple(kwargs.get("VolumeIds", []))
        self.events.append(("waiter", self.name, *volume_ids))


class FakeEC2Client:
    def __init__(self, events: list[tuple[str, ...]]) -> None:
        self.events = events

    def attach_volume(self, *, VolumeId: str, InstanceId: str, Device: str) -> None:
        self.events.append(("ec2_attach", VolumeId, InstanceId, Device))

    def detach_volume(self, *, VolumeId: str, InstanceId: str) -> None:
        self.events.append(("ec2_detach", VolumeId, InstanceId))

    def get_waiter(self, name: str) -> FakeWaiter:
        return FakeWaiter(self.events, name)

    def terminate_instances(self, *, InstanceIds: list[str]) -> None:
        self.events.append(("terminate", *InstanceIds))


def make_config() -> DeploymentConfig:
    return DeploymentConfig(
        app_name="glow",
        aws_region="eu-west-2",
        domain_name="example.com",
        certificate_arn="arn:aws:acm:eu-west-2:123456789012:certificate/test",
        git_repo_url="https://github.com/OxfordRSE/glow.git",
        git_ref=ResolvedGitRef(requested_ref="main", resolved_ref="main", commit_sha="a" * 40),
        runner_ami_version="runner-2026-07-08",
        runner_instance_type="t3.large",
        runner_root_volume_size_gb=30,
        data_volume_size_gb=100,
        dry_run=False,
        force_rebuild=False,
        verbose=False,
    )


def make_outputs() -> dict[str, object]:
    return {
        "target_group_arns": ["tg-1"],
        "primary_target_group_arn": "tg-1",
        "runner_launch_template_id": "lt-123",
        "runner_launch_template_latest_version": "1",
        "runner_subnet_id": "subnet-123",
        "data_volume_id": "vol-1",
    }


def install_common_monkeypatches(monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, ...]], *, fail_on: str | None = None) -> None:
    from glow_aws_deploy import cutover

    monkeypatch.setattr(cutover, "current_volume_holder", lambda *_: "i-old")
    monkeypatch.setattr(cutover, "launch_runner", lambda *_, **__: "i-new")
    monkeypatch.setattr(cutover, "wait_for_instance_running", lambda *_, **__: None)
    monkeypatch.setattr(cutover, "wait_for_ssm_online", lambda *_, **__: None)
    monkeypatch.setattr(cutover, "wait_for_target_absence", lambda *_, **__: None)
    monkeypatch.setattr(cutover, "wait_for_target_health", lambda *_, **__: None)
    monkeypatch.setattr(
        cutover,
        "deregister_instance_from_target_groups",
        lambda _client, _arns, instance_id: events.append(("deregister", instance_id)),
    )
    monkeypatch.setattr(
        cutover,
        "register_instance_with_target_groups",
        lambda _client, _arns, instance_id: events.append(("register", instance_id)),
    )

    def fake_wait_for_remote_check(
        _console: object,
        _ssm_client: object,
        instance_id: str,
        *,
        comment: str,
        commands: list[str],
        timeout_seconds: int = 1800,
    ) -> None:
        del timeout_seconds
        events.append(("remote", comment, instance_id, commands[0]))
        if fail_on == comment:
            raise DeploymentError(f"forced failure during {comment}")

    monkeypatch.setattr(cutover, "wait_for_remote_check", fake_wait_for_remote_check)


def test_perform_cutover_mounts_after_attach_and_unmounts_before_detach(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, ...]] = []
    install_common_monkeypatches(monkeypatch, events)

    perform_cutover(
        FakeConsole(),
        make_config(),
        ec2_client=FakeEC2Client(events),
        elbv2_client=object(),
        ssm_client=object(),
        outputs=make_outputs(),
    )

    assert events == [
        ("remote", "wait for runner bootstrap", "i-new", "timeout 1800 bash -c 'until test -f /opt/glow-runner/bootstrap.ready; do sleep 1; done'"),
        ("deregister", "i-old"),
        ("remote", "stop old stack", "i-old", "sudo bash /opt/glow/deploy/aws/runtime/stop-stack.sh"),
        ("remote", "unmount data volume", "i-old", "sudo bash /opt/glow/deploy/aws/runtime/unmount-data-volume.sh"),
        ("ec2_detach", "vol-1", "i-old"),
        ("waiter", "volume_available", "vol-1"),
        ("ec2_attach", "vol-1", "i-new", "/dev/xvdf"),
        ("waiter", "volume_in_use", "vol-1"),
        ("remote", "mount data volume", "i-new", "sudo bash /opt/glow/deploy/aws/runtime/mount-data-volume.sh"),
        ("remote", "activate stack on new runner", "i-new", "DOMAIN_NAME=example.com sudo bash /opt/glow/deploy/aws/runtime/activate-stack.sh"),
        ("remote", "runner healthcheck", "i-new", "sudo /opt/glow-runner/healthcheck.sh"),
        ("register", "i-new"),
        ("terminate", "i-old"),
    ]


def test_perform_cutover_rolls_back_by_remounting_old_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, ...]] = []
    install_common_monkeypatches(monkeypatch, events, fail_on="activate stack on new runner")

    with pytest.raises(DeploymentError, match="forced failure"):
        perform_cutover(
            FakeConsole(),
            make_config(),
            ec2_client=FakeEC2Client(events),
            elbv2_client=object(),
            ssm_client=object(),
            outputs=make_outputs(),
        )

    assert events == [
        ("remote", "wait for runner bootstrap", "i-new", "timeout 1800 bash -c 'until test -f /opt/glow-runner/bootstrap.ready; do sleep 1; done'"),
        ("deregister", "i-old"),
        ("remote", "stop old stack", "i-old", "sudo bash /opt/glow/deploy/aws/runtime/stop-stack.sh"),
        ("remote", "unmount data volume", "i-old", "sudo bash /opt/glow/deploy/aws/runtime/unmount-data-volume.sh"),
        ("ec2_detach", "vol-1", "i-old"),
        ("waiter", "volume_available", "vol-1"),
        ("ec2_attach", "vol-1", "i-new", "/dev/xvdf"),
        ("waiter", "volume_in_use", "vol-1"),
        ("remote", "mount data volume", "i-new", "sudo bash /opt/glow/deploy/aws/runtime/mount-data-volume.sh"),
        ("remote", "activate stack on new runner", "i-new", "DOMAIN_NAME=example.com sudo bash /opt/glow/deploy/aws/runtime/activate-stack.sh"),
        ("remote", "stop new stack for rollback", "i-new", "sudo bash /opt/glow/deploy/aws/runtime/stop-stack.sh"),
        ("remote", "unmount data volume", "i-new", "sudo bash /opt/glow/deploy/aws/runtime/unmount-data-volume.sh"),
        ("ec2_detach", "vol-1", "i-new"),
        ("waiter", "volume_available", "vol-1"),
        ("ec2_attach", "vol-1", "i-old", "/dev/xvdf"),
        ("waiter", "volume_in_use", "vol-1"),
        ("remote", "mount data volume", "i-old", "sudo bash /opt/glow/deploy/aws/runtime/mount-data-volume.sh"),
        ("remote", "restart old stack during rollback", "i-old", "DOMAIN_NAME=example.com sudo bash /opt/glow/deploy/aws/runtime/activate-stack.sh"),
        ("register", "i-old"),
        ("terminate", "i-new"),
    ]

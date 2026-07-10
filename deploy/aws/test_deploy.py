from pathlib import Path
from types import SimpleNamespace

import deploy


def test_rerun_runner_userdata_reports_last_bootstrap_log_line(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_ssm_command(instance_id, region, commands, comment, timeout=1800):
        captured["instance_id"] = instance_id
        captured["region"] = region
        captured["commands"] = commands
        captured["comment"] = comment
        captured["timeout"] = timeout

    monkeypatch.setattr(deploy, "run_ssm_command", fake_run_ssm_command)

    deploy.rerun_runner_userdata("i-1234567890", "eu-west-2")

    assert captured["instance_id"] == "i-1234567890"
    assert captured["region"] == "eu-west-2"
    assert captured["comment"] == "rerun runner userdata"
    assert captured["timeout"] == 3600

    command = captured["commands"][0]
    assert "tail -n 1 /var/log/glow-runner-bootstrap.log" in command
    assert "last bootstrap log line:" in command


def test_rerun_runner_userdata_accepts_git_environment_overrides(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_ssm_command(instance_id, region, commands, comment, timeout=1800):
        captured["instance_id"] = instance_id
        captured["region"] = region
        captured["commands"] = commands
        captured["comment"] = comment
        captured["timeout"] = timeout

    monkeypatch.setattr(deploy, "run_ssm_command", fake_run_ssm_command)

    deploy.rerun_runner_userdata(
        "i-1234567890",
        "eu-west-2",
        {
            "GIT_REPO_URL": "https://example.com/glow.git",
            "GIT_CHECKOUT_REF": "deadbeef",
        },
    )

    command = captured["commands"][0]
    assert "export GIT_REPO_URL=https://example.com/glow.git" in command
    assert "export GIT_CHECKOUT_REF=deadbeef" in command


def test_prepare_runner_repository_clones_and_checks_out_requested_ref(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_ssm_command(instance_id, region, commands, comment, timeout=1800):
        captured["instance_id"] = instance_id
        captured["region"] = region
        captured["commands"] = commands
        captured["comment"] = comment
        captured["timeout"] = timeout

    monkeypatch.setattr(deploy, "run_ssm_command", fake_run_ssm_command)

    deploy.prepare_runner_repository(
        "i-1234567890",
        "eu-west-2",
        "https://example.com/glow.git",
        "deadbeef",
    )

    assert captured["comment"] == "prepare runner repository"
    assert captured["timeout"] == 3600

    command = captured["commands"][0]
    assert 'git clone "${repo_url}" /opt/glow' in command
    assert 'git -C /opt/glow checkout --force "${checkout_ref}"' in command
    assert "repo_url=https://example.com/glow.git" in command
    assert "checkout_ref=deadbeef" in command


def test_runner_userdata_prefers_git_environment_over_template_defaults():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert 'GIT_REPO_URL="${GIT_REPO_URL:-${git_repo_url}}"' in template
    assert 'GIT_CHECKOUT_REF="${GIT_CHECKOUT_REF:-${git_checkout_ref}}"' in template


def test_runner_userdata_uses_var_lib_glow_for_persistent_state_check():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert "/var/lib/glow/.mnttest" in template
    assert "/data/.mnttest" not in template


def test_runner_userdata_does_not_clone_or_checkout_repository():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert "git clone" not in template
    assert "git -C /opt/glow checkout --force" not in template


def test_update_prepares_repository_before_rerunning_userdata(monkeypatch):
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(deploy, "ensure_state_bucket", lambda region, domain: "bucket")
    monkeypatch.setattr(deploy, "terraform_init", lambda bucket, region: None)
    monkeypatch.setattr(
        deploy,
        "run_command",
        lambda args, check=True, cwd=None: SimpleNamespace(
            stdout='{"runner_instance_id": {"value": "i-1234567890"}}'
        ),
    )
    monkeypatch.setattr(
        deploy,
        "wait_for_ssm_online",
        lambda instance_id, region: calls.append(("wait", instance_id)),
    )
    monkeypatch.setattr(
        deploy,
        "prepare_runner_repository",
        lambda instance_id, region, repo_url, checkout_ref: calls.append(
            ("prepare", (instance_id, region, repo_url, checkout_ref))
        ),
    )
    monkeypatch.setattr(
        deploy,
        "rerun_runner_userdata",
        lambda instance_id, region, env=None: calls.append(("rerun", env)),
    )
    monkeypatch.setattr(
        deploy,
        "verify_runner_health",
        lambda instance_id, region: calls.append(("verify", instance_id)),
    )

    config = deploy.Config(
        domain_name="example.com",
        certificate_arn="",
        git_repo_url="https://example.com/glow.git",
        git_ref="main",
        git_commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        aws_region="eu-west-2",
        app_name="glow-core",
        runner_instance_type="t3.medium",
        runner_root_volume_size_gb=100,
        dry_run=False,
        force_rebuild_ami=False,
    )

    deploy.update(config)

    assert calls == [
        ("wait", "i-1234567890"),
        (
            "prepare",
            (
                "i-1234567890",
                "eu-west-2",
                "https://example.com/glow.git",
                "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            ),
        ),
        (
            "rerun",
            {
                "GIT_REPO_URL": "https://example.com/glow.git",
                "GIT_CHECKOUT_REF": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            },
        ),
        ("verify", "i-1234567890"),
    ]


def test_provision_prepares_repository_before_rerunning_userdata(monkeypatch):
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(deploy, "ensure_state_bucket", lambda region, domain: "bucket")
    monkeypatch.setattr(
        deploy, "find_ami_in_account", lambda region, commit: "ami-12345678"
    )
    monkeypatch.setattr(deploy, "terraform_init", lambda bucket, region: None)
    monkeypatch.setattr(
        deploy,
        "terraform_apply",
        lambda config, ami_id: {
            "runner_instance_id": "i-1234567890",
            "alb_dns_name": "alb.example.com",
        },
    )
    monkeypatch.setattr(
        deploy,
        "wait_for_ssm_online",
        lambda instance_id, region: calls.append(("wait", instance_id)),
    )
    monkeypatch.setattr(
        deploy,
        "prepare_runner_repository",
        lambda instance_id, region, repo_url, checkout_ref: calls.append(
            ("prepare", (instance_id, region, repo_url, checkout_ref))
        ),
    )
    monkeypatch.setattr(
        deploy,
        "rerun_runner_userdata",
        lambda instance_id, region, env=None: calls.append(("rerun", env)),
    )
    monkeypatch.setattr(
        deploy,
        "verify_runner_health",
        lambda instance_id, region: calls.append(("verify", instance_id)),
    )

    config = deploy.Config(
        domain_name="example.com",
        certificate_arn="",
        git_repo_url="https://example.com/glow.git",
        git_ref="main",
        git_commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        aws_region="eu-west-2",
        app_name="glow-core",
        runner_instance_type="t3.medium",
        runner_root_volume_size_gb=100,
        dry_run=False,
        force_rebuild_ami=False,
    )

    deploy.provision(config)

    assert calls == [
        ("wait", "i-1234567890"),
        (
            "prepare",
            (
                "i-1234567890",
                "eu-west-2",
                "https://example.com/glow.git",
                "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            ),
        ),
        (
            "rerun",
            {
                "GIT_REPO_URL": "https://example.com/glow.git",
                "GIT_CHECKOUT_REF": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            },
        ),
        ("verify", "i-1234567890"),
    ]

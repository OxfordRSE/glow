from pathlib import Path
from types import SimpleNamespace

import deploy
import pytest


def test_resolve_git_commit_prefers_peeled_annotated_tag_commit(monkeypatch):
    def fake_run_command(args, check=True, cwd=None):
        return SimpleNamespace(
            stdout=(
                "1111111111111111111111111111111111111111\trefs/tags/v1.2.3\n"
                "2222222222222222222222222222222222222222\trefs/tags/v1.2.3^{}\n"
            )
        )

    monkeypatch.setattr(deploy, "run_command", fake_run_command)

    assert (
        deploy.resolve_git_commit("https://example.com/glow.git", "v1.2.3")
        == "2222222222222222222222222222222222222222"
    )


def test_extract_ami_id_from_packer_output_reads_machine_readable_artifact_id():
    output = "\n".join(
        [
            "1720781200,,ui,say,Building AMI",
            "1720781201,amazon-ebs.runner,artifact,0,id,eu-west-2:ami-0123456789abcdef0",
        ]
    )

    assert (
        deploy.extract_ami_id_from_packer_output(output) == "ami-0123456789abcdef0"
    )


def test_extract_ami_id_from_packer_output_ignores_trailing_control_characters():
    output = (
        "1720781201,amazon-ebs.runner,artifact,0,id,"
        "eu-west-2:ami-0123456789abcdef0\u001b[0m"
    )

    assert (
        deploy.extract_ami_id_from_packer_output(output) == "ami-0123456789abcdef0"
    )


def test_extract_ami_id_from_packer_output_rejects_missing_artifact_id():
    with pytest.raises(deploy.DeployError, match="could not extract AMI ID"):
        deploy.extract_ami_id_from_packer_output("1720781200,,ui,say,Building AMI")


def test_validate_ami_id_rejects_invalid_characters():
    with pytest.raises(deploy.DeployError, match="invalid AMI ID"):
        deploy.validate_ami_id("ami-01234567\u0007")


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
            "GIT_REF": "v1.2.3",
            "GIT_COMMIT": "deadbeef",
        },
    )

    command = captured["commands"][0]
    assert "export GIT_REPO_URL=https://example.com/glow.git" in command
    assert "export GIT_REF=v1.2.3" in command
    assert "export GIT_COMMIT=deadbeef" in command


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


def test_wait_for_runner_bootstrap_completion_waits_for_ready_file(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_ssm_command(instance_id, region, commands, comment, timeout=1800):
        captured["instance_id"] = instance_id
        captured["region"] = region
        captured["commands"] = commands
        captured["comment"] = comment
        captured["timeout"] = timeout

    monkeypatch.setattr(deploy, "run_ssm_command", fake_run_ssm_command)

    deploy.wait_for_runner_bootstrap_completion("i-1234567890", "eu-west-2")

    assert captured["instance_id"] == "i-1234567890"
    assert captured["region"] == "eu-west-2"
    assert captured["comment"] == "wait for runner bootstrap completion"
    assert captured["timeout"] == 1800
    assert captured["commands"] == [
        "timeout 300 bash -c 'while [ ! -f /opt/glow-runner/bootstrap.ready ]; do sleep 1; done'"
    ]


def test_runner_userdata_prefers_git_environment_over_template_defaults():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert 'GIT_REPO_URL="$${GIT_REPO_URL:-${git_repo_url}}"' in template
    assert 'GIT_REF="$${GIT_REF:-${git_ref}}"' in template
    assert 'GIT_COMMIT="$${GIT_COMMIT:-${git_checkout_ref}}"' in template


def test_runner_userdata_marks_bootstrap_ready_before_waiting_for_repository_checkout():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    wait_line = (
        '  echo "[PROGRESS] Repository checkout not present yet; waiting for deploy.py '
        'to prepare it"'
    )
    assert "touch /opt/glow-runner/bootstrap.ready" in template
    assert wait_line in template
    assert template.index("touch /opt/glow-runner/bootstrap.ready") < template.index(
        wait_line
    )


def test_runner_userdata_persists_git_ref_and_commit_in_environment_files():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert "GIT_REF=$${GIT_REF}" in template
    assert "GIT_COMMIT=$${GIT_COMMIT}" in template
    assert "/etc/environment" in template
    assert "GIT_REF=\"$${GIT_REF}\"" in template
    assert "GIT_COMMIT=\"$${GIT_COMMIT}\"" in template


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


def test_activate_stack_configures_odk_without_querying_users_id():
    script_path = Path(__file__).with_name("runtime") / "activate-stack.sh"
    script = script_path.read_text()

    assert "SELECT id FROM users" not in script
    assert "user-create 2>&1 || true" in script
    assert "user-set-password" in script


def test_activate_stack_writes_requested_git_ref_and_commit_to_metadata():
    script_path = Path(__file__).with_name("runtime") / "activate-stack.sh"
    script = script_path.read_text()

    assert '"git_ref": "${GIT_REF:-}",' in script
    assert '"git_commit": "${checkout_ref}"' in script


def test_activate_stack_uses_odk_domain_for_helper_host_header_and_ping():
    script_path = Path(__file__).with_name("runtime") / "activate-stack.sh"
    script = script_path.read_text()

    assert 'export ODK_DOMAIN="odk.${DOMAIN_NAME}"' in script
    assert 'info "> odk_ping"' in script
    assert 'if odk_ping >/dev/null 2>&1; then' in script
    assert "curl -fsS -H \"Host: odk.$DOMAIN_NAME\" http://127.0.0.1:8080/" not in script
    assert 'curl -fsS http://127.0.0.1:8080/ >/dev/null' not in script


def test_odk_api_helper_supports_optional_host_header_and_ping():
    script_path = Path(__file__).parents[1] / ".." / "scripts" / "odk" / "odk-api-helper.sh"
    script = script_path.resolve().read_text()

    assert 'ODK_HOST_HEADER="${ODK_DOMAIN:-}"' in script
    assert 'odk_curl() {' in script
    assert 'curl -H "Host: ${ODK_HOST_HEADER}" "$@"' in script
    assert 'odk_ping() {' in script
    assert 'local root_url="${ODK_API_BASE%/v1}/"' in script
    assert 'odk_curl -fsS "${root_url}"' in script


def test_get_git_ref_script_reads_runner_environment_file():
    script_path = Path(__file__).with_name("runtime") / "get-git-ref.sh"
    script = script_path.read_text()

    assert 'ENV_FILE="/etc/glow-runner.env"' in script
    assert 'case "${1:-}" in' in script
    assert '--commit)' in script
    assert 'printf \"%s\\n\" "${GIT_REF:-}"' in script
    assert 'printf \"%s\\n\" "${GIT_COMMIT:-}"' in script


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
        "wait_for_runner_bootstrap_completion",
        lambda instance_id, region: calls.append(("bootstrap", instance_id)),
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
        ("bootstrap", "i-1234567890"),
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
                "GIT_REF": "main",
                "GIT_COMMIT": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
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
        "wait_for_runner_bootstrap_completion",
        lambda instance_id, region: calls.append(("bootstrap", instance_id)),
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
        ("bootstrap", "i-1234567890"),
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
                "GIT_REF": "main",
                "GIT_COMMIT": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            },
        ),
        ("verify", "i-1234567890"),
    ]

from pathlib import Path

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


def test_runner_userdata_uses_var_lib_glow_for_persistent_state_check():
    template_path = Path(__file__).with_name("templates") / "runner-userdata.sh.tpl"
    template = template_path.read_text()

    assert "/var/lib/glow/.mnttest" in template
    assert "/data/.mnttest" not in template

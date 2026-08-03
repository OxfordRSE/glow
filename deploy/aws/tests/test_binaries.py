import pytest

import glow_deploy.binaries as binaries


@pytest.fixture(autouse=True)
def _clear_overrides(monkeypatch):
    monkeypatch.delenv("GLOW_DEPLOY_TERRAFORM_BIN", raising=False)
    monkeypatch.delenv("GLOW_DEPLOY_PACKER_BIN", raising=False)
    monkeypatch.setattr(binaries.sys, "frozen", False, raising=False)


def test_terraform_binary_respects_env_override(monkeypatch):
    monkeypatch.setenv("GLOW_DEPLOY_TERRAFORM_BIN", "/custom/terraform")
    assert binaries.terraform_binary() == "/custom/terraform"


def test_packer_binary_respects_env_override(monkeypatch):
    monkeypatch.setenv("GLOW_DEPLOY_PACKER_BIN", "/custom/packer")
    assert binaries.packer_binary() == "/custom/packer"


def test_terraform_binary_falls_back_to_path(monkeypatch):
    monkeypatch.setattr(binaries.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert binaries.terraform_binary() == "/usr/bin/terraform"


def test_terraform_binary_raises_when_not_found(monkeypatch):
    monkeypatch.setattr(binaries.shutil, "which", lambda name: None)
    with pytest.raises(binaries.DeployError, match="required binary not found"):
        binaries.terraform_binary()


def test_terraform_binary_prefers_a_vendored_binary_in_a_frozen_build(
    monkeypatch, tmp_path
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    terraform_path = bin_dir / "terraform"
    terraform_path.write_text("#!/bin/sh\n")

    monkeypatch.setattr(binaries.sys, "frozen", True, raising=False)
    monkeypatch.setattr(binaries.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(
        binaries.shutil, "which", lambda name: f"/usr/bin/{name}"
    )  # should be ignored

    assert binaries.terraform_binary() == str(terraform_path)


def test_terraform_binary_falls_back_to_path_when_frozen_but_binary_not_vendored(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(binaries.sys, "frozen", True, raising=False)
    monkeypatch.setattr(binaries.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(binaries.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert binaries.terraform_binary() == "/usr/bin/terraform"

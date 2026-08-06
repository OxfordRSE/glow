from __future__ import annotations

from glow_deploy.gui import paths


def test_gui_dir_returns_the_real_package_directory_when_not_frozen(monkeypatch):
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)

    assert paths.gui_dir() == paths._GUI_DIR
    assert (paths.gui_dir() / "templates").is_dir()


def test_gui_dir_uses_meipass_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert paths.gui_dir() == tmp_path / "glow_deploy" / "gui"

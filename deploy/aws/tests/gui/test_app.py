"""create_app() wiring: version defaults and the update-nudge banner."""

from __future__ import annotations

from starlette.testclient import TestClient

from glow_deploy.gui import secret_store, update_check
from glow_deploy.gui.app import create_app


def test_create_app_defaults_to_dev_version_and_skips_update_check(monkeypatch):
    monkeypatch.setattr(secret_store, "load_credentials", lambda profile: None)
    called = []
    monkeypatch.setattr(
        update_check, "latest_release_tag", lambda current_version: called.append(True)
    )

    app = create_app()

    assert app.state.current_version == "dev"
    assert app.state.latest_release is None
    assert called == []


def test_update_banner_renders_when_a_newer_release_is_set(monkeypatch):
    monkeypatch.setattr(secret_store, "load_credentials", lambda profile: None)
    app = create_app()
    app.state.latest_release = "gui-v9.9.9"
    client = TestClient(app)

    response = client.get("/signin")

    assert "gui-v9.9.9" in response.text

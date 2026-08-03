"""FastAPI route tests for the GUI backend (Phase 3): auth wiring, session
gating, and the plan/apply job flow for new deployments and updates.

Core AWS-touching functions (core.list_deployments/provision/update, the
SSO/manual sign-in helpers, GitHub ref resolution) are monkeypatched — these
tests exercise route/job wiring, not real AWS or network calls.
"""

from __future__ import annotations

import time

import pytest
from starlette.testclient import TestClient

from glow_deploy import core, github_api
from glow_deploy.errors import DeployError
from glow_deploy.gui import aws_auth, secret_store
from glow_deploy.gui.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(secret_store, "load_credentials", lambda profile: None)
    monkeypatch.setattr(secret_store, "save_credentials", lambda profile, creds: None)
    monkeypatch.setattr(secret_store, "delete_credentials", lambda profile: None)
    app = create_app()
    return TestClient(app)


def _sign_in(client: TestClient) -> None:
    client.app.state.session = object()
    client.app.state.region = "eu-west-2"


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/jobs/{job_id}/status").json()
        if status["status"] not in ("pending", "running"):
            return status
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Session gating
# ---------------------------------------------------------------------------


def test_signin_page_renders_without_a_session(client):
    response = client.get("/signin")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_protected_routes_redirect_to_signin_when_signed_out(client):
    response = client.get("/deployments", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/signin"


# ---------------------------------------------------------------------------
# Manual sign-in
# ---------------------------------------------------------------------------


def test_manual_signin_sets_session_and_redirects_home(client, monkeypatch):
    sentinel_session = object()
    monkeypatch.setattr(
        aws_auth, "session_from_manual_credentials", lambda *a, **k: sentinel_session
    )
    monkeypatch.setattr(aws_auth, "to_stored_credentials", lambda session, **k: object())

    response = client.post(
        "/signin/manual",
        data={"access_key": "AKIA", "secret_key": "secret", "region": "eu-west-2"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/deployments"
    assert client.app.state.session is sentinel_session


def test_manual_signin_shows_error_on_rejected_credentials(client, monkeypatch):
    monkeypatch.setattr(
        aws_auth,
        "session_from_manual_credentials",
        lambda *a, **k: (_ for _ in ()).throw(DeployError("AWS credentials rejected")),
    )

    response = client.post(
        "/signin/manual",
        data={"access_key": "bad", "secret_key": "bad", "region": "eu-west-2"},
    )

    assert response.status_code == 200
    assert "AWS credentials rejected" in response.text
    assert client.app.state.session is None


# ---------------------------------------------------------------------------
# Home / deployment listing
# ---------------------------------------------------------------------------


def test_home_lists_deployments(client, monkeypatch):
    _sign_in(client)
    monkeypatch.setattr(
        core,
        "list_deployments",
        lambda session, region: [
            {
                "instance_id": "i-123",
                "state": "running",
                "domain": "example.com",
                "git_ref": "main",
                "git_commit": "deadbeef" * 5,
                "launch_time": "2026-01-01T00:00:00Z",
            }
        ],
    )

    response = client.get("/deployments")

    assert response.status_code == 200
    assert "example.com" in response.text


# ---------------------------------------------------------------------------
# New deployment: plan -> apply
# ---------------------------------------------------------------------------


def test_new_deployment_plan_then_apply_provisions(client, monkeypatch):
    _sign_in(client)
    monkeypatch.setattr(
        github_api, "resolve_git_commit_via_github", lambda repo_url, ref: "c" * 40
    )
    provision_calls = []
    monkeypatch.setattr(
        core, "provision", lambda config: provision_calls.append(config) or core.write_line("done")
    )

    plan_response = client.post(
        "/deployments/new/plan",
        data={
            "domain": "example.com",
            "certificate_arn": "arn:aws:acm:...",
            "git_repo_url": "https://github.com/OxfordRSE/glow.git",
            "git_ref": "main",
            "aws_region": "eu-west-2",
            "app_name": "glow-core",
            "runner_instance_type": "t3.medium",
            "runner_root_volume_size_gb": "100",
        },
        follow_redirects=False,
    )
    assert plan_response.status_code == 303
    plan_job_id = plan_response.headers["location"].removeprefix("/jobs/")

    plan_status = _wait_for_job(client, plan_job_id)
    assert plan_status["status"] == "succeeded"
    assert len(provision_calls) == 1
    assert provision_calls[0].dry_run is True

    job_page = client.get(f"/jobs/{plan_job_id}")
    assert "Confirm" in job_page.text
    assert 'action="/deployments/new/apply"' in job_page.text

    apply_response = client.post(
        "/deployments/new/apply",
        data={
            "domain_name": "example.com",
            "certificate_arn": "arn:aws:acm:...",
            "git_repo_url": "https://github.com/OxfordRSE/glow.git",
            "git_ref": "main",
            "git_commit": "c" * 40,
            "aws_region": "eu-west-2",
            "app_name": "glow-core",
            "runner_instance_type": "t3.medium",
            "runner_root_volume_size_gb": "100",
        },
        follow_redirects=False,
    )
    assert apply_response.status_code == 303
    apply_job_id = apply_response.headers["location"].removeprefix("/jobs/")

    apply_status = _wait_for_job(client, apply_job_id)
    assert apply_status["status"] == "succeeded"
    assert len(provision_calls) == 2
    assert provision_calls[1].dry_run is False
    assert provision_calls[1].git_commit == "c" * 40


def test_new_deployment_plan_surfaces_git_ref_errors(client, monkeypatch):
    _sign_in(client)
    monkeypatch.setattr(
        github_api,
        "resolve_git_commit_via_github",
        lambda repo_url, ref: (_ for _ in ()).throw(DeployError("ref not found")),
    )

    response = client.post(
        "/deployments/new/plan",
        data={
            "domain": "example.com",
            "git_repo_url": "https://github.com/OxfordRSE/glow.git",
            "git_ref": "nonexistent",
            "aws_region": "eu-west-2",
        },
    )

    assert response.status_code == 200
    assert "ref not found" in response.text


# ---------------------------------------------------------------------------
# Deployment detail, update, logs
# ---------------------------------------------------------------------------


def _stub_deployment(monkeypatch):
    monkeypatch.setattr(
        core,
        "list_deployments",
        lambda session, region: [
            {
                "instance_id": "i-123",
                "state": "running",
                "domain": "example.com",
                "git_ref": "main",
                "git_commit": "a" * 40,
                "launch_time": "2026-01-01T00:00:00Z",
            }
        ],
    )


def test_deployment_detail_renders_for_known_domain(client, monkeypatch):
    _sign_in(client)
    _stub_deployment(monkeypatch)

    response = client.get("/deployments/example.com")

    assert response.status_code == 200
    assert "example.com" in response.text


def test_deployment_detail_404s_for_unknown_domain(client, monkeypatch):
    _sign_in(client)
    _stub_deployment(monkeypatch)

    response = client.get("/deployments/does-not-exist.com")

    assert response.status_code == 404


def test_update_plan_then_apply_updates(client, monkeypatch):
    _sign_in(client)
    _stub_deployment(monkeypatch)
    monkeypatch.setattr(
        github_api, "resolve_git_commit_via_github", lambda repo_url, ref: "d" * 40
    )
    update_calls = []
    monkeypatch.setattr(
        core, "update", lambda config: update_calls.append(config) or core.write_line("done")
    )

    plan_response = client.post(
        "/deployments/example.com/update/plan",
        data={"git_repo_url": "https://github.com/OxfordRSE/glow.git", "git_ref": "v2"},
        follow_redirects=False,
    )
    assert plan_response.status_code == 303
    plan_job_id = plan_response.headers["location"].removeprefix("/jobs/")
    plan_status = _wait_for_job(client, plan_job_id)
    assert plan_status["status"] == "succeeded"
    assert update_calls[0].dry_run is True

    apply_response = client.post(
        "/deployments/example.com/update/apply",
        data={
            "domain_name": "example.com",
            "git_repo_url": "https://github.com/OxfordRSE/glow.git",
            "git_ref": "v2",
            "git_commit": "d" * 40,
            "aws_region": "eu-west-2",
            "app_name": "glow-core",
        },
        follow_redirects=False,
    )
    assert apply_response.status_code == 303
    apply_job_id = apply_response.headers["location"].removeprefix("/jobs/")
    apply_status = _wait_for_job(client, apply_job_id)
    assert apply_status["status"] == "succeeded"
    assert len(update_calls) == 2
    assert update_calls[1].dry_run is False


def test_logs_route_surfaces_runner_status(client, monkeypatch):
    _sign_in(client)
    _stub_deployment(monkeypatch)
    monkeypatch.setattr(
        core,
        "get_runner_status",
        lambda instance_id, region, session: {
            "health": "ok",
            "git_ref": "main",
            "git_commit": "a" * 40,
        },
    )

    response = client.get("/deployments/example.com/logs")

    assert response.status_code == 200
    assert "ok" in response.text


def test_logs_route_surfaces_deploy_errors(client, monkeypatch):
    _sign_in(client)
    _stub_deployment(monkeypatch)
    monkeypatch.setattr(
        core,
        "get_runner_status",
        lambda instance_id, region, session: (_ for _ in ()).throw(
            DeployError("SSM offline")
        ),
    )

    response = client.get("/deployments/example.com/logs")

    assert response.status_code == 200
    assert "SSM offline" in response.text

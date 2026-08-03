"""FastAPI application factory for the Glow deploy GUI.

`app.state` holds the process-lifetime signed-in session (single local user,
no multi-tenant concerns) plus the background job manager and any in-flight
SSO device-authorization attempt.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from glow_deploy.gui import secret_store
from glow_deploy.gui.aws_auth import session_from_stored_credentials
from glow_deploy.gui.jobs import JobManager
from glow_deploy.gui.routes import auth, deployments, jobs, logs

_PROFILE = "default"
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Glow Deploy")
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.state.region = "eu-west-2"
    app.state.job_manager = JobManager()
    app.state.pending_device_auth = None
    app.state.sso_token = None

    stored = secret_store.load_credentials(_PROFILE)
    app.state.session = session_from_stored_credentials(stored) if stored else None
    if stored:
        app.state.region = stored.region

    app.include_router(auth.router)
    app.include_router(deployments.router)
    app.include_router(jobs.router)
    app.include_router(logs.router)

    return app

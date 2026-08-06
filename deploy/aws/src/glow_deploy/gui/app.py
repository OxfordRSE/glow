"""FastAPI application factory for the Glow deploy GUI.

`app.state` holds the process-lifetime signed-in session (single local user,
no multi-tenant concerns) plus the background job manager and any in-flight
SSO device-authorization attempt.
"""

from __future__ import annotations

import threading
import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from glow_deploy.gui import secret_store, update_check, version
from glow_deploy.gui.aws_auth import session_from_stored_credentials
from glow_deploy.gui.jobs import JobManager
from glow_deploy.gui.paths import gui_dir
from glow_deploy.gui.routes import auth, deployments, heartbeat, jobs, logs

_PROFILE = "default"


def create_app() -> FastAPI:
    app = FastAPI(title="Glow Deploy")
    app.mount("/static", StaticFiles(directory=str(gui_dir() / "static")), name="static")

    app.state.region = "eu-west-2"
    app.state.job_manager = JobManager()
    app.state.pending_device_auth = None
    app.state.sso_token = None
    app.state.current_version = version.CURRENT_VERSION
    app.state.latest_release = None
    # Set at startup (not left at 0) so the watcher thread doesn't see a stale
    # timestamp and quit before the browser tab's first heartbeat lands.
    app.state.last_heartbeat = time.time()

    stored = secret_store.load_credentials(_PROFILE)
    app.state.session = session_from_stored_credentials(stored) if stored else None
    if stored:
        app.state.region = stored.region

    app.include_router(auth.router)
    app.include_router(deployments.router)
    app.include_router(heartbeat.router)
    app.include_router(jobs.router)
    app.include_router(logs.router)

    # Skipped entirely for source/dev runs ("dev" has nothing to compare
    # against) — see version.py.
    if app.state.current_version != "dev":
        threading.Thread(target=_check_for_update, args=(app,), daemon=True).start()

    return app


def _check_for_update(app: FastAPI) -> None:
    tag = update_check.latest_release_tag()
    if tag and tag != app.state.current_version:
        app.state.latest_release = tag

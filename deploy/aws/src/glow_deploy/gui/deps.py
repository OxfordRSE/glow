"""Shared FastAPI dependencies for routes that need a signed-in AWS session."""

from __future__ import annotations

from fastapi import HTTPException, Request

from glow_deploy import core


def require_session(request: Request):
    """Return the signed-in boto3.Session, or redirect to /signin if none."""
    session = request.app.state.session
    if session is None:
        raise HTTPException(status_code=303, headers={"Location": "/signin"})
    return session


def find_deployment(request: Request, domain: str) -> dict:
    """Look up a single deployment by domain, or 404."""
    session = require_session(request)
    deployments = core.list_deployments(session, request.app.state.region)
    for deployment in deployments:
        if deployment["domain"] == domain:
            return deployment
    raise HTTPException(status_code=404, detail=f"no deployment found for domain {domain!r}")

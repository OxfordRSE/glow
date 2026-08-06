"""Status/logs routes for an existing deployment.

No CloudWatch Logs integration in v1 — this surfaces the same on-instance
healthcheck + deployed-git-ref scripts the CLI's update flow already reads
via SSM (see core.get_runner_status).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from glow_deploy import core
from glow_deploy.errors import DeployError
from glow_deploy.gui.deps import find_deployment, require_session
from glow_deploy.gui.templating import templates

router = APIRouter()


@router.get("/deployments/{domain}/logs", response_class=HTMLResponse)
def logs(request: Request, domain: str, session=Depends(require_session)):
    deployment = find_deployment(request, domain)
    status = None
    error = None
    try:
        status = core.get_runner_status(
            deployment["instance_id"], request.app.state.region, session
        )
    except DeployError as exc:
        error = str(exc)

    return templates.TemplateResponse(request, "deployment_logs.html", {"deployment": deployment, "status": status, "error": error},
    )


@router.get("/deployments/{domain}/advanced", response_class=HTMLResponse)
def advanced(request: Request, domain: str, _session=Depends(require_session)):
    deployment = find_deployment(request, domain)
    return templates.TemplateResponse(request, "deployment_advanced.html", {"deployment": deployment}
    )

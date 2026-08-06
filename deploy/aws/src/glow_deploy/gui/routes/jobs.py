"""Job progress: an HTML page (meta-refresh, no JS yet) and a JSON status
endpoint for the JS-based polling Phase 4 adds on top of the same job data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from glow_deploy.gui.deps import require_session
from glow_deploy.gui.templating import templates

router = APIRouter()


def _get_job(request: Request, job_id: str):
    job = request.app.state.job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no job found for id {job_id!r}")
    return job


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_progress(request: Request, job_id: str, _session=Depends(require_session)):
    job = _get_job(request, job_id)
    return templates.TemplateResponse(request, "job_progress.html", {"job": job})


@router.get("/jobs/{job_id}/status")
def job_status(request: Request, job_id: str, _session=Depends(require_session)):
    job = _get_job(request, job_id)
    return {
        "id": job.id,
        "status": job.status,
        "lines": job.lines,
        "error": job.error,
    }

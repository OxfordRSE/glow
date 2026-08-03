"""Deployment listing, creation (plan/apply), and update (plan/apply) routes.

Both the new-deployment and update flows follow the same shape: a "plan" POST
resolves the git ref and runs a dry-run job (terraform plan output ends up in
the job's progress lines), then a "Confirm & Deploy" form on that job's page
POSTs to the matching "apply" route with the resolved fields replayed as
hidden inputs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from glow_deploy import core, github_api
from glow_deploy.errors import DeployError
from glow_deploy.gui.deps import find_deployment, require_session
from glow_deploy.gui.templating import templates

router = APIRouter()


@router.get("/deployments", response_class=HTMLResponse)
def home(request: Request, session=Depends(require_session)):
    deployments = core.list_deployments(session, request.app.state.region)
    return templates.TemplateResponse(request, "home.html", {"deployments": deployments}
    )


@router.get("/deployments/new", response_class=HTMLResponse)
def new_deployment_form(request: Request, _session=Depends(require_session)):
    return templates.TemplateResponse(request, "new_deployment.html", {"error": None,
            "defaults": {
                "git_repo_url": core.DEFAULT_GIT_REPO_URL,
                "git_ref": "main",
                "aws_region": request.app.state.region,
                "app_name": "glow-core",
                "runner_instance_type": "t3.medium",
                "runner_root_volume_size_gb": 100,
            },
        },
    )


@router.post("/deployments/new/plan", response_class=HTMLResponse)
def new_deployment_plan(
    request: Request,
    session=Depends(require_session),
    domain: str = Form(...),
    certificate_arn: str = Form(""),
    git_repo_url: str = Form(core.DEFAULT_GIT_REPO_URL),
    git_ref: str = Form("main"),
    aws_region: str = Form(...),
    app_name: str = Form("glow-core"),
    runner_instance_type: str = Form("t3.medium"),
    runner_root_volume_size_gb: int = Form(100),
    force_rebuild_ami: bool = Form(False),
):
    try:
        git_commit = github_api.resolve_git_commit_via_github(git_repo_url, git_ref)
    except DeployError as exc:
        return templates.TemplateResponse(request, "new_deployment.html", {"error": str(exc),
                "defaults": {
                    "git_repo_url": git_repo_url,
                    "git_ref": git_ref,
                    "aws_region": aws_region,
                    "app_name": app_name,
                    "runner_instance_type": runner_instance_type,
                    "runner_root_volume_size_gb": runner_root_volume_size_gb,
                },
            },
        )

    config_fields = dict(
        domain_name=domain,
        certificate_arn=certificate_arn,
        git_repo_url=git_repo_url,
        git_ref=git_ref,
        git_commit=git_commit,
        aws_region=aws_region,
        app_name=app_name,
        runner_instance_type=runner_instance_type,
        runner_root_volume_size_gb=runner_root_volume_size_gb,
        force_rebuild_ami=force_rebuild_ami,
    )
    config = core.Config(session=session, dry_run=True, **config_fields)
    job_id = request.app.state.job_manager.submit(
        lambda: core.provision(config),
        meta={
            "kind": "provision_plan",
            "domain": domain,
            "apply_action": "/deployments/new/apply",
            "config": config_fields,
        },
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/deployments/new/apply", response_class=HTMLResponse)
def new_deployment_apply(
    request: Request,
    session=Depends(require_session),
    domain_name: str = Form(...),
    certificate_arn: str = Form(""),
    git_repo_url: str = Form(...),
    git_ref: str = Form(...),
    git_commit: str = Form(...),
    aws_region: str = Form(...),
    app_name: str = Form(...),
    runner_instance_type: str = Form(...),
    runner_root_volume_size_gb: int = Form(...),
    force_rebuild_ami: bool = Form(False),
):
    config = core.Config(
        session=session,
        dry_run=False,
        domain_name=domain_name,
        certificate_arn=certificate_arn,
        git_repo_url=git_repo_url,
        git_ref=git_ref,
        git_commit=git_commit,
        aws_region=aws_region,
        app_name=app_name,
        runner_instance_type=runner_instance_type,
        runner_root_volume_size_gb=runner_root_volume_size_gb,
        force_rebuild_ami=force_rebuild_ami,
    )
    job_id = request.app.state.job_manager.submit(
        lambda: core.provision(config),
        meta={"kind": "provision_apply", "domain": domain_name},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.get("/deployments/{domain}", response_class=HTMLResponse)
def deployment_detail(request: Request, domain: str, _session=Depends(require_session)):
    deployment = find_deployment(request, domain)
    return templates.TemplateResponse(request, "deployment_detail.html", {"deployment": deployment, "error": None}
    )


@router.post("/deployments/{domain}/update/plan", response_class=HTMLResponse)
def update_plan(
    request: Request,
    domain: str,
    session=Depends(require_session),
    git_repo_url: str = Form(core.DEFAULT_GIT_REPO_URL),
    git_ref: str = Form("main"),
):
    deployment = find_deployment(request, domain)
    try:
        git_commit = github_api.resolve_git_commit_via_github(git_repo_url, git_ref)
    except DeployError as exc:
        return templates.TemplateResponse(request, "deployment_detail.html", {"deployment": deployment, "error": str(exc)},
        )

    config_fields = dict(
        domain_name=domain,
        certificate_arn="",
        git_repo_url=git_repo_url,
        git_ref=git_ref,
        git_commit=git_commit,
        aws_region=request.app.state.region,
        app_name="glow-core",
        runner_instance_type="",
        runner_root_volume_size_gb=0,
        force_rebuild_ami=False,
    )
    config = core.Config(session=session, dry_run=True, **config_fields)
    job_id = request.app.state.job_manager.submit(
        lambda: core.update(config),
        meta={
            "kind": "update_plan",
            "domain": domain,
            "apply_action": f"/deployments/{domain}/update/apply",
            "config": config_fields,
        },
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/deployments/{domain}/update/apply", response_class=HTMLResponse)
def update_apply(
    request: Request,
    domain: str,
    session=Depends(require_session),
    domain_name: str = Form(...),
    certificate_arn: str = Form(""),
    git_repo_url: str = Form(...),
    git_ref: str = Form(...),
    git_commit: str = Form(...),
    aws_region: str = Form(...),
    app_name: str = Form(...),
    runner_instance_type: str = Form(""),
    runner_root_volume_size_gb: int = Form(0),
    force_rebuild_ami: bool = Form(False),
):
    config = core.Config(
        session=session,
        dry_run=False,
        domain_name=domain_name,
        certificate_arn=certificate_arn,
        git_repo_url=git_repo_url,
        git_ref=git_ref,
        git_commit=git_commit,
        aws_region=aws_region,
        app_name=app_name,
        runner_instance_type=runner_instance_type,
        runner_root_volume_size_gb=runner_root_volume_size_gb,
        force_rebuild_ami=force_rebuild_ami,
    )
    job_id = request.app.state.job_manager.submit(
        lambda: core.update(config),
        meta={"kind": "update_apply", "domain": domain_name},
    )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)

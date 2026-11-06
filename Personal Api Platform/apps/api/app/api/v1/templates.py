from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import Server, Project, ProjectSource, Deployment, User
from apps.api.app.services.template_service import list_templates, get_template
from apps.api.app.services.job_service import create_and_dispatch_job
from apps.api.app.services.audit_service import log_activity

router = APIRouter(prefix="/templates", tags=["App Store & Templates"])

class DeployTemplateRequest(BaseModel):
    server_id: str
    template_id: str
    project_name: str
    port: Optional[int] = None
    environment_variables: Optional[Dict[str, str]] = None

@router.get("", response_model=List[Dict[str, Any]])
def get_all_templates(current_user: User = Depends(get_current_user)):
    """List curated homelab applications ready for 1-click deployment."""
    return list_templates()

@router.get("/{template_id}", response_model=Dict[str, Any])
def get_template_detail(template_id: str, current_user: User = Depends(get_current_user)):
    """Retrieve template details, default ports, and compose structure."""
    tmpl = get_template(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return tmpl

@router.post("/deploy")
async def deploy_template(
    payload: DeployTemplateRequest,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    """Deploy a homelab template into a running Docker stack on target server."""
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Target server not found")

    tmpl = get_template(payload.template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{payload.template_id}' not found")

    # Prepare environment variables
    env_vars = dict(tmpl.get("environment_variables", {}))
    if payload.environment_variables:
        env_vars.update(payload.environment_variables)

    sanitized_name = payload.project_name.strip().lower().replace(" ", "-")
    env_vars["CONTAINER_NAME"] = sanitized_name
    if payload.port:
        env_vars["HOST_PORT"] = str(payload.port)
    elif "default_port" in tmpl and tmpl["default_port"] > 0:
        env_vars["HOST_PORT"] = str(tmpl["default_port"])

    # Create new Project entity
    project = Project(
        name=payload.project_name,
        server_id=server.id,
        owner_id=current_user.id,
        source_type="compose",
        framework="docker",
        status="active"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    source = ProjectSource(
        project_id=project.id,
        compose_path="docker-compose.yml"
    )
    db.add(source)

    # Create Deployment record
    deployment = Deployment(
        project_id=project.id,
        version=1,
        status="building",
        commit_hash="template-init",
        triggered_by=current_user.id
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Dispatch job to agent
    job_payload = {
        "project_id": project.id,
        "project_name": sanitized_name,
        "deployment_id": deployment.id,
        "compose_content": tmpl["compose_yaml"],
        "environment_variables": env_vars
    }

    job = await create_and_dispatch_job(
        db=db,
        server_id=server.id,
        job_type="deployment.compose",
        payload=job_payload
    )

    log_activity(
        db,
        action="template.deploy",
        resource_type="project",
        resource_id=project.id,
        user_id=current_user.id,
        details={
            "template_id": payload.template_id,
            "project_name": payload.project_name,
            "server_id": server.id,
            "job_id": job.id
        }
    )

    return {
        "status": "dispatched",
        "message": f"Template '{tmpl['name']}' deployment started on '{server.name}'",
        "project_id": project.id,
        "deployment_id": deployment.id,
        "job_id": job.id
    }

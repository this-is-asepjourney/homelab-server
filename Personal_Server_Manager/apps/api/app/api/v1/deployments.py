import os
import secrets
import shutil
import zipfile
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.config import settings
from apps.api.app.core.security import encrypt_secret, decrypt_secret
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import (
    Project,
    EnvironmentVariable,
    Deployment,
    DeploymentLog,
    Server,
    Job,
    User,
)
from apps.api.app.schemas.all_schemas import (
    DeploymentCreateGit,
    DeploymentCreateCompose,
    DeploymentResponse,
    DeploymentLogResponse,
)
from apps.api.app.services.audit_service import log_activity
from apps.api.app.services.job_service import create_and_dispatch_job
from apps.api.app.services.db_provision_service import provision_and_sync_project_db

router = APIRouter(prefix="/deployments", tags=["Deployment Center"])

def get_next_version(db: Session, project_id: str) -> int:
    last = db.query(Deployment).filter(
        Deployment.project_id == project_id
    ).order_by(Deployment.version.desc()).first()
    return (last.version + 1) if last else 1

@router.get("", response_model=List[DeploymentResponse])
def list_deployments(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    deployments = db.query(Deployment).order_by(Deployment.created_at.desc()).limit(limit).all()
    result = []
    for d in deployments:
        result.append(
            DeploymentResponse(
                id=d.id,
                project_id=d.project_id,
                project_name=d.project.name if d.project else "Unknown Project",
                version=d.version,
                commit_hash=d.commit_hash,
                image_tag=d.image_tag,
                status=d.status,
                triggered_by=d.triggered_by,
                started_at=d.started_at,
                finished_at=d.finished_at,
                duration_seconds=d.duration_seconds,
                created_at=d.created_at,
            )
        )
    return result

@router.post("/git", response_model=DeploymentResponse)
async def create_git_deployment(
    payload: DeploymentCreateGit,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    src = project.source
    if not src or not src.repository_url:
        raise HTTPException(status_code=400, detail="Project does not have a Git repository configured")

    # Update port_mappings and env vars if provided in deploy payload
    if payload.port_mappings:
        project.port_mappings = payload.port_mappings.strip()

    if payload.environment_variables:
        for item in payload.environment_variables:
            if item.key and item.key.strip():
                existing = db.query(EnvironmentVariable).filter(
                    EnvironmentVariable.project_id == project.id,
                    EnvironmentVariable.key == item.key.strip()
                ).first()
                if existing:
                    existing.encrypted_value = encrypt_secret(item.value)
                else:
                    db.add(EnvironmentVariable(
                        project_id=project.id,
                        key=item.key.strip(),
                        encrypted_value=encrypt_secret(item.value)
                    ))
        db.commit()

    version = get_next_version(db, project.id)
    image_tag = f"{project.name.lower().replace(' ', '-')}:v{version}"

    now = datetime.now(timezone.utc)
    deployment = Deployment(
        project_id=project.id,
        version=version,
        commit_hash=payload.commit_hash or "HEAD",
        image_tag=image_tag,
        status="preparing",
        triggered_by=current_user.id,
        started_at=now
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    # Initial deployment log
    initial_log = DeploymentLog(
        deployment_id=deployment.id,
        sequence=1,
        level="info",
        message=f"Deployment v{version} triggered via Git ({src.repository_url} @ {payload.branch or src.branch})"
    )
    db.add(initial_log)
    db.commit()

    # Auto-provision & auto-connect PostgreSQL database for the project
    db_info, env_vars = provision_and_sync_project_db(db, project)

    db_log_msg = (
        f"[PostgreSQL] Database '{db_info.get('db_name')}' did not exist — automatically created on {db_info.get('host')}:{db_info.get('port')} and linked to project."
        if db_info.get("created")
        else f"[PostgreSQL] Auto-connected project to database '{db_info.get('db_name')}' ({db_info.get('host')}:{db_info.get('port')})."
    )
    db.add(
        DeploymentLog(
            deployment_id=deployment.id,
            sequence=2,
            level="info",
            message=db_log_msg,
        )
    )
    db.commit()

    # Dispatch job to target server agent
    job_payload = {
        "deployment_id": deployment.id,
        "project_id": project.id,
        "project_name": project.name,
        "repository_url": src.repository_url,
        "branch": payload.branch or src.branch or "main",
        "commit_hash": payload.commit_hash,
        "dockerfile_path": src.dockerfile_path or "Dockerfile",
        "compose_path": src.compose_path or "docker-compose.yml",
        "port_mappings": project.port_mappings or "3000:3000",
        "image_tag": image_tag,
        "version": version,
        "environment_variables": env_vars,
        "database_config": db_info,
    }

    job = await create_and_dispatch_job(
        db=db,
        server_id=project.server_id,
        job_type="deployment.git",
        payload=job_payload,
        deployment_id=deployment.id,
        priority=20
    )

    deployment.status = "building"
    db.commit()

    log_activity(
        db,
        action="deployment.git_trigger",
        resource_type="deployment",
        resource_id=deployment.id,
        user_id=current_user.id,
        details={"project": project.name, "version": version, "job_id": job.id}
    )

    return DeploymentResponse(
        id=deployment.id,
        project_id=project.id,
        project_name=project.name,
        version=version,
        commit_hash=deployment.commit_hash,
        image_tag=deployment.image_tag,
        status=deployment.status,
        triggered_by=current_user.id,
        started_at=deployment.started_at,
        finished_at=None,
        duration_seconds=0,
        created_at=deployment.created_at,
    )

@router.post("/upload-sessions")
def create_upload_session(
    project_id: str,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id = f"upload_{secrets.token_hex(16)}"
    return {
        "upload_session_id": session_id,
        "project_id": project_id,
        "max_file_size_mb": 100,
        "allowed_formats": [".zip"]
    }

@router.post("/{project_id}/finalize-upload", response_model=DeploymentResponse)
async def finalize_zip_upload(
    project_id: str,
    file: UploadFile = File(...),
    port_mappings: Optional[str] = Form(None),
    env_vars_json: Optional[str] = Form(None),
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    # Update port mappings if provided with upload
    if port_mappings:
        project.port_mappings = port_mappings.strip()

    # Update environment variables if provided
    if env_vars_json:
        try:
            import json
            parsed = json.loads(env_vars_json)
            if isinstance(parsed, list):
                for item in parsed:
                    k = item.get("key", "").strip()
                    v = item.get("value", "")
                    if k:
                        existing = db.query(EnvironmentVariable).filter(
                            EnvironmentVariable.project_id == project.id,
                            EnvironmentVariable.key == k
                        ).first()
                        if existing:
                            existing.encrypted_value = encrypt_secret(v)
                        else:
                            db.add(EnvironmentVariable(project_id=project.id, key=k, encrypted_value=encrypt_secret(v)))
            elif isinstance(parsed, dict):
                for k, v in parsed.items():
                    k_str = str(k).strip()
                    if k_str:
                        existing = db.query(EnvironmentVariable).filter(
                            EnvironmentVariable.project_id == project.id,
                            EnvironmentVariable.key == k_str
                        ).first()
                        if existing:
                            existing.encrypted_value = encrypt_secret(str(v))
                        else:
                            db.add(EnvironmentVariable(project_id=project.id, key=k_str, encrypted_value=encrypt_secret(str(v))))
            db.commit()
        except Exception:
            pass

    # Save uploaded file
    target_filename = f"{project.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    target_path = os.path.join(settings.UPLOAD_DIR, target_filename)

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Basic ZIP security inspection (Zip Slip / Path traversal check)
    try:
        with zipfile.ZipFile(target_path, "r") as z:
            for zip_info in z.infolist():
                if ".." in zip_info.filename or zip_info.filename.startswith("/"):
                    os.remove(target_path)
                    raise HTTPException(status_code=400, detail="Malicious ZIP: Path traversal detected")
    except zipfile.BadZipFile:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise HTTPException(status_code=400, detail="Corrupted or invalid ZIP file")

    version = get_next_version(db, project.id)
    image_tag = f"{project.name.lower().replace(' ', '-')}:v{version}"
    now = datetime.now(timezone.utc)

    deployment = Deployment(
        project_id=project.id,
        version=version,
        image_tag=image_tag,
        status="building",
        triggered_by=current_user.id,
        started_at=now
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    initial_log = DeploymentLog(
        deployment_id=deployment.id,
        sequence=1,
        level="info",
        message=f"Deployment v{version} triggered via ZIP upload ({file.filename})"
    )
    db.add(initial_log)
    db.commit()

    # Auto-provision & auto-connect PostgreSQL database for ZIP deployment
    db_info, env_vars = provision_and_sync_project_db(db, project)

    job_payload = {
        "deployment_id": deployment.id,
        "project_id": project.id,
        "project_name": project.name,
        "zip_path": target_path,
        "image_tag": image_tag,
        "version": version,
        "dockerfile_path": project.source.dockerfile_path if project.source else "Dockerfile",
        "compose_path": project.source.compose_path if project.source else "docker-compose.yml",
        "port_mappings": project.port_mappings or "3000:3000",
        "environment_variables": env_vars,
        "database_config": db_info,
    }

    job = await create_and_dispatch_job(
        db=db,
        server_id=project.server_id,
        job_type="deployment.zip",
        payload=job_payload,
        deployment_id=deployment.id,
        priority=20
    )

    log_activity(
        db,
        action="deployment.zip_trigger",
        resource_type="deployment",
        resource_id=deployment.id,
        user_id=current_user.id,
        details={"project": project.name, "version": version, "job_id": job.id}
    )

    return DeploymentResponse(
        id=deployment.id,
        project_id=project.id,
        project_name=project.name,
        version=version,
        commit_hash=None,
        image_tag=deployment.image_tag,
        status=deployment.status,
        triggered_by=current_user.id,
        started_at=deployment.started_at,
        finished_at=None,
        duration_seconds=0,
        created_at=deployment.created_at,
    )

@router.post("/webhook/{project_id}")
async def github_webhook_trigger(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Automated deployment trigger from GitHub or GitLab webhooks."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    src = project.source
    if not src or not src.repository_url:
        raise HTTPException(status_code=400, detail="Project has no Git repository configured")

    payload = {}
    try:
        payload = await request.json()
    except Exception:
        pass

    # Extract branch and commit from GitHub push payload
    ref = payload.get("ref", "")
    pushed_branch = ref.split("/")[-1] if "/" in ref else (src.branch or "main")
    commit_hash = payload.get("after") or (payload.get("head_commit", {}) or {}).get("id") or "HEAD"

    # Only deploy if matching configured branch (default to main)
    target_branch = src.branch or "main"
    if pushed_branch and pushed_branch != target_branch:
        return {
            "status": "ignored",
            "reason": f"Push event on branch '{pushed_branch}' does not match tracking branch '{target_branch}'"
        }

    version = get_next_version(db, project.id)
    image_tag = f"{project.name.lower().replace(' ', '-')}:v{version}"
    now = datetime.now(timezone.utc)

    deployment = Deployment(
        project_id=project.id,
        version=version,
        commit_hash=commit_hash[:8] if len(commit_hash) >= 8 else commit_hash,
        image_tag=image_tag,
        status="building",
        triggered_by=project.owner_id,
        started_at=now
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    initial_log = DeploymentLog(
        deployment_id=deployment.id,
        sequence=1,
        level="info",
        message=f"[Webhook] Auto-deploy v{version} triggered by GitHub push on '{pushed_branch}' ({commit_hash[:7]})"
    )
    db.add(initial_log)
    db.commit()

    # Auto-provision & auto-connect PostgreSQL database for webhook deployment
    db_info, env_vars = provision_and_sync_project_db(db, project)

    job_payload = {
        "deployment_id": deployment.id,
        "project_id": project.id,
        "project_name": project.name,
        "repository_url": src.repository_url,
        "branch": pushed_branch,
        "commit_hash": commit_hash,
        "dockerfile_path": src.dockerfile_path or "Dockerfile",
        "compose_path": src.compose_path or "docker-compose.yml",
        "port_mappings": project.port_mappings or "3000:3000",
        "image_tag": image_tag,
        "version": version,
        "environment_variables": env_vars,
        "database_config": db_info,
    }

    job = await create_and_dispatch_job(
        db=db,
        server_id=project.server_id,
        job_type="deployment.git",
        payload=job_payload,
        deployment_id=deployment.id,
        priority=20
    )

    log_activity(
        db,
        action="deployment.webhook_trigger",
        resource_type="deployment",
        resource_id=deployment.id,
        user_id=project.owner_id,
        details={"project": project.name, "version": version, "branch": pushed_branch, "job_id": job.id}
    )

    return {
        "status": "triggered",
        "message": f"Deployment v{version} started for {project.name}",
        "deployment_id": deployment.id,
        "version": version,
        "job_id": job.id
    }

@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    d = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return DeploymentResponse(
        id=d.id,
        project_id=d.project_id,
        project_name=d.project.name if d.project else "Unknown Project",
        version=d.version,
        commit_hash=d.commit_hash,
        image_tag=d.image_tag,
        status=d.status,
        triggered_by=d.triggered_by,
        started_at=d.started_at,
        finished_at=d.finished_at,
        duration_seconds=d.duration_seconds,
        created_at=d.created_at,
    )

@router.post("/{deployment_id}/cancel")
def cancel_deployment(
    deployment_id: str,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    d = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if d.status in ["success", "failed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Deployment has already finished")

    d.status = "cancelled"
    d.finished_at = datetime.now(timezone.utc)
    db.commit()

    log_activity(
        db,
        action="deployment.cancel",
        resource_type="deployment",
        resource_id=deployment_id,
        user_id=current_user.id
    )
    return {"message": "Deployment cancelled"}

@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(
    deployment_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    target_deploy = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not target_deploy:
        raise HTTPException(status_code=404, detail="Target deployment to rollback to not found")

    if not target_deploy.image_tag:
        raise HTTPException(status_code=400, detail="Target release does not have a valid image tag to restore")

    project = target_deploy.project
    new_version = get_next_version(db, project.id)

    now = datetime.now(timezone.utc)
    rollback_deploy = Deployment(
        project_id=project.id,
        version=new_version,
        image_tag=target_deploy.image_tag,
        status="rolling_back",
        triggered_by=current_user.id,
        started_at=now
    )
    db.add(rollback_deploy)
    db.commit()
    db.refresh(rollback_deploy)

    initial_log = DeploymentLog(
        deployment_id=rollback_deploy.id,
        sequence=1,
        level="warning",
        message=f"Rolling back project to release v{target_deploy.version} (image: {target_deploy.image_tag})"
    )
    db.add(initial_log)
    db.commit()

    # Dispatch rollback job
    job_payload = {
        "deployment_id": rollback_deploy.id,
        "project_id": project.id,
        "project_name": project.name,
        "target_image_tag": target_deploy.image_tag,
        "rollback_from_version": target_deploy.version
    }

    job = await create_and_dispatch_job(
        db=db,
        server_id=project.server_id,
        job_type="deployment.rollback",
        payload=job_payload,
        deployment_id=rollback_deploy.id,
        priority=25
    )

    log_activity(
        db,
        action="deployment.rollback",
        resource_type="deployment",
        resource_id=rollback_deploy.id,
        user_id=current_user.id,
        details={"restored_version": target_deploy.version}
    )

    return DeploymentResponse(
        id=rollback_deploy.id,
        project_id=project.id,
        project_name=project.name,
        version=new_version,
        commit_hash=target_deploy.commit_hash,
        image_tag=rollback_deploy.image_tag,
        status=rollback_deploy.status,
        triggered_by=current_user.id,
        started_at=rollback_deploy.started_at,
        finished_at=None,
        duration_seconds=0,
        created_at=rollback_deploy.created_at,
    )

@router.get("/{deployment_id}/logs", response_model=List[DeploymentLogResponse])
def get_deployment_logs(
    deployment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(DeploymentLog).filter(
        DeploymentLog.deployment_id == deployment_id
    ).order_by(DeploymentLog.sequence.asc()).all()
    return logs


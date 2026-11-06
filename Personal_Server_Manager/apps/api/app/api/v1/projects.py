from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.security import encrypt_secret, decrypt_secret
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import (
    Project,
    ProjectSource,
    EnvironmentVariable,
    Server,
    Deployment,
    DeploymentLog,
    Container,
    User,
)
from apps.api.app.schemas.all_schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectDatabaseProvisionRequest,
    EnvironmentUpdateRequest,
    EnvironmentItemResponse,
    DeploymentResponse,
    ContainerResponse,
)
from apps.api.app.services.audit_service import log_activity
from apps.api.app.services.pap_client import sync_psm_to_pap
from apps.api.app.services.job_service import create_and_dispatch_job
from apps.api.app.services.db_provision_service import (
    provision_and_sync_project_db,
    resolve_project_db_name,
    ensure_postgres_database,
    build_postgres_env_vars,
    list_all_postgres_databases,
)

router = APIRouter(prefix="/projects", tags=["Project Management"])

def mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 4:
        return "****"
    return val[:2] + "****" + val[-2:]

@router.get("", response_model=List[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    result = []
    for p in projects:
        src = p.source
        result.append(
            ProjectResponse(
                id=p.id,
                server_id=p.server_id,
                server_name=p.server.name if p.server else "Unknown Server",
                owner_id=p.owner_id,
                name=p.name,
                description=p.description,
                framework=p.framework,
                source_type=p.source_type,
                status=p.status,
                repository_url=src.repository_url if src else None,
                branch=src.branch if src else None,
                dockerfile_path=src.dockerfile_path if src else None,
                compose_path=src.compose_path if src else None,
                port_mappings=p.port_mappings or "3000:3000",
                created_at=p.created_at
            )
        )
    return result

@router.post("", response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Target server not found")

    project = Project(
        server_id=payload.server_id,
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        framework=payload.framework,
        source_type=payload.source_type,
        port_mappings=payload.port_mappings or "3000:3000",
        status="active"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Create project source config
    source = ProjectSource(
        project_id=project.id,
        repository_url=payload.repository_url,
        branch=payload.branch or "main",
        dockerfile_path=payload.dockerfile_path or "Dockerfile",
        compose_path=payload.compose_path or "docker-compose.yml"
    )
    db.add(source)
    db.commit()

    # Save initial environment variables if provided
    if payload.environment_variables:
        for item in payload.environment_variables:
            if item.key and item.key.strip():
                encrypted = encrypt_secret(item.value or "")
                db_var = EnvironmentVariable(
                    project_id=project.id,
                    key=item.key.strip(),
                    encrypted_value=encrypted
                )
                db.add(db_var)
        db.commit()

    # Auto-provision & auto-connect PostgreSQL database for the project
    db_info = {}
    if getattr(payload, "auto_provision_db", True):
        try:
            db_info, _ = provision_and_sync_project_db(
                db=db,
                project=project,
                custom_db_name=getattr(payload, "database_name", None),
                override_existing_env=True,
            )
        except Exception:
            pass

    # Optional immediate deployment for Git projects
    deployment_id = None
    if payload.source_type == "git" and payload.repository_url and getattr(payload, "auto_deploy", True):
        try:
            version = 1
            image_tag = f"{project.name.lower().replace(' ', '-')}:v{version}"
            now = datetime.now(timezone.utc)
            deployment = Deployment(
                project_id=project.id,
                version=version,
                commit_hash="HEAD",
                image_tag=image_tag,
                status="building",
                triggered_by=current_user.id,
                started_at=now
            )
            db.add(deployment)
            db.commit()
            db.refresh(deployment)
            deployment_id = deployment.id

            db.add(
                DeploymentLog(
                    deployment_id=deployment.id,
                    sequence=1,
                    level="info",
                    message=f"Deployment v1 dimulai otomatis via Git ({source.repository_url} @ {source.branch})"
                )
            )
            db.commit()

            # Retrieve all stored decrypted environment variables
            env_items = db.query(EnvironmentVariable).filter(EnvironmentVariable.project_id == project.id).all()
            full_env = {}
            for item in env_items:
                try:
                    full_env[item.key] = decrypt_secret(item.encrypted_value)
                except Exception:
                    pass

            job_payload = {
                "deployment_id": deployment.id,
                "project_id": project.id,
                "project_name": project.name,
                "repository_url": source.repository_url,
                "branch": source.branch or "main",
                "commit_hash": None,
                "dockerfile_path": source.dockerfile_path or "Dockerfile",
                "compose_path": source.compose_path or "docker-compose.yml",
                "port_mappings": project.port_mappings or "3000:3000",
                "image_tag": image_tag,
                "version": version,
                "environment_variables": full_env,
                "database_config": db_info,
            }

            await create_and_dispatch_job(
                db=db,
                server_id=project.server_id,
                job_type="deployment.git",
                payload=job_payload,
                deployment_id=deployment.id,
                priority=20
            )
        except Exception:
            pass

    log_activity(
        db,
        action="project.create",
        resource_type="project",
        resource_id=project.id,
        user_id=current_user.id,
        details={
            "name": project.name,
            "source_type": project.source_type,
            "port_mappings": project.port_mappings,
            "database": db_info.get("db_name"),
            "db_auto_created": db_info.get("created", False),
            "auto_deployed": deployment_id is not None,
            "pap_synced": bool(sync_psm_to_pap(db)),
        }
    )

    return ProjectResponse(
        id=project.id,
        server_id=project.server_id,
        server_name=server.name,
        owner_id=project.owner_id,
        name=project.name,
        description=project.description,
        framework=project.framework,
        source_type=project.source_type,
        status=project.status,
        repository_url=source.repository_url,
        branch=source.branch,
        dockerfile_path=source.dockerfile_path,
        compose_path=source.compose_path,
        port_mappings=project.port_mappings or "3000:3000",
        deployment_id=deployment_id,
        created_at=project.created_at
    )

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    src = p.source
    return ProjectResponse(
        id=p.id,
        server_id=p.server_id,
        server_name=p.server.name if p.server else "Unknown Server",
        owner_id=p.owner_id,
        name=p.name,
        description=p.description,
        framework=p.framework,
        source_type=p.source_type,
        status=p.status,
        repository_url=src.repository_url if src else None,
        branch=src.branch if src else None,
        dockerfile_path=src.dockerfile_path if src else None,
        compose_path=src.compose_path if src else None,
        port_mappings=p.port_mappings or "3000:3000",
        created_at=p.created_at
    )

@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.name is not None:
        p.name = payload.name
    if payload.description is not None:
        p.description = payload.description
    if payload.framework is not None:
        p.framework = payload.framework
    if payload.port_mappings is not None:
        p.port_mappings = payload.port_mappings

    src = p.source
    if src:
        if payload.repository_url is not None:
            src.repository_url = payload.repository_url
        if payload.branch is not None:
            src.branch = payload.branch
        if payload.dockerfile_path is not None:
            src.dockerfile_path = payload.dockerfile_path
        if payload.compose_path is not None:
            src.compose_path = payload.compose_path

    db.commit()
    db.refresh(p)

    log_activity(
        db,
        action="project.update",
        resource_type="project",
        resource_id=p.id,
        user_id=current_user.id
    )
    return get_project(project_id=project_id, current_user=current_user, db=db)

@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(p)
    db.commit()

    log_activity(
        db,
        action="project.delete",
        resource_type="project",
        resource_id=project_id,
        user_id=current_user.id
    )
    return {"message": "Project deleted successfully"}

@router.get("/{project_id}/environment", response_model=List[EnvironmentItemResponse])
def get_project_environment(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    items = db.query(EnvironmentVariable).filter(EnvironmentVariable.project_id == project_id).all()
    results = []
    for item in items:
        # Decrypt to mask securely
        try:
            val = decrypt_secret(item.encrypted_value)
            masked = mask_secret(val)
        except Exception:
            masked = "********"
        results.append(
            EnvironmentItemResponse(
                key=item.key,
                masked_value=masked,
                updated_at=item.updated_at
            )
        )
    return results

@router.put("/{project_id}/environment")
def update_project_environment(
    project_id: str,
    payload: EnvironmentUpdateRequest,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Replace variables with encrypted values
    db.query(EnvironmentVariable).filter(EnvironmentVariable.project_id == project_id).delete()

    for item in payload.variables:
        encrypted = encrypt_secret(item.value)
        db_var = EnvironmentVariable(
            project_id=project_id,
            key=item.key.strip(),
            encrypted_value=encrypted
        )
        db.add(db_var)

    db.commit()

    log_activity(
        db,
        action="project.environment_update",
        resource_type="project",
        resource_id=project_id,
        user_id=current_user.id,
        details={"keys_updated": [i.key for i in payload.variables]}
    )
    return {"message": "Environment variables encrypted and updated"}

@router.get("/{project_id}/deployments", response_model=List[DeploymentResponse])
def get_project_deployments(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    deployments = db.query(Deployment).filter(
        Deployment.project_id == project_id
    ).order_by(Deployment.created_at.desc()).all()
    return deployments


@router.get("/databases/list")
def get_all_postgres_databases(
    current_user: User = Depends(get_current_user),
):
    """List all databases present on the PostgreSQL server."""
    return {"databases": list_all_postgres_databases()}


@router.get("/{project_id}/database")
def get_project_database_info(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inspect the PostgreSQL database bound to this project (auto-creating if missing)."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    db_name = resolve_project_db_name(p)
    db_info = ensure_postgres_database(db_name)
    pg_env = build_postgres_env_vars(db_info)

    # Mask password in returned env preview for UI safety while providing full info
    masked_pass = mask_secret(db_info.get("password", ""))
    return {
        **db_info,
        "masked_password": masked_pass,
        "masked_connection_url_internal": f"postgresql://{db_info['user']}:{masked_pass}@{db_info['host']}:{db_info['port']}/{db_info['db_name']}",
        "masked_connection_url_external": f"postgresql://{db_info['user']}:{masked_pass}@{db_info['external_host']}:{db_info['port']}/{db_info['db_name']}",
        "env_preview": {
            k: (mask_secret(v) if "PASS" in k or "URL" in k or "URI" in k else v)
            for k, v in pg_env.items()
        },
        "env_full": pg_env,
    }


@router.post("/{project_id}/database/provision")
def provision_project_database_endpoint(
    project_id: str,
    payload: Optional[ProjectDatabaseProvisionRequest] = None,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db),
):
    """Ensure the project's PostgreSQL database exists and inject/sync connection environment variables."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    custom_db = payload.db_name if payload else None
    override = payload.override_env if payload else True

    db_info, merged_env = provision_and_sync_project_db(
        db=db,
        project=p,
        custom_db_name=custom_db,
        override_existing_env=override,
    )

    log_activity(
        db,
        action="project.database_provision",
        resource_type="project",
        resource_id=project_id,
        user_id=current_user.id,
        details={
            "project": p.name,
            "db_name": db_info.get("db_name"),
            "created": db_info.get("created"),
            "host": db_info.get("host"),
        },
    )

    masked_pass = mask_secret(db_info.get("password", ""))
    return {
        **db_info,
        "masked_password": masked_pass,
        "synced_env_keys": list(merged_env.keys()),
    }



import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple
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
    DockerfileGenerateRequest,
    DockerfileUpdateRequest,
    EnvironmentUpdateRequest,
    EnvironmentItemResponse,
    DeploymentResponse,
    ContainerResponse,
)
from apps.api.app.services.audit_service import log_activity
from apps.api.app.services.pap_client import sync_psm_to_pap
from apps.api.app.services.job_service import create_and_dispatch_job
from apps.api.app.services.github_service import get_stored_token
from apps.api.app.services.db_provision_service import (
    provision_and_sync_project_db,
    resolve_project_db_name,
    ensure_postgres_database,
    build_postgres_env_vars,
    ensure_mysql_database,
    build_mysql_env_vars,
    build_sqlite_env_vars,
    list_all_postgres_databases,
)

router = APIRouter(prefix="/projects", tags=["Project Management"])

def mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 4:
        return "****"
    return val[:2] + "****" + val[-2:]

def sanitize_git_url_and_branch(repo_url: Optional[str], branch: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not repo_url:
        return repo_url, branch
    clean_url = repo_url.strip()
    clean_branch = (branch or "").strip()
    if "/tree/" in clean_url:
        parts = clean_url.split("/tree/", 1)
        clean_url = parts[0].rstrip("/")
        extracted_branch = parts[1].strip("/").split("/")[0]
        if extracted_branch and (not clean_branch or clean_branch in ("main", "master")):
            clean_branch = extracted_branch
    if clean_url and not clean_url.endswith(".git") and "github.com" in clean_url:
        clean_url = clean_url.rstrip("/") + ".git"
    return clean_url, (clean_branch or "main")

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
                domain=p.domain,
                db_type=p.db_type or "none",
                db_name=p.db_name,
                created_at=p.created_at
            )
        )
    return result

@router.get("/next-port")
def get_next_available_port(
    db: Session = Depends(get_db)
):
    """Detects active and reserved ports in the homelab and returns a safe, unallocated host port."""
    import socket

    # Homelab core system reserved ports
    reserved_ports = {
        53: "CoreDNS (:53)",
        80: "Nginx Ingress Router (:80)",
        1883: "Mosquitto MQTT (:1883)",
        3000: "PSM Web Internal (:3000)",
        3001: "Grafana Utama (:3001)",
        3002: "Uptime Kuma (:3002)",
        3005: "PSM Console Web (:3005)",
        3306: "MySQL Server (:3306)",
        5001: "Homelab Registry (:5001)",
        5432: "PostgreSQL Server (:5432)",
        8000: "PAP Core API Gateway (:8000)",
        8001: "PAP Core Web UI (:8001)",
        8080: "Vaultwarden (:8080)",
        8081: "Apache Web (:8081)",
        8086: "InfluxDB TSDB (:8086)",
        8088: "HeatpressHub Web (:8088)",
        9001: "Prometheus Server (:9001)",
        9090: "Cockpit Console (:9090)",
    }

    # Query all ports currently mapped in projects database
    projects = db.query(Project).all()
    for p in projects:
        if p.port_mappings:
            for entry in p.port_mappings.split(","):
                if ":" in entry:
                    try:
                        hp = int(entry.split(":")[0].strip())
                        reserved_ports[hp] = f"Project: {p.name} (Port {hp})"
                    except Exception:
                        pass

    # Find the next free port starting from 3100
    candidate = 3100
    while candidate < 65535:
        if candidate not in reserved_ports:
            # Also test socket bind to ensure nothing outside docker is using it
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.08)
            try:
                result = sock.connect_ex(("127.0.0.1", candidate))
                if result != 0:  # Not listening, port is free
                    break
            except Exception:
                break
            finally:
                sock.close()
        candidate += 1

    return {
        "success": True,
        "recommended_host_port": candidate,
        "reserved_ports": reserved_ports,
    }


@router.post("", response_model=ProjectResponse)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    server = db.query(Server).filter(Server.id == payload.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Target server not found")

    import re
    clean_slug = re.sub(r"[^a-zA-Z0-9-]", "-", payload.name.lower().strip()).strip("-")
    project_domain = payload.domain.strip().lower() if payload.domain else f"{clean_slug}.homelab"
    project_db_type = getattr(payload, "db_type", "postgres") or "none"

    project = Project(
        server_id=payload.server_id,
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        framework=payload.framework,
        source_type=payload.source_type,
        port_mappings=payload.port_mappings or "3000:3000",
        domain=project_domain,
        db_type=project_db_type,
        db_name=getattr(payload, "database_name", None),
        status="active"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Create project source config
    sanitized_repo, sanitized_branch = sanitize_git_url_and_branch(payload.repository_url, payload.branch)
    source = ProjectSource(
        project_id=project.id,
        repository_url=sanitized_repo,
        branch=sanitized_branch or "main",
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

    # Auto-provision & auto-connect database for the project (respecting explicit db_type)
    db_info = {}
    if getattr(payload, "auto_provision_db", True):
        try:
            db_info, _ = provision_and_sync_project_db(
                db=db,
                project=project,
                custom_db_name=getattr(payload, "database_name", None),
                db_type=project.db_type,
                override_existing_env=True,
            )
        except Exception:
            pass

    # Register Local DNS & Ingress Routing
    if project.domain:
        try:
            from apps.api.app.services.pap_client import sync_domain_routing
            hp = 3000
            if project.port_mappings and ":" in project.port_mappings:
                try:
                    hp = int(project.port_mappings.split(":")[0].strip())
                except Exception:
                    hp = 3000
            sync_domain_routing(domain=project.domain, target_port=hp, project_name=project.name)
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
                "db_type": project.db_type,
                "environment_variables": full_env,
                "database_config": db_info,
                "git_token": get_stored_token(),
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
        domain=project.domain,
        db_type=project.db_type or "none",
        db_name=project.db_name,
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
        domain=p.domain,
        db_type=p.db_type or "none",
        db_name=p.db_name,
        created_at=p.created_at
    )

async def execute_project_redeploy(
    db: Session,
    project: Project,
    current_user_id: str
) -> DeploymentResponse:
    src = project.source
    if src and src.repository_url:
        s_url, s_branch = sanitize_git_url_and_branch(src.repository_url, src.branch)
        if s_url != src.repository_url or s_branch != src.branch:
            src.repository_url = s_url
            src.branch = s_branch
            db.commit()
            db.refresh(src)

    last_deployment = db.query(Deployment).filter(
        Deployment.project_id == project.id
    ).order_by(Deployment.version.desc()).first()
    version = (last_deployment.version + 1) if (last_deployment and last_deployment.version) else 1

    clean_proj_name = project.name.lower().replace(" ", "-")
    image_tag = f"{clean_proj_name}:v{version}"
    now = datetime.now(timezone.utc)

    deployment = Deployment(
        project_id=project.id,
        version=version,
        commit_hash="HEAD" if (src and src.repository_url) else None,
        image_tag=image_tag,
        status="building",
        triggered_by=current_user_id,
        started_at=now
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    source_desc = f"Git ({src.repository_url} @ {src.branch or 'main'})" if (src and src.repository_url) else "Server Archive"
    initial_log = DeploymentLog(
        deployment_id=deployment.id,
        sequence=1,
        level="info",
        message=f"Deployment v{version} triggered via Project Update / Redeploy to Server ({source_desc})"
    )
    db.add(initial_log)
    db.commit()

    # Auto-provision & auto-connect database respecting explicit db_type
    db_info, env_vars = provision_and_sync_project_db(
        db, project, custom_db_name=project.db_name, db_type=project.db_type, override_existing_env=True
    )

    # Collect all stored decrypted environment variables
    env_items = db.query(EnvironmentVariable).filter(EnvironmentVariable.project_id == project.id).all()
    full_env = dict(env_vars or {})
    for item in env_items:
        try:
            full_env[item.key] = decrypt_secret(item.encrypted_value)
        except Exception:
            pass

    # Build job payload depending on source type
    if src and src.repository_url:
        job_type = "deployment.git"
        job_payload = {
            "deployment_id": deployment.id,
            "project_id": project.id,
            "project_name": project.name,
            "framework": project.framework,
            "repository_url": src.repository_url,
            "branch": src.branch or "main",
            "commit_hash": None,
            "dockerfile_path": src.dockerfile_path or "Dockerfile",
            "compose_path": src.compose_path or "docker-compose.yml",
            "port_mappings": project.port_mappings or "3000:3000",
            "image_tag": image_tag,
            "version": version,
            "db_type": project.db_type,
            "environment_variables": full_env,
            "database_config": db_info,
            "git_token": get_stored_token(),
        }
    elif src and src.upload_object_key and os.path.exists(src.upload_object_key):
        job_type = "deployment.zip"
        job_payload = {
            "deployment_id": deployment.id,
            "project_id": project.id,
            "project_name": project.name,
            "framework": project.framework,
            "zip_path": src.upload_object_key,
            "image_tag": image_tag,
            "version": version,
            "dockerfile_path": src.dockerfile_path or "Dockerfile",
            "compose_path": src.compose_path or "docker-compose.yml",
            "port_mappings": project.port_mappings or "3000:3000",
            "db_type": project.db_type,
            "environment_variables": full_env,
            "database_config": db_info,
            "git_token": get_stored_token(),
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Project tidak memiliki repositori Git maupun file archive ZIP yang tersimpan di server. Silakan deploy rilis baru dengan Git atau upload file ZIP terlebih dahulu."
        )

    job = await create_and_dispatch_job(
        db=db,
        server_id=project.server_id,
        job_type=job_type,
        payload=job_payload,
        deployment_id=deployment.id,
        priority=20
    )

    log_activity(
        db,
        action="project.redeploy",
        resource_type="deployment",
        resource_id=deployment.id,
        user_id=current_user_id,
        details={"project": project.name, "version": version, "job_id": job.id, "job_type": job_type}
    )

    return DeploymentResponse(
        id=deployment.id,
        project_id=project.id,
        project_name=project.name,
        version=version,
        commit_hash=deployment.commit_hash,
        image_tag=deployment.image_tag,
        status=deployment.status,
        triggered_by=current_user_id,
        started_at=deployment.started_at,
        finished_at=None,
        duration_seconds=0,
        created_at=deployment.created_at,
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
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
    if payload.domain is not None:
        p.domain = payload.domain.strip().lower() if payload.domain else None
    if payload.db_type is not None:
        p.db_type = payload.db_type
        # Immediately re-provision and sync environment variables when database engine is updated
        try:
            from apps.api.app.services.db_provision_service import provision_and_sync_project_db
            provision_and_sync_project_db(
                db=db,
                project=p,
                custom_db_name=payload.db_name or p.db_name,
                db_type=p.db_type,
                override_existing_env=True
            )
        except Exception:
            pass
    if payload.db_name is not None:
        p.db_name = payload.db_name

    src = p.source
    if src:
        if payload.repository_url is not None or payload.branch is not None:
            raw_url = payload.repository_url if payload.repository_url is not None else src.repository_url
            raw_branch = payload.branch if payload.branch is not None else src.branch
            s_url, s_branch = sanitize_git_url_and_branch(raw_url, raw_branch)
            if payload.repository_url is not None:
                src.repository_url = s_url
            if payload.branch is not None or (s_branch and s_branch != raw_branch):
                src.branch = s_branch
        if payload.dockerfile_path is not None:
            src.dockerfile_path = payload.dockerfile_path
        if payload.compose_path is not None:
            src.compose_path = payload.compose_path

    db.commit()
    db.refresh(p)

    # Sync DNS & Ingress Routing if domain or ports changed
    if p.domain and (payload.port_mappings is not None or payload.domain is not None):
        try:
            from apps.api.app.services.pap_client import sync_domain_routing
            hp = 3000
            if p.port_mappings and ":" in p.port_mappings:
                try:
                    hp = int(p.port_mappings.split(":")[0].strip())
                except Exception:
                    hp = 3000
            sync_domain_routing(domain=p.domain, target_port=hp, project_name=p.name)
        except Exception:
            pass

    log_activity(
        db,
        action="project.update",
        resource_type="project",
        resource_id=p.id,
        user_id=current_user.id
    )

    deployment_id = None
    if payload.redeploy:
        try:
            dep = await execute_project_redeploy(db=db, project=p, current_user_id=current_user.id)
            deployment_id = dep.id
        except Exception:
            pass

    resp = get_project(project_id=project_id, current_user=current_user, db=db)
    if deployment_id:
        resp.deployment_id = deployment_id
    return resp


@router.post("/{project_id}/redeploy", response_model=DeploymentResponse)
async def redeploy_project(
    project_id: str,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    """
    Trigger immediate redeployment of project to the server container
    using current settings, database configuration, and environment variables.
    """
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await execute_project_redeploy(db=db, project=p, current_user_id=current_user.id)

@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    # Remove Local DNS & Ingress Routing
    if p.domain:
        try:
            # pyrefly: ignore[missing-import]
            from app.modules.dns.service import DnsService
            DnsService.remove_domain_route(p.domain)
        except Exception:
            pass

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
    """Inspect the database bound to this project (PostgreSQL, MySQL, or SQLite)."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    target_type = (p.db_type or "postgres").lower().strip()
    db_name = resolve_project_db_name(p)

    if target_type in ("mysql", "mariadb"):
        db_info = ensure_mysql_database(db_name)
        db_env = build_mysql_env_vars(db_info)
        masked_pass = mask_secret(db_info.get("password", ""))
        user = db_info.get("user", "appuser")
        host = db_info.get("host", "192.168.25.101")
        port = db_info.get("port", 3306)
        clean_db = db_info.get("db_name", db_name)
        conn_url_internal = f"mysql://{user}:{masked_pass}@{host}:{port}/{clean_db}"
        conn_url_external = f"mysql://{user}:{masked_pass}@{db_info.get('external_host', host)}:{port}/{clean_db}"
        raw_url = f"mysql://{user}:{db_info.get('password', '')}@{host}:{port}/{clean_db}"
    elif target_type == "sqlite":
        db_info, db_env = build_sqlite_env_vars(db_name)
        masked_pass = ""
        conn_url_internal = db_env.get("DATABASE_URL", f"sqlite:////data/{db_name}.db")
        conn_url_external = conn_url_internal
        raw_url = conn_url_internal
    elif target_type in ("none", "stateless"):
        db_info = {
            "db_type": "none",
            "db_name": None,
            "host": "N/A",
            "external_host": "N/A",
            "port": 0,
            "user": "N/A",
            "created": False,
            "connected": False,
            "tables": [],
            "tables_count": 0,
            "size_bytes": 0,
        }
        db_env = {}
        masked_pass = ""
        conn_url_internal = "none"
        conn_url_external = "none"
        raw_url = ""
    else:  # postgres default
        db_info = ensure_postgres_database(db_name)
        db_env = build_postgres_env_vars(db_info)
        masked_pass = mask_secret(db_info.get("password", ""))
        user = db_info.get("user", "appuser")
        host = db_info.get("host", "192.168.25.101")
        port = db_info.get("port", 5432)
        clean_db = db_info.get("db_name", db_name)
        conn_url_internal = f"postgresql://{user}:{masked_pass}@{host}:{port}/{clean_db}"
        conn_url_external = f"postgresql://{user}:{masked_pass}@{db_info.get('external_host', host)}:{port}/{clean_db}"
        raw_url = f"postgresql://{user}:{db_info.get('password', '')}@{host}:{port}/{clean_db}"

    return {
        **db_info,
        "masked_password": masked_pass,
        "masked_connection_url_internal": conn_url_internal,
        "masked_connection_url_external": conn_url_external,
        "connection_url_internal": raw_url,
        "env_preview": {
            k: (mask_secret(v) if "PASS" in k or "URL" in k or "URI" in k else v)
            for k, v in db_env.items()
        },
        "env_full": db_env,
    }


@router.post("/{project_id}/database/provision")
def provision_project_database_endpoint(
    project_id: str,
    payload: Optional[ProjectDatabaseProvisionRequest] = None,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db),
):
    """Ensure the project's database exists (PostgreSQL, MySQL, SQLite) and inject/sync connection environment variables."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    custom_db = payload.db_name if payload else None
    target_type = (payload.db_type if (payload and payload.db_type) else p.db_type) or "postgres"
    override = payload.override_env if payload else True

    db_info, merged_env = provision_and_sync_project_db(
        db=db,
        project=p,
        custom_db_name=custom_db,
        db_type=target_type,
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
            "db_type": target_type,
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


# ══════════════════════════════════════════════════════════════════════════════
# DOCKER CONTAINER RUNTIME & TERMINAL LOGS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/{project_id}/container")
def get_project_container_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve runtime status, health, and state of the Docker container for this project."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    from apps.api.app.services.docker_service import DockerEngineService

    matched = DockerEngineService.find_container_by_project(p.name, p.id)
    if not matched:
        return {
            "exists": False,
            "container_name": p.name,
            "status": "not_created",
            "state": "not_created",
            "running": False,
            "message": f"Container Docker untuk project '{p.name}' belum aktif atau belum di-deploy.",
        }

    cid = matched.get("full_id") or matched.get("docker_id") or matched.get("name")
    inspected = DockerEngineService.inspect_container(cid)

    return {
        "exists": True,
        "docker_id": matched.get("docker_id"),
        "full_id": matched.get("full_id"),
        "container_name": matched.get("name"),
        "image": matched.get("image"),
        "status": matched.get("status"),
        "state": inspected.get("state", matched.get("state", "unknown")),
        "running": inspected.get("running", "Up" in matched.get("status", "")),
        "restarting": inspected.get("restarting", False),
        "oom_killed": inspected.get("oom_killed", False),
        "exit_code": inspected.get("exit_code"),
        "error": inspected.get("error", ""),
        "started_at": inspected.get("started_at", ""),
        "finished_at": inspected.get("finished_at", ""),
        "ports": inspected.get("ports", matched.get("ports", {})),
        "ip_address": inspected.get("ip_address", ""),
    }


@router.get("/{project_id}/container/logs")
def get_project_container_logs(
    project_id: str,
    tail: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve live stdout & stderr terminal logs directly from the Docker container."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    from apps.api.app.services.docker_service import DockerEngineService

    matched = DockerEngineService.find_container_by_project(p.name, p.id)
    if not matched:
        return {
            "container_name": p.name,
            "exists": False,
            "status": "not_created",
            "state": "not_created",
            "logs": f"[PSM] Container '{p.name}' belum ditemukan di Docker daemon.\nKlik tombol 'Deploy Release' atau 'Deploy Latest' untuk membangun dan meluncurkan container aplikasi.",
        }

    cid = matched.get("full_id") or matched.get("docker_id") or matched.get("name")
    raw_logs = DockerEngineService.get_container_logs(cid, tail=tail)
    inspected = DockerEngineService.inspect_container(cid)

    return {
        "container_name": matched.get("name"),
        "docker_id": matched.get("docker_id"),
        "exists": True,
        "status": matched.get("status"),
        "state": inspected.get("state", matched.get("state", "unknown")),
        "running": inspected.get("running", "Up" in matched.get("status", "")),
        "exit_code": inspected.get("exit_code"),
        "error": inspected.get("error", ""),
        "logs": raw_logs,
    }


@router.post("/{project_id}/container/restart")
def restart_project_container_endpoint(
    project_id: str,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db),
):
    """Restart the Docker container for this project."""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    from apps.api.app.services.docker_service import DockerEngineService

    matched = DockerEngineService.find_container_by_project(p.name, p.id)
    if not matched:
        raise HTTPException(status_code=404, detail=f"Container untuk '{p.name}' belum dibuat.")

    cid = matched.get("full_id") or matched.get("docker_id") or matched.get("name")
    success = DockerEngineService.restart_container(cid)

    log_activity(
        db,
        action="project.container_restart",
        resource_type="project",
        resource_id=project_id,
        user_id=current_user.id,
        details={"project": p.name, "container": matched.get("name"), "success": success},
    )

    if not success:
        raise HTTPException(status_code=500, detail="Gagal me-restart container.")

    return {
        "success": True,
        "message": f"Container '{matched.get('name')}' berhasil di-restart.",
    }


def _resolve_project_workspace_dir(project_id: str) -> str:
    import os
    from apps.api.app.core.config import settings

    candidates = [
        os.path.join(settings.STORAGE_BASE_DIR, "psm", "workspaces", project_id),
        os.path.join("./storage/psm/workspaces", project_id),
        os.path.join("./storage/workspaces", project_id),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


@router.get("/dockerfile/templates")
def get_dockerfile_templates_endpoint():
    """List all available professional multi-stage Dockerfile templates."""
    from apps.agent.app.deployment.dockerfile_generator import get_available_templates
    return {
        "success": True,
        "templates": get_available_templates(),
    }


@router.post("/dockerfile/generate")
def generate_dockerfile_preview_endpoint(payload: DockerfileGenerateRequest):
    """Generate professional Dockerfile and .dockerignore for a framework & port."""
    from apps.agent.app.deployment.dockerfile_generator import (
        generate_dockerfile,
        generate_dockerignore,
        TEMPLATES,
    )
    tmpl_key = payload.template_key
    if not tmpl_key:
        fw_clean = (payload.framework or "").lower()
        if "next" in fw_clean:
            tmpl_key = "nextjs"
        elif "vite" in fw_clean or "react" in fw_clean or "vue" in fw_clean:
            tmpl_key = "vite_spa"
        elif "fastapi" in fw_clean:
            tmpl_key = "fastapi"
        elif "django" in fw_clean:
            tmpl_key = "django"
        elif "flask" in fw_clean:
            tmpl_key = "flask"
        elif "laravel" in fw_clean or "php" in fw_clean:
            tmpl_key = "laravel"
        elif "go" in fw_clean:
            tmpl_key = "golang"
        elif "static" in fw_clean or "html" in fw_clean:
            tmpl_key = "static_html"
        else:
            tmpl_key = "node_backend"

    port = payload.port or TEMPLATES.get(tmpl_key, {}).get("default_port", 3000)
    df_content = generate_dockerfile(tmpl_key, port=port, project_name=payload.project_name)
    di_content = generate_dockerignore()

    return {
        "success": True,
        "template_key": tmpl_key,
        "template_name": TEMPLATES.get(tmpl_key, {}).get("name", "Custom"),
        "dockerfile": df_content,
        "dockerignore": di_content,
        "recommended_port": port,
    }


@router.get("/{project_id}/dockerfile")
def get_project_dockerfile_endpoint(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve existing or auto-generated Dockerfile and .dockerignore for this project."""
    import os
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    from apps.agent.app.deployment.dockerfile_generator import (
        generate_dockerfile,
        generate_dockerignore,
        detect_project_stack,
        TEMPLATES,
    )

    ws_dir = _resolve_project_workspace_dir(project_id)
    df_rel = p.source.dockerfile_path if p.source and p.source.dockerfile_path else "Dockerfile"
    full_df = os.path.join(ws_dir, df_rel)
    full_di = os.path.join(ws_dir, ".dockerignore")

    df_content = ""
    di_content = ""
    exists = False
    is_generated = False

    # Check if files physically exist in project workspace
    if os.path.exists(full_df):
        try:
            with open(full_df, "r", encoding="utf-8", errors="ignore") as f:
                df_content = f.read()
            exists = True
        except Exception:
            pass

    if os.path.exists(full_di):
        try:
            with open(full_di, "r", encoding="utf-8", errors="ignore") as f:
                di_content = f.read()
        except Exception:
            pass

    # If no Dockerfile yet, auto-generate high-performance preview
    if not df_content:
        is_generated = True
        stack_info = detect_project_stack(ws_dir) if os.path.exists(ws_dir) else {}
        tmpl_key = stack_info.get("template_key")
        if not tmpl_key:
            fw_clean = (p.framework or "").lower()
            if "next" in fw_clean:
                tmpl_key = "nextjs"
            elif "vite" in fw_clean or "react" in fw_clean or "vue" in fw_clean:
                tmpl_key = "vite_spa"
            elif "fastapi" in fw_clean:
                tmpl_key = "fastapi"
            elif "django" in fw_clean:
                tmpl_key = "django"
            elif "flask" in fw_clean:
                tmpl_key = "flask"
            elif "laravel" in fw_clean or "php" in fw_clean:
                tmpl_key = "laravel"
            elif "go" in fw_clean:
                tmpl_key = "golang"
            elif "static" in fw_clean or "html" in fw_clean:
                tmpl_key = "static_html"
            else:
                tmpl_key = "node_backend"

        port = 3000
        if p.port_mappings and ":" in p.port_mappings:
            try:
                port = int(p.port_mappings.split(":")[-1].split(",")[0].strip())
            except Exception:
                port = 3000

        df_content = generate_dockerfile(tmpl_key, port=port, project_name=p.name)

    if not di_content:
        di_content = generate_dockerignore()

    return {
        "success": True,
        "project_id": p.id,
        "project_name": p.name,
        "framework": p.framework,
        "dockerfile_path": df_rel,
        "dockerfile": df_content,
        "dockerignore": di_content,
        "exists": exists,
        "is_generated": is_generated,
        "workspace_exists": os.path.exists(ws_dir),
    }


@router.put("/{project_id}/dockerfile")
def update_project_dockerfile_endpoint(
    project_id: str,
    payload: DockerfileUpdateRequest,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db),
):
    """Write or update Dockerfile & .dockerignore directly in the project workspace."""
    import os
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    ws_dir = _resolve_project_workspace_dir(project_id)
    os.makedirs(ws_dir, exist_ok=True)

    target_rel = payload.dockerfile_path or (p.source.dockerfile_path if p.source else "Dockerfile") or "Dockerfile"
    full_df = os.path.join(ws_dir, target_rel)
    os.makedirs(os.path.dirname(full_df), exist_ok=True)

    with open(full_df, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload.dockerfile)

    if payload.dockerignore is not None:
        full_di = os.path.join(ws_dir, ".dockerignore")
        with open(full_di, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload.dockerignore)

    if p.source:
        p.source.dockerfile_path = target_rel
        db.commit()

    log_activity(
        db,
        action="project.dockerfile_update",
        resource_type="project",
        resource_id=project_id,
        user_id=current_user.id,
        details={"project": p.name, "dockerfile_path": target_rel},
    )

    return {
        "success": True,
        "message": f"Dockerfile berhasil disimpan ke workspace project ('{target_rel}').",
        "dockerfile_path": target_rel,
    }




import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.config import settings
from apps.api.app.core.security import hash_token
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import Server, Agent, AgentToken, ServerMetric, User
from apps.api.app.schemas.all_schemas import (
    ServerCreate,
    ServerUpdate,
    ServerResponse,
    ServerRegistrationResponse,
    AgentInfoResponse,
    MetricsSnapshot,
)
from apps.api.app.services.audit_service import log_activity
from apps.api.app.services.job_service import create_and_dispatch_job

router = APIRouter(prefix="/servers", tags=["Servers"])

def _get_control_plane_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8000"
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    if "testserver" in host:
        return "http://localhost:8000"
    # If host has port 3005 (from frontend proxy), point to API port 8000
    if host.endswith(":3005"):
        host = host.replace(":3005", ":8000")
    elif ":" not in host and scheme == "http":
        host = f"{host}:8000"
    return f"{scheme}://{host}"

def compute_server_status(server: Server) -> str:
    if server.status == "maintenance":
        return "maintenance"
    if server.agent and server.agent.revoked_at:
        return "offline"
    if not server.last_seen:
        return server.status if server.status == "online" else "pending"
    now = datetime.now(timezone.utc)
    last_seen = server.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if now - last_seen > timedelta(seconds=settings.HEARTBEAT_TIMEOUT_SECONDS):
        return "offline"
    return server.status if server.status != "pending" else "online"

@router.get("", response_model=List[ServerResponse])
def list_servers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    servers = db.query(Server).order_by(Server.created_at.desc()).all()
    result = []
    for s in servers:
        computed_status = compute_server_status(s)
        latest_metric = db.query(ServerMetric).filter(
            ServerMetric.server_id == s.id
        ).order_by(ServerMetric.recorded_at.desc()).first()

        metrics_data = None
        if latest_metric:
            metrics_data = MetricsSnapshot(
                cpu_usage=latest_metric.cpu_usage,
                memory_usage=latest_metric.memory_usage,
                memory_used_bytes=latest_metric.memory_used_bytes,
                memory_total_bytes=latest_metric.memory_total_bytes,
                disk_usage=latest_metric.disk_usage,
                disk_used_bytes=latest_metric.disk_used_bytes,
                disk_total_bytes=latest_metric.disk_total_bytes,
                network_rx=latest_metric.network_rx,
                network_tx=latest_metric.network_tx,
                uptime=latest_metric.uptime,
                recorded_at=latest_metric.recorded_at,
            )

        agent_data = None
        if s.agent:
            agent_data = AgentInfoResponse(
                id=s.agent.id,
                agent_version=s.agent.agent_version,
                connected_at=s.agent.connected_at,
                last_seen=s.agent.last_seen,
                revoked_at=s.agent.revoked_at,
            )

        result.append(
            ServerResponse(
                id=s.id,
                owner_id=s.owner_id,
                name=s.name,
                hostname=s.hostname,
                description=s.description,
                os_name=s.os_name,
                os_version=s.os_version,
                architecture=s.architecture,
                status=computed_status,
                last_seen=s.last_seen,
                created_at=s.created_at,
                agent=agent_data,
                latest_metrics=metrics_data,
            )
        )
    return result

@router.post("", response_model=ServerRegistrationResponse)
def create_server(
    payload: ServerCreate,
    request: Request,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    server = Server(
        owner_id=current_user.id,
        name=payload.name,
        hostname=payload.hostname or "localhost",
        description=payload.description,
        os_name=payload.os_name or "Ubuntu Server",
        os_version=payload.os_version or "24.04 LTS",
        architecture=payload.architecture or "x86_64",
        status="pending"
    )
    db.add(server)
    db.commit()
    db.refresh(server)

    raw_token = f"psm_agent_{secrets.token_urlsafe(32)}"
    token_record = AgentToken(
        server_id=server.id,
        token_hash=hash_token(raw_token),
        name=f"token-{server.name}"
    )
    db.add(token_record)
    db.commit()

    cp_url = _get_control_plane_url(request)
    install_command = (
        f"curl -sSL {cp_url}/install-agent.sh | "
        f"PSM_SERVER_ID={server.id} PSM_TOKEN={raw_token} PSM_CONTROL_PLANE={cp_url} bash"
    )
    docker_run_command = (
        f"docker run -d --name psm-agent --restart unless-stopped "
        f"-v /var/run/docker.sock:/var/run/docker.sock -v /opt/psm:/opt/psm "
        f"-e SERVER_ID={server.id} -e AGENT_TOKEN={raw_token} -e CONTROL_PLANE_URL={cp_url} "
        f"personal-server-manager-agent:latest"
    )

    log_activity(
        db,
        action="server.create",
        resource_type="server",
        resource_id=server.id,
        user_id=current_user.id,
        details={"name": server.name, "hostname": server.hostname}
    )

    return {
        "server_id": server.id,
        "agent_token": raw_token,
        "install_command": install_command,
        "docker_run_command": docker_run_command
    }

@router.get("/{server_id}", response_model=ServerResponse)
def get_server(
    server_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    latest_metric = db.query(ServerMetric).filter(
        ServerMetric.server_id == s.id
    ).order_by(ServerMetric.recorded_at.desc()).first()

    metrics_data = None
    if latest_metric:
        metrics_data = MetricsSnapshot(
            cpu_usage=latest_metric.cpu_usage,
            memory_usage=latest_metric.memory_usage,
            memory_used_bytes=latest_metric.memory_used_bytes,
            memory_total_bytes=latest_metric.memory_total_bytes,
            disk_usage=latest_metric.disk_usage,
            disk_used_bytes=latest_metric.disk_used_bytes,
            disk_total_bytes=latest_metric.disk_total_bytes,
            network_rx=latest_metric.network_rx,
            network_tx=latest_metric.network_tx,
            uptime=latest_metric.uptime,
            recorded_at=latest_metric.recorded_at,
        )

    agent_data = None
    if s.agent:
        agent_data = AgentInfoResponse(
            id=s.agent.id,
            agent_version=s.agent.agent_version,
            connected_at=s.agent.connected_at,
            last_seen=s.agent.last_seen,
            revoked_at=s.agent.revoked_at,
        )

    return ServerResponse(
        id=s.id,
        owner_id=s.owner_id,
        name=s.name,
        hostname=s.hostname,
        description=s.description,
        os_name=s.os_name,
        os_version=s.os_version,
        architecture=s.architecture,
        status=compute_server_status(s),
        last_seen=s.last_seen,
        created_at=s.created_at,
        agent=agent_data,
        latest_metrics=metrics_data,
    )

@router.patch("/{server_id}", response_model=ServerResponse)
def update_server(
    server_id: str,
    payload: ServerUpdate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    if payload.name is not None:
        s.name = payload.name
    if payload.hostname is not None:
        s.hostname = payload.hostname
    if payload.description is not None:
        s.description = payload.description
    if payload.status is not None:
        s.status = payload.status

    db.commit()
    db.refresh(s)

    log_activity(
        db,
        action="server.update",
        resource_type="server",
        resource_id=s.id,
        user_id=current_user.id
    )

    return get_server(server_id=server_id, current_user=current_user, db=db)

@router.delete("/{server_id}")
def delete_server(
    server_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    db.delete(s)
    db.commit()

    log_activity(
        db,
        action="server.delete",
        resource_type="server",
        resource_id=server_id,
        user_id=current_user.id
    )
    return {"message": "Server deleted successfully"}

@router.get("/{server_id}/status")
def get_server_status(
    server_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    return {
        "server_id": s.id,
        "status": compute_server_status(s),
        "last_seen": s.last_seen
    }

@router.get("/{server_id}/metrics", response_model=List[MetricsSnapshot])
def get_server_metrics(
    server_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    records = db.query(ServerMetric).filter(
        ServerMetric.server_id == server_id
    ).order_by(ServerMetric.recorded_at.desc()).limit(limit).all()
    return list(reversed(records))

@router.post("/{server_id}/reconnect")
async def request_server_reconnect(
    server_id: str,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    job = await create_and_dispatch_job(
        db=db,
        server_id=s.id,
        job_type="server.ping",
        payload={"requested_by": current_user.email}
    )
    return {"message": "Ping job dispatched to agent", "job_id": job.id}

@router.get("/{server_id}/agent")
def get_server_agent(
    server_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")
    if not s.agent:
        return {"registered": False, "server_id": s.id}
    return {
        "registered": True,
        "id": s.agent.id,
        "server_id": s.id,
        "agent_version": s.agent.agent_version,
        "connected_at": s.agent.connected_at,
        "last_seen": s.agent.last_seen,
        "revoked_at": s.agent.revoked_at
    }

@router.post("/{server_id}/agent/revoke")
def revoke_server_agent(
    server_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.now(timezone.utc)
    if s.agent:
        s.agent.revoked_at = now
    db.query(AgentToken).filter(AgentToken.server_id == server_id).delete()
    s.status = "offline"
    db.commit()

    log_activity(
        db,
        action="agent.revoke",
        resource_type="server",
        resource_id=server_id,
        user_id=current_user.id,
        details={"server_name": s.name}
    )
    return {"message": "Agent credentials revoked successfully", "server_id": server_id}

@router.post("/{server_id}/agent/rotate", response_model=ServerRegistrationResponse)
def rotate_server_agent_token(
    server_id: str,
    request: Request,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    s = db.query(Server).filter(Server.id == server_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Server not found")

    db.query(AgentToken).filter(AgentToken.server_id == server_id).delete()
    raw_token = f"psm_agent_{secrets.token_urlsafe(32)}"
    token_hash = hash_token(raw_token)
    token_record = AgentToken(
        server_id=s.id,
        token_hash=token_hash,
        name=f"rotated-{s.name}"
    )
    db.add(token_record)
    if s.agent:
        s.agent.credential_hash = token_hash
        s.agent.revoked_at = None
    db.commit()

    cp_url = _get_control_plane_url(request)
    install_command = (
        f"curl -sSL {cp_url}/install-agent.sh | "
        f"PSM_SERVER_ID={s.id} PSM_TOKEN={raw_token} PSM_CONTROL_PLANE={cp_url} bash"
    )
    docker_run_command = (
        f"docker run -d --name psm-agent --restart unless-stopped "
        f"-v /var/run/docker.sock:/var/run/docker.sock -v /opt/psm:/opt/psm "
        f"-e SERVER_ID={s.id} -e AGENT_TOKEN={raw_token} -e CONTROL_PLANE_URL={cp_url} "
        f"personal-server-manager-agent:latest"
    )

    log_activity(
        db,
        action="agent.rotate_token",
        resource_type="server",
        resource_id=s.id,
        user_id=current_user.id,
        details={"server_name": s.name}
    )

    return {
        "server_id": s.id,
        "agent_token": raw_token,
        "install_command": install_command,
        "docker_run_command": docker_run_command
    }

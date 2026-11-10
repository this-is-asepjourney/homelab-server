"""HTTP router for liveness, readiness, system info, version, and Prometheus metrics scrape."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.prometheus import render_prometheus_metrics
from app.modules.server.service import ServerService
from app.schemas import success_response

router = APIRouter(tags=["System"])

_latest_worker_heartbeat: Dict[str, Any] = {}


class WorkerHeartbeatPayload(BaseModel):
    worker_id: str = "pap-worker-01"
    uptime_sec: int = 0
    mqtt_connected: bool = True
    mqtt_messages_processed: int = 0
    last_mqtt_topic: Optional[str] = None
    last_mqtt_at: Optional[str] = None
    auto_backup_enabled: bool = True
    last_backup_at: Optional[str] = None
    active_monitors: int = 0
    memory_rss_mb: float = 0.0


@router.get("/health")
def health_check():
    return success_response(
        data={
            "status": "healthy",
            "service": "personal-api-platform",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        message="PAP service is alive",
    )


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    service = ServerService(db)
    return success_response(
        data=service.get_readiness(),
        message="PAP service is ready",
    )


@router.get("/system/info")
def system_info(db: Session = Depends(get_db)):
    service = ServerService(db)
    return success_response(
        data=service.get_system_info(),
        message="System information retrieved successfully",
    )


@router.get("/system/version")
def system_version(db: Session = Depends(get_db)):
    service = ServerService(db)
    return success_response(
        data=service.get_version(),
        message="API version retrieved successfully",
    )


@router.get("/metrics", include_in_schema=False)
def prometheus_exporter_endpoint():
    """Exposes bounded-label PAP & IoT telemetry metrics for Prometheus scraping."""
    payload = render_prometheus_metrics()
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.post("/system/worker-heartbeat")
def receive_worker_heartbeat(payload: WorkerHeartbeatPayload):
    """Heartbeat receiver called periodically by the decoupled pap-worker background daemon."""
    global _latest_worker_heartbeat
    data = payload.dict()
    data["received_at"] = datetime.now(timezone.utc).isoformat()
    data["received_timestamp"] = time.time()
    _latest_worker_heartbeat = data
    return {"status": "ok", "message": "Heartbeat recorded"}


@router.get("/system/worker-status")
def get_worker_status():
    """Returns the operational status of the decoupled pap-worker background engine."""
    global _latest_worker_heartbeat
    if not _latest_worker_heartbeat:
        return success_response(
            data={
                "status": "not_registered",
                "healthy": False,
                "role": "monolith_fallback",
                "detail": "No external pap-worker heartbeat registered. Falling back to internal mode.",
            },
            message="Worker status",
        )

    diff = time.time() - _latest_worker_heartbeat.get("received_timestamp", 0)
    is_healthy = diff < 60.0
    status_str = "healthy" if is_healthy else ("stale" if diff < 120.0 else "offline")
    return success_response(
        data={
            "status": status_str,
            "healthy": is_healthy,
            "seconds_since_heartbeat": round(diff, 1),
            "details": _latest_worker_heartbeat,
        },
        message="Worker status retrieved successfully",
    )


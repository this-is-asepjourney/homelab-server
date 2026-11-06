"""HTTP router for liveness, readiness, system info,version, and Prometheus metrics scrape."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.prometheus import render_prometheus_metrics
from app.modules.server.service import ServerService
from app.schemas import success_response

router = APIRouter(tags=["System"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    service = ServerService(db)
    return success_response(
        data=service.get_health(),
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


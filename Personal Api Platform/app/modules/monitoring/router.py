"""HTTP router for homelab service monitoring and platform overview."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_any_scope
from app.modules.monitoring.service import MonitoringService
from app.schemas import success_response

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/services")
def get_monitoring_services(
    principal: Principal = Depends(require_any_scope("metrics:read", "server:read")),
    db: Session = Depends(get_db),
):
    service = MonitoringService(db)
    return success_response(
        data=service.get_services_status(),
        message="Service status retrieved successfully",
    )


@router.get("/overview")
def get_monitoring_overview(
    principal: Principal = Depends(require_any_scope("metrics:read", "server:read")),
    db: Session = Depends(get_db),
):
    service = MonitoringService(db)
    return success_response(
        data=service.get_overview(),
        message="Monitoring overview retrieved successfully",
    )


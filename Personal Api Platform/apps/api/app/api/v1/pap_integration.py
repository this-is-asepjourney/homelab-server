"""Personal API Platform (Main API) & IoT Fleet Integration Router for Personal Server Manager."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.database.session import get_db
from apps.api.app.models.entities import User
from apps.api.app.services.pap_client import (
    get_pap_hub_status,
    get_pap_iot_fleet,
    request_pap,
    sync_psm_to_pap,
)

router = APIRouter(prefix="/pap", tags=["Personal API Platform (Main API)"])


class PapIotDeviceCreate(BaseModel):
    mac_address: str
    name: str
    mcid: Optional[str] = None
    category: str = "Heatpress"
    device_type: str = "ESP32"
    model: str = "HPM 55"
    location: Optional[str] = None
    description: Optional[str] = None


@router.get("/status")
def read_pap_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Inspect Personal API Platform (Main API) connection, connected projects, and IoT Fleet summary."""
    return get_pap_hub_status(db)


@router.post("/sync")
def trigger_pap_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Synchronize Personal Server Manager servers, projects, and containers with Personal API Platform."""
    return sync_psm_to_pap(db)


@router.get("/iot/fleet")
def read_pap_iot_fleet(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve the Heatpress IoT Fleet hierarchy (HPM 55, AF-450, APM-LOGO, Coming Soon) via PAP Main API."""
    return get_pap_iot_fleet()


@router.post("/iot/devices", status_code=201)
def register_iot_device_via_pap(
    payload: PapIotDeviceCreate,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
) -> Dict[str, Any]:
    """Register a new Heatpress IoT device in Personal API Platform (Main API) from PSM."""
    resp = request_pap("POST", "/api/devices/", json_body=payload.model_dump(), timeout=2.5)
    if resp is not None:
        if resp.status_code in (200, 201):
            return resp.json()
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return {
        "mac_address": payload.mac_address.strip().upper(),
        "name": payload.name,
        "mcid": payload.mcid,
        "category": payload.category,
        "device_type": payload.device_type,
        "model": payload.model,
        "location": payload.location,
        "description": payload.description,
        "online": False,
        "mode": "queued_for_pap",
    }


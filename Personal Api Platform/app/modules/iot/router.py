"""HTTP router for IoT devices, credential rotation, telemetry, and commands."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_any_scope, require_scopes
from app.modules.iot.models import Device
from app.modules.iot.schemas import (
    CommandCreate,
    CommandRead,
    CredentialRotationResponse,
    DeviceCreate,
    DeviceRead,
    DeviceRegisteredResponse,
    DeviceUpdate,
    TelemetryPayload,
    TelemetryRead,
)
from app.modules.iot.service import IotService
from app.schemas import success_response

router = APIRouter(prefix="/iot", tags=["IoT"])


def serialize_device(device: Device) -> dict:
    return DeviceRead(
        id=device.id,
        project_id=device.project_id,
        device_uid=device.device_uid,
        name=device.name,
        device_type=device.device_type,
        status=device.status,
        metadata=device.metadata_json,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
        updated_at=device.updated_at,
    ).model_dump(mode="json")


@router.get("/devices")
def list_devices(
    principal: Principal = Depends(require_scopes("iot:read")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    devices = service.list_devices(principal)
    return success_response(
        data=[serialize_device(d) for d in devices],
        message="IoT devices retrieved successfully",
    )


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceCreate,
    principal: Principal = Depends(require_scopes("iot:manage")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    device, raw_credential = service.register_device(payload, principal)
    resp = DeviceRegisteredResponse(
        id=device.id,
        project_id=device.project_id,
        device_uid=device.device_uid,
        name=device.name,
        device_type=device.device_type,
        status=device.status,
        metadata=device.metadata_json,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
        updated_at=device.updated_at,
        raw_credential=raw_credential,
    )
    return success_response(
        data=resp.model_dump(mode="json"),
        message="IoT device registered successfully. Store raw_credential securely.",
    )


@router.get("/devices/{device_id}")
def get_device(
    device_id: str,
    principal: Principal = Depends(require_scopes("iot:read")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    device = service.get_device(device_id, principal)
    return success_response(
        data=serialize_device(device),
        message="IoT device retrieved successfully",
    )


@router.patch("/devices/{device_id}")
def update_device(
    device_id: str,
    payload: DeviceUpdate,
    principal: Principal = Depends(require_scopes("iot:manage")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    device = service.update_device(device_id, payload, principal)
    return success_response(
        data=serialize_device(device),
        message="IoT device updated successfully",
    )


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: str,
    principal: Principal = Depends(require_scopes("iot:manage")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    deleted = service.delete_device(device_id, principal)
    return success_response(
        data=deleted,
        message="IoT device deleted successfully",
    )


@router.post("/devices/{device_id}/credentials/rotate")
def rotate_device_credential(
    device_id: str,
    principal: Principal = Depends(require_scopes("iot:manage")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    device, new_cred, raw_cred = service.rotate_credential(device_id, principal)
    resp = CredentialRotationResponse(
        device_id=device.id,
        device_uid=device.device_uid,
        credential_id=new_cred.id,
        raw_credential=raw_cred,
        rotated_at=datetime.now(timezone.utc),
    )
    return success_response(
        data=resp.model_dump(mode="json"),
        message="Device credential rotated successfully",
    )


@router.post("/devices/{device_id}/telemetry", status_code=status.HTTP_201_CREATED)
def ingest_device_telemetry(
    device_id: str,
    payload: TelemetryPayload,
    principal: Principal = Depends(require_scopes("iot:write")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    telemetry = service.ingest_telemetry(device_id, payload, principal)
    return success_response(
        data=TelemetryRead.model_validate(telemetry).model_dump(mode="json"),
        message="Telemetry ingested successfully",
    )


@router.get("/devices/{device_id}/telemetry")
def get_device_telemetry(
    device_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    principal: Principal = Depends(require_scopes("iot:read")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    records = service.query_telemetry(device_id, principal, limit=limit)
    data = [TelemetryRead.model_validate(r).model_dump(mode="json") for r in records]
    return success_response(
        data=data,
        message="Device telemetry retrieved successfully",
    )


@router.get("/devices/{device_id}/status")
def get_device_status(
    device_id: str,
    principal: Principal = Depends(require_scopes("iot:read")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    status_data = service.get_device_status(device_id, principal)
    return success_response(
        data=status_data,
        message="Device status retrieved successfully",
    )


@router.post("/devices/{device_id}/commands", status_code=status.HTTP_201_CREATED)
def create_device_command(
    device_id: str,
    payload: CommandCreate,
    principal: Principal = Depends(require_any_scope("iot:write", "iot:manage")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    cmd = service.create_command(device_id, payload, principal)
    return success_response(
        data=CommandRead.model_validate(cmd).model_dump(mode="json"),
        message="Authorized command created successfully",
    )


@router.post("/devices/{device_id}/commands/{correlation_id}/ack")
def acknowledge_device_command(
    device_id: str,
    correlation_id: str,
    principal: Principal = Depends(require_scopes("iot:write")),
    db: Session = Depends(get_db),
):
    service = IotService(db)
    cmd = service.acknowledge_command(device_id, correlation_id, principal)
    return success_response(
        data=CommandRead.model_validate(cmd).model_dump(mode="json"),
        message="Command acknowledged successfully",
    )


"""Service for IoT device lifecycle, authenticated telemetry ingestion, and command publishing."""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.permissions import Principal
from app.core.security import generate_device_credential
from app.integrations.mqtt import MqttAdapter
from app.integrations.prometheus import record_iot_prometheus_metrics
from app.modules.audit.service import AuditService
from app.modules.iot.models import Device, DeviceCredential, IotCommand, IotTelemetry
from app.modules.iot.repository import IotRepository
from app.modules.iot.schemas import (
    CommandCreate,
    DeviceCreate,
    DeviceUpdate,
    TelemetryPayload,
)
from app.modules.projects.repository import ProjectRepository


class IotService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = IotRepository(db)
        self.project_repo = ProjectRepository(db)
        self.mqtt = MqttAdapter()
        self.audit = AuditService(db)

    def resolve_device(self, identifier: str | uuid.UUID) -> Device:
        if isinstance(identifier, uuid.UUID):
            device = self.repo.get_by_id(identifier)
        else:
            try:
                uid = uuid.UUID(str(identifier))
                device = self.repo.get_by_id(uid)
            except ValueError:
                device = self.repo.get_by_uid(str(identifier))
        if not device:
            raise NotFoundError(message="IoT device not found", code="DEVICE_NOT_FOUND")
        return device

    def list_devices(self, principal: Principal) -> list[Device]:
        allowed = None if principal.is_admin else principal.allowed_project_ids
        return self.repo.list_devices(allowed_project_ids=allowed)

    def register_device(
        self, payload: DeviceCreate, principal: Principal
    ) -> tuple[Device, str]:
        project = self.project_repo.get_by_id(payload.project_id)
        if not project:
            raise NotFoundError(message="Project not found", code="PROJECT_NOT_FOUND")
        principal.require_project_access(project.id)

        if self.repo.get_by_uid(payload.device_uid):
            raise ConflictError(
                message=f"Device '{payload.device_uid}' is already registered",
                code="DEVICE_UID_EXISTS",
            )

        device = self.repo.create_device(
            Device(
                project_id=project.id,
                device_uid=payload.device_uid.strip(),
                name=payload.name or payload.device_uid.strip(),
                device_type=payload.device_type,
                status="registered",
                metadata_json=payload.metadata,
            )
        )
        raw_cred, cred_hash = generate_device_credential()
        self.repo.create_credential(
            DeviceCredential(
                device_id=device.id,
                credential_hash=cred_hash,
            )
        )

        self.audit.record(
            action="iot.device_registered",
            resource="devices",
            resource_id=str(device.id),
            project_id=project.id,
            principal=principal,
            details={"device_uid": device.device_uid, "device_type": device.device_type},
        )
        return device, raw_cred

    def get_device(self, identifier: str, principal: Principal) -> Device:
        device = self.resolve_device(identifier)
        if principal.identity_type == "device" and principal.device_id != device.id:
            raise PermissionDeniedError(
                message="Device cannot inspect another device",
                code="DEVICE_ISOLATION_VIOLATION",
            )
        principal.require_project_access(device.project_id)
        return device

    def update_device(
        self, identifier: str, payload: DeviceUpdate, principal: Principal
    ) -> Device:
        device = self.get_device(identifier, principal)
        if payload.name is not None:
            device.name = payload.name
        if payload.status is not None:
            device.status = payload.status
        if payload.metadata is not None:
            device.metadata_json = payload.metadata

        updated = self.repo.save_device(device)
        self.audit.record(
            action="iot.device_updated",
            resource="devices",
            resource_id=str(updated.id),
            project_id=updated.project_id,
            principal=principal,
            details={"device_uid": updated.device_uid, "status": updated.status},
        )
        return updated

    def delete_device(self, identifier: str, principal: Principal) -> dict[str, Any]:
        device = self.get_device(identifier, principal)
        info = {
            "id": str(device.id),
            "device_uid": device.device_uid,
            "name": device.name,
            "project_id": str(device.project_id),
        }
        self.repo.delete_device(device)
        self.audit.record(
            action="iot.device_deleted",
            resource="devices",
            resource_id=info["id"],
            project_id=device.project_id,
            principal=principal,
            details={"device_uid": info["device_uid"]},
        )
        return info

    def rotate_credential(
        self, identifier: str, principal: Principal
    ) -> tuple[Device, DeviceCredential, str]:
        device = self.get_device(identifier, principal)
        self.repo.revoke_active_credentials(device.id)
        raw_cred, cred_hash = generate_device_credential()
        new_cred = self.repo.create_credential(
            DeviceCredential(device_id=device.id, credential_hash=cred_hash)
        )
        self.audit.record(
            action="iot.credential_rotated",
            resource="device_credentials",
            resource_id=str(new_cred.id),
            project_id=device.project_id,
            principal=principal,
            details={"device_uid": device.device_uid},
        )
        return device, new_cred, raw_cred

    def ingest_telemetry(
        self, identifier: str, payload: TelemetryPayload, principal: Principal
    ) -> IotTelemetry:
        device = self.resolve_device(identifier)

        # Enforce strict anti-impersonation rules per Section 9.4 & Phase 5
        if principal.identity_type == "device":
            if principal.device_id != device.id or principal.device_uid != payload.device_id:
                self.audit.record(
                    action="iot.telemetry_spoofing_blocked",
                    resource="devices",
                    resource_id=str(device.id),
                    project_id=device.project_id,
                    status="failure",
                    details={
                        "authenticated_device_uid": principal.device_uid,
                        "target_device_uid": device.device_uid,
                        "payload_device_id": payload.device_id,
                    },
                )
                raise PermissionDeniedError(
                    message="Device identity mismatch; payload device_id does not match authenticated device credential",
                    code="DEVICE_IDENTITY_MISMATCH",
                )
        else:
            principal.require_project_access(device.project_id)
            if payload.device_id != device.device_uid:
                raise PermissionDeniedError(
                    message="Payload device_id does not match target device UID",
                    code="DEVICE_IDENTITY_MISMATCH",
                )

        now = datetime.now(timezone.utc)
        device.last_seen_at = now
        if device.status == "registered" or device.status == "offline":
            device.status = "online"
        self.db.commit()

        telemetry = self.repo.create_telemetry(
            IotTelemetry(
                device_id=device.id,
                device_uid=device.device_uid,
                timestamp=payload.timestamp,
                temperature=payload.temperature,
                counter=payload.counter,
                current=payload.current,
                payload=payload.model_dump(mode="json"),
            )
        )

        # Update Prometheus bounded-label exporter metrics
        record_iot_prometheus_metrics(
            device_uid=device.device_uid,
            device_type=device.device_type,
            temperature=payload.temperature,
            counter=payload.counter,
            current=payload.current,
        )
        return telemetry

    def query_telemetry(
        self, identifier: str, principal: Principal, limit: int = 50
    ) -> list[IotTelemetry]:
        device = self.get_device(identifier, principal)
        return self.repo.list_telemetry(device.id, limit=limit)

    def get_device_status(self, identifier: str, principal: Principal) -> dict[str, Any]:
        device = self.get_device(identifier, principal)
        return {
            "device_id": str(device.id),
            "device_uid": device.device_uid,
            "device_type": device.device_type,
            "status": device.status,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "topics": {
                "telemetry": MqttAdapter.telemetry_topic(device.device_uid),
                "status": MqttAdapter.status_topic(device.device_uid),
                "command": MqttAdapter.command_topic(device.device_uid),
                "config": MqttAdapter.config_topic(device.device_uid),
            },
        }

    def create_command(
        self, identifier: str, payload: CommandCreate, principal: Principal
    ) -> IotCommand:
        if principal.identity_type == "device":
            raise PermissionDeniedError(
                message="IoT devices are not permitted to issue commands",
                code="DEVICE_COMMAND_FORBIDDEN",
            )
        device = self.get_device(identifier, principal)
        correlation_id = payload.correlation_id or f"cmd-{uuid.uuid4()}"
        if self.repo.get_command_by_correlation(correlation_id):
            raise ConflictError(
                message=f"Command correlation_id '{correlation_id}' already exists",
                code="CORRELATION_ID_EXISTS",
            )

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.ttl_seconds)
        published = self.mqtt.publish_command(
            device_uid=device.device_uid,
            correlation_id=correlation_id,
            command=payload.command,
            parameters=payload.parameters,
            expires_at_iso=expires_at.isoformat(),
        )
        cmd = self.repo.create_command(
            IotCommand(
                device_id=device.id,
                correlation_id=correlation_id,
                command=payload.command,
                parameters=payload.parameters,
                status="published" if published else "pending",
                expires_at=expires_at,
            )
        )
        self.audit.record(
            action="iot.command_issued",
            resource="iot_commands",
            resource_id=str(cmd.id),
            project_id=device.project_id,
            principal=principal,
            details={
                "device_uid": device.device_uid,
                "command": cmd.command,
                "correlation_id": cmd.correlation_id,
            },
        )
        return cmd

    def acknowledge_command(
        self, identifier: str, correlation_id: str, principal: Principal
    ) -> IotCommand:
        device = self.get_device(identifier, principal)
        cmd = self.repo.get_command_by_correlation(correlation_id)
        if not cmd or cmd.device_id != device.id:
            raise NotFoundError(message="Command not found", code="COMMAND_NOT_FOUND")
        cmd.status = "acknowledged"
        cmd.acknowledged_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(cmd)
        return cmd


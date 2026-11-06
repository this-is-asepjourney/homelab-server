"""SQLAlchemy models for IoT device registry, credentials, telemetry, and authorized commands."""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), default="esp32", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="registered", index=True, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    credentials: Mapped[list["DeviceCredential"]] = relationship(
        "DeviceCredential",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    credential_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped["Device"] = relationship("Device", back_populates="credentials")


class IotTelemetry(Base):
    __tablename__ = "iot_telemetry"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    device_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class IotCommand(Base):
    __tablename__ = "iot_commands"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    command: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


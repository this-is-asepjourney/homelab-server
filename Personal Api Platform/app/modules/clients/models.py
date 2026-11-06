"""SQLAlchemy models for API clients, hashed API keys, and client scope assignments."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.permissions.models import Scope


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


client_scopes_table = Table(
    "client_scopes",
    Base.metadata,
    Column(
        "client_id",
        Uuid(as_uuid=True),
        ForeignKey("api_clients.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "scope_id",
        Uuid(as_uuid=True),
        ForeignKey("scopes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ApiClient(Base):
    __tablename__ = "api_clients"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_type: Mapped[str] = mapped_column(String(64), default="backend", nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    scopes: Mapped[list[Scope]] = relationship(
        Scope,
        secondary=client_scopes_table,
        lazy="selectin",
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="client",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("api_clients.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), default="default", nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    client: Mapped["ApiClient"] = relationship("ApiClient", back_populates="api_keys")


"""SQLAlchemy model for registered database connections (stores secret references only)."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DatabaseConnection(Base):
    __tablename__ = "database_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)  # postgresql | mysql
    host: Mapped[str] = mapped_column(String(255), default="100.106.63.90", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=5432, nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_tables: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


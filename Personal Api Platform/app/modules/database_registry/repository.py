"""Repository for registered database connections."""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.database_registry.models import DatabaseConnection


class DatabaseRegistryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, conn_id: uuid.UUID) -> Optional[DatabaseConnection]:
        return self.db.get(DatabaseConnection, conn_id)

    def get_by_name(self, name: str) -> Optional[DatabaseConnection]:
        return self.db.scalar(select(DatabaseConnection).where(DatabaseConnection.name == name))

    def list_connections(
        self, allowed_project_ids: Optional[set[uuid.UUID]] = None
    ) -> list[DatabaseConnection]:
        stmt = select(DatabaseConnection).order_by(DatabaseConnection.created_at.desc())
        if allowed_project_ids is not None:
            if not allowed_project_ids:
                return []
            stmt = stmt.where(DatabaseConnection.project_id.in_(allowed_project_ids))
        return list(self.db.scalars(stmt).all())

    def create(self, conn: DatabaseConnection) -> DatabaseConnection:
        self.db.add(conn)
        self.db.commit()
        self.db.refresh(conn)
        return conn


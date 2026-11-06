"""Service for database connection registry, health checks, and allowlisted schema inspection."""

from typing import Any, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.integrations.mysql import MySQLReadOnlyAdapter
from app.integrations.postgresql import PostgreSQLAdapter
from app.modules.audit.service import AuditService
from app.modules.database_registry.models import DatabaseConnection
from app.modules.database_registry.repository import DatabaseRegistryRepository
from app.modules.database_registry.schemas import DatabaseConnectionCreate
from app.modules.projects.repository import ProjectRepository


class DatabaseRegistryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DatabaseRegistryRepository(db)
        self.project_repo = ProjectRepository(db)
        self.audit = AuditService(db)

    def list_connections(self, principal: Principal) -> list[DatabaseConnection]:
        allowed = None if principal.is_admin else principal.allowed_project_ids
        return self.repo.list_connections(allowed_project_ids=allowed)

    def register_connection(
        self, payload: DatabaseConnectionCreate, principal: Principal
    ) -> DatabaseConnection:
        project = self.project_repo.get_by_id(payload.project_id)
        if not project:
            raise NotFoundError(message="Project not found", code="PROJECT_NOT_FOUND")
        principal.require_project_access(project.id)

        if self.repo.get_by_name(payload.name):
            raise ConflictError(
                message=f"Database connection '{payload.name}' already exists",
                code="DB_CONNECTION_EXISTS",
            )

        conn = DatabaseConnection(
            project_id=project.id,
            name=payload.name,
            engine=payload.engine,
            host=payload.host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            secret_reference=payload.secret_reference,
            allowed_tables=payload.allowed_tables,
            read_only=payload.read_only,
            is_active=True,
        )
        created = self.repo.create(conn)
        self.audit.record(
            action="database.connection_registered",
            resource="database_connections",
            resource_id=str(created.id),
            project_id=project.id,
            principal=principal,
            details={
                "name": created.name,
                "engine": created.engine,
                "database_name": created.database_name,
                "secret_reference": created.secret_reference,
            },
        )
        return created

    def get_connection(self, conn_id: uuid.UUID, principal: Principal) -> DatabaseConnection:
        conn = self.repo.get_by_id(conn_id)
        if not conn:
            raise NotFoundError(
                message="Database connection not found", code="DB_CONNECTION_NOT_FOUND"
            )
        principal.require_project_access(conn.project_id)
        return conn

    def _build_adapter(self, conn: DatabaseConnection):
        if conn.engine == "mysql":
            return MySQLReadOnlyAdapter(
                host=conn.host,
                port=conn.port,
                database_name=conn.database_name,
                username=conn.username,
                secret_reference=conn.secret_reference,
                allowed_tables=conn.allowed_tables,
            )
        return PostgreSQLAdapter(
            host=conn.host,
            port=conn.port,
            database_name=conn.database_name,
            username=conn.username,
            secret_reference=conn.secret_reference,
            allowed_tables=conn.allowed_tables,
        )

    def check_connection_health(self, conn_id: uuid.UUID, principal: Principal) -> dict[str, Any]:
        conn = self.get_connection(conn_id, principal)
        adapter = self._build_adapter(conn)
        health = adapter.check_health()
        health["connection_id"] = str(conn.id)
        health["name"] = conn.name
        return health

    def list_approved_sources(self, principal: Principal) -> list[dict[str, Any]]:
        conns = self.list_connections(principal)
        return [
            {
                "id": str(c.id),
                "project_id": str(c.project_id),
                "name": c.name,
                "engine": c.engine,
                "database_name": c.database_name,
                "allowed_tables": c.allowed_tables,
                "read_only": c.read_only,
                "is_active": c.is_active,
            }
            for c in conns
            if c.is_active
        ]

    def read_approved_schema(
        self,
        conn_id: uuid.UUID,
        principal: Principal,
        table_name: Optional[str] = None,
    ) -> dict[str, Any]:
        conn = self.get_connection(conn_id, principal)
        adapter = self._build_adapter(conn)
        schema_data = adapter.get_approved_schema(table_name=table_name)
        schema_data["source_id"] = str(conn.id)
        schema_data["source_name"] = conn.name
        self.audit.record(
            action="database.schema_inspected",
            resource="database_connections",
            resource_id=str(conn.id),
            project_id=conn.project_id,
            principal=principal,
            details={"table": table_name},
        )
        return schema_data


"""HTTP router for database connection registry and allowlisted schema inspection."""

from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import PermissionDeniedError
from app.core.permissions import Principal
from app.dependencies import get_current_principal, require_scopes
from app.modules.database_registry.schemas import (
    DatabaseConnectionCreate,
    DatabaseConnectionRead,
)
from app.modules.database_registry.service import DatabaseRegistryService
from app.schemas import success_response

router = APIRouter(prefix="/database", tags=["Database Registry"])


@router.get("/connections")
def list_database_connections(
    principal: Principal = Depends(require_scopes("database:read")),
    db: Session = Depends(get_db),
):
    service = DatabaseRegistryService(db)
    conns = service.list_connections(principal)
    data = [DatabaseConnectionRead.model_validate(c).model_dump(mode="json") for c in conns]
    return success_response(
        data=data,
        message="Database connections retrieved successfully",
    )


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def register_database_connection(
    payload: DatabaseConnectionCreate,
    principal: Principal = Depends(require_scopes("database:manage")),
    db: Session = Depends(get_db),
):
    service = DatabaseRegistryService(db)
    conn = service.register_connection(payload, principal)
    return success_response(
        data=DatabaseConnectionRead.model_validate(conn).model_dump(mode="json"),
        message="Database connection registered successfully",
    )


@router.get("/connections/{connection_id}/health")
def check_database_connection_health(
    connection_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("database:read")),
    db: Session = Depends(get_db),
):
    service = DatabaseRegistryService(db)
    health = service.check_connection_health(connection_id, principal)
    return success_response(
        data=health,
        message="Database connection health checked",
    )


@router.get("/sources")
def list_approved_sources(
    principal: Principal = Depends(require_scopes("database:read")),
    db: Session = Depends(get_db),
):
    service = DatabaseRegistryService(db)
    sources = service.list_approved_sources(principal)
    return success_response(
        data=sources,
        message="Approved data sources retrieved successfully",
    )


@router.get("/sources/{source_id}/schema")
def read_approved_schema(
    source_id: uuid.UUID,
    table: Optional[str] = Query(default=None),
    principal: Principal = Depends(require_scopes("database:read")),
    db: Session = Depends(get_db),
):
    service = DatabaseRegistryService(db)
    schema_meta = service.read_approved_schema(source_id, principal, table_name=table)
    return success_response(
        data=schema_meta,
        message="Approved schema metadata retrieved successfully",
    )


@router.api_route("/query", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def reject_unrestricted_sql_query(
    principal: Principal = Depends(get_current_principal),
):
    """Explicitly block unrestricted SQL execution per Blueprint Section 1.2 & 7.3."""
    raise PermissionDeniedError(
        message="Unrestricted SQL execution endpoint is forbidden by PAP security policy.",
        code="UNRESTRICTED_SQL_FORBIDDEN",
    )


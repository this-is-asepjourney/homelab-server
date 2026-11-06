"""HTTP router for RBAC roles, permissions, and scopes."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_scopes
from app.modules.permissions.schemas import (
    PermissionRead,
    RoleCreate,
    RolePermissionsUpdate,
    RoleRead,
    ScopeCreate,
    ScopeRead,
)
from app.modules.permissions.service import PermissionsService
from app.schemas import success_response

router = APIRouter(tags=["Permissions & Scopes"])


def _serialize_role(role) -> dict:
    return RoleRead(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=[p.name for p in role.permissions],
        created_at=role.created_at,
    ).model_dump(mode="json")


@router.get("/scopes")
def list_scopes(
    principal: Principal = Depends(require_scopes("clients:read")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    scopes = service.list_scopes()
    data = [ScopeRead.model_validate(s).model_dump(mode="json") for s in scopes]
    return success_response(data=data, message="Scopes retrieved successfully")


@router.post("/scopes", status_code=status.HTTP_201_CREATED)
def create_scope(
    payload: ScopeCreate,
    principal: Principal = Depends(require_scopes("clients:manage")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    scope = service.create_scope(payload, principal)
    return success_response(
        data=ScopeRead.model_validate(scope).model_dump(mode="json"),
        message="Scope created successfully",
    )


@router.get("/permissions")
def list_permissions(
    principal: Principal = Depends(require_scopes("users:read")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    perms = service.list_permissions()
    data = [PermissionRead.model_validate(p).model_dump(mode="json") for p in perms]
    return success_response(data=data, message="Permissions retrieved successfully")


@router.get("/roles")
def list_roles(
    principal: Principal = Depends(require_scopes("users:read")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    roles = service.list_roles()
    return success_response(
        data=[_serialize_role(r) for r in roles],
        message="Roles retrieved successfully",
    )


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    principal: Principal = Depends(require_scopes("users:manage")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    role = service.create_role(payload, principal)
    return success_response(data=_serialize_role(role), message="Role created successfully")


@router.put("/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: uuid.UUID,
    payload: RolePermissionsUpdate,
    principal: Principal = Depends(require_scopes("users:manage")),
    db: Session = Depends(get_db),
):
    service = PermissionsService(db)
    role = service.update_role_permissions(role_id, payload.permissions, principal)
    return success_response(
        data=_serialize_role(role),
        message="Role permissions updated successfully",
    )


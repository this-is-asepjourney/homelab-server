"""HTTP router for user management."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_scopes
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserRead, UserRolesUpdate, UserUpdate
from app.modules.users.service import UserService
from app.schemas import success_response

router = APIRouter(prefix="/users", tags=["Users"])


def serialize_user(user: User) -> dict:
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=[r.name for r in user.roles],
        created_at=user.created_at,
        updated_at=user.updated_at,
    ).model_dump(mode="json")


@router.get("")
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_scopes("users:read")),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    users, total = service.list_users(page=page, page_size=page_size)
    return success_response(
        data=[serialize_user(u) for u in users],
        message="Users retrieved successfully",
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    principal: Principal = Depends(require_scopes("users:manage")),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = service.create_user(payload, principal)
    return success_response(
        data=serialize_user(user),
        message="User created successfully",
    )


@router.get("/{user_id}")
def get_user(
    user_id: uuid.UUID,
    principal: Principal = Depends(require_scopes("users:read")),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = service.get_user(user_id)
    return success_response(data=serialize_user(user), message="User retrieved successfully")


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    principal: Principal = Depends(require_scopes("users:manage")),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = service.update_user(user_id, payload, principal)
    return success_response(data=serialize_user(user), message="User updated successfully")


@router.put("/{user_id}/roles")
def assign_user_roles(
    user_id: uuid.UUID,
    payload: UserRolesUpdate,
    principal: Principal = Depends(require_scopes("users:manage")),
    db: Session = Depends(get_db),
):
    service = UserService(db)
    user = service.assign_roles(user_id, payload.roles, principal)
    return success_response(
        data=serialize_user(user),
        message="User roles updated successfully",
    )


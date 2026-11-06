from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.security import hash_password
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import User
from apps.api.app.schemas.all_schemas import UserCreate, UserUpdate, UserResponse
from apps.api.app.services.audit_service import log_activity

router = APIRouter(prefix="/users", tags=["User Management"])

@router.get("", response_model=List[UserResponse])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(User).order_by(User.created_at.asc()).all()

@router.post("", response_model=UserResponse)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email is already registered")

    user = User(
        name=payload.name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role if payload.role in ("owner", "admin", "operator", "viewer") else "operator",
        theme="system",
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        user_id=current_user.id,
        details={"email": user.email, "role": user.role}
    )
    return user

@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.id != user_id and current_user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if payload.name is not None:
        user.name = payload.name
    if payload.theme is not None:
        user.theme = payload.theme
    if payload.role is not None and current_user.role in ("owner", "admin"):
        user.role = payload.role
    if payload.is_active is not None and current_user.role in ("owner", "admin"):
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)

    log_activity(
        db,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        user_id=current_user.id,
        details={"role": user.role, "is_active": user.is_active}
    )
    return user

@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    log_activity(
        db,
        action="user.delete",
        resource_type="user",
        resource_id=user_id,
        user_id=current_user.id
    )
    return {"message": "User deleted"}


"""Service for user management and role assignment."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.core.security import hash_password
from app.modules.audit.service import AuditService
from app.modules.permissions.repository import PermissionsRepository
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserUpdate


class UserService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = UserRepository(db)
        self.perm_repo = PermissionsRepository(db)
        self.audit = AuditService(db)

    def create_user(self, payload: UserCreate, principal: Principal | None = None) -> User:
        if self.repo.get_by_email(payload.email):
            raise ConflictError(
                message=f"User with email '{payload.email}' already exists",
                code="EMAIL_ALREADY_EXISTS",
            )
        roles = []
        for role_name in payload.roles:
            role = self.perm_repo.get_role_by_name(role_name)
            if not role:
                role = self.perm_repo.create_role(name=role_name, description=role_name)
            roles.append(role)

        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            is_active=True,
            roles=roles,
        )
        created = self.repo.create(user)
        self.audit.record(
            action="user.created",
            resource="users",
            resource_id=str(created.id),
            principal=principal,
            details={"email": created.email, "roles": payload.roles},
        )
        return created

    def get_user(self, user_id: uuid.UUID) -> User:
        user = self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(message="User not found", code="USER_NOT_FOUND")
        return user

    def list_users(self, page: int = 1, page_size: int = 50) -> tuple[list[User], int]:
        offset = (page - 1) * page_size
        return self.repo.list_users(offset=offset, limit=page_size)

    def update_user(
        self, user_id: uuid.UUID, payload: UserUpdate, principal: Principal
    ) -> User:
        user = self.get_user(user_id)
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.is_active is not None:
            user.is_active = payload.is_active
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)

        updated = self.repo.save(user)
        self.audit.record(
            action="user.updated",
            resource="users",
            resource_id=str(updated.id),
            principal=principal,
            details={"email": updated.email, "is_active": updated.is_active},
        )
        return updated

    def assign_roles(
        self, user_id: uuid.UUID, role_names: list[str], principal: Principal
    ) -> User:
        user = self.get_user(user_id)
        roles = []
        for role_name in role_names:
            role = self.perm_repo.get_role_by_name(role_name)
            if not role:
                role = self.perm_repo.create_role(name=role_name, description=role_name)
            roles.append(role)
        user.roles = roles
        updated = self.repo.save(user)
        self.audit.record(
            action="user.roles_assigned",
            resource="users",
            resource_id=str(updated.id),
            principal=principal,
            details={"roles": role_names},
        )
        return updated


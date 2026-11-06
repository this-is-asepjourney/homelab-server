"""Repository for roles, permissions, and scopes."""

from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.permissions.models import Permission, Role, Scope


class PermissionsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_scope_by_name(self, name: str) -> Optional[Scope]:
        return self.db.scalar(select(Scope).where(Scope.name == name))

    def list_scopes(self) -> list[Scope]:
        return list(self.db.scalars(select(Scope).order_by(Scope.name)).all())

    def create_scope(self, name: str, description: str = "") -> Scope:
        scope = Scope(name=name, description=description)
        self.db.add(scope)
        self.db.commit()
        self.db.refresh(scope)
        return scope

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        return self.db.scalar(select(Permission).where(Permission.name == name))

    def list_permissions(self) -> list[Permission]:
        return list(self.db.scalars(select(Permission).order_by(Permission.name)).all())

    def create_permission(self, name: str, description: str = "") -> Permission:
        perm = Permission(name=name, description=description)
        self.db.add(perm)
        self.db.commit()
        self.db.refresh(perm)
        return perm

    def get_role_by_id(self, role_id: uuid.UUID) -> Optional[Role]:
        return self.db.get(Role, role_id)

    def get_role_by_name(self, name: str) -> Optional[Role]:
        return self.db.scalar(select(Role).where(Role.name == name))

    def list_roles(self) -> list[Role]:
        return list(self.db.scalars(select(Role).order_by(Role.name)).all())

    def create_role(
        self,
        name: str,
        description: Optional[str] = None,
        permissions: Optional[list[Permission]] = None,
    ) -> Role:
        role = Role(name=name, description=description)
        if permissions:
            role.permissions = permissions
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role


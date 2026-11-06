"""Service for managing roles, permissions, and scopes."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import DEFAULT_ROLES, DEFAULT_SCOPES, Principal
from app.modules.audit.service import AuditService
from app.modules.permissions.models import Permission, Role, Scope
from app.modules.permissions.repository import PermissionsRepository
from app.modules.permissions.schemas import RoleCreate, ScopeCreate


class PermissionsService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PermissionsRepository(db)
        self.audit = AuditService(db)

    def seed_defaults(self) -> None:
        """Ensure canonical scopes, permissions, and roles exist in the database."""
        for scope_name, desc in DEFAULT_SCOPES.items():
            if not self.repo.get_scope_by_name(scope_name):
                self.db.add(Scope(name=scope_name, description=desc))
            if not self.repo.get_permission_by_name(scope_name):
                self.db.add(Permission(name=scope_name, description=desc))
        self.db.commit()

        for role_name, perm_names in DEFAULT_ROLES.items():
            role = self.repo.get_role_by_name(role_name)
            perms = [
                p
                for name in perm_names
                if (p := self.repo.get_permission_by_name(name)) is not None
            ]
            if not role:
                new_role = Role(name=role_name, description=f"Default {role_name} role")
                new_role.permissions = perms
                self.db.add(new_role)
            else:
                role.permissions = perms
        self.db.commit()

    def list_scopes(self) -> list[Scope]:
        return self.repo.list_scopes()

    def create_scope(self, payload: ScopeCreate, principal: Principal) -> Scope:
        if self.repo.get_scope_by_name(payload.name):
            raise ConflictError(message=f"Scope '{payload.name}' already exists", code="SCOPE_EXISTS")
        scope = self.repo.create_scope(name=payload.name, description=payload.description)
        self.audit.record(
            action="scope.created",
            resource="scopes",
            resource_id=str(scope.id),
            principal=principal,
            details={"name": scope.name},
        )
        return scope

    def list_permissions(self) -> list[Permission]:
        return self.repo.list_permissions()

    def list_roles(self) -> list[Role]:
        return self.repo.list_roles()

    def create_role(self, payload: RoleCreate, principal: Principal) -> Role:
        if self.repo.get_role_by_name(payload.name):
            raise ConflictError(message=f"Role '{payload.name}' already exists", code="ROLE_EXISTS")
        perms: list[Permission] = []
        for perm_name in payload.permissions:
            perm = self.repo.get_permission_by_name(perm_name)
            if not perm:
                perm = self.repo.create_permission(name=perm_name, description=perm_name)
            perms.append(perm)
        role = self.repo.create_role(
            name=payload.name, description=payload.description, permissions=perms
        )
        self.audit.record(
            action="role.created",
            resource="roles",
            resource_id=str(role.id),
            principal=principal,
            details={"name": role.name, "permissions": payload.permissions},
        )
        return role

    def update_role_permissions(
        self, role_id: uuid.UUID, permission_names: list[str], principal: Principal
    ) -> Role:
        role = self.repo.get_role_by_id(role_id)
        if not role:
            raise NotFoundError(message="Role not found", code="ROLE_NOT_FOUND")
        perms: list[Permission] = []
        for perm_name in permission_names:
            perm = self.repo.get_permission_by_name(perm_name)
            if not perm:
                perm = self.repo.create_permission(name=perm_name, description=perm_name)
            perms.append(perm)
        role.permissions = perms
        self.db.commit()
        self.db.refresh(role)
        self.audit.record(
            action="role.permissions_updated",
            resource="roles",
            resource_id=str(role.id),
            principal=principal,
            details={"role": role.name, "permissions": permission_names},
        )
        return role


"""RBAC roles, permissions, scopes, and authenticated Principal model."""

from dataclasses import dataclass, field
from typing import Optional
import uuid

from app.core.exceptions import PermissionDeniedError

# Canonical PAP scopes defined in Blueprint Section 8.3
DEFAULT_SCOPES: dict[str, str] = {
    "projects:read": "Read registered projects and project metadata",
    "projects:manage": "Create, update, and manage projects and memberships",
    "clients:read": "Read registered API clients and scope assignments",
    "clients:manage": "Register API clients, issue/revoke API keys, and assign scopes",
    "users:read": "Read user accounts and roles",
    "users:manage": "Create, update, and assign roles to users",
    "inventory:read": "Read approved product and inventory data",
    "inventory:write": "Publish or update approved inventory events",
    "transactions:read": "Read approved transaction records",
    "transactions:write": "Create or publish approved transaction events",
    "iot:read": "Read IoT device registry, status, and telemetry",
    "iot:write": "Publish device telemetry or send authorized commands",
    "iot:manage": "Register IoT devices, update metadata, and rotate credentials",
    "metrics:read": "Query Prometheus metrics and monitoring status",
    "server:read": "Read server resource metrics and platform info",
    "docker:read": "Read container status and statistics",
    "docker:restart": "Execute restricted container restart operation",
    "database:read": "List registered database connections and approved schema metadata",
    "database:manage": "Register database connections and test connectivity",
    "integrations:read": "List configured integrations and check integration health",
    "integrations:manage": "Configure project integrations",
    "webhooks:read": "List webhook subscriptions and delivery state",
    "webhooks:manage": "Create and disable webhook subscriptions",
    "audit:read": "Read platform audit logs",
}

DEFAULT_ROLES: dict[str, list[str]] = {
    "admin": list(DEFAULT_SCOPES.keys()),
    "developer": [
        "projects:read",
        "projects:manage",
        "clients:read",
        "clients:manage",
        "inventory:read",
        "transactions:read",
        "iot:read",
        "iot:manage",
        "metrics:read",
        "server:read",
        "database:read",
        "integrations:read",
        "webhooks:read",
        "webhooks:manage",
        "audit:read",
    ],
    "operator": [
        "projects:read",
        "inventory:read",
        "iot:read",
        "iot:write",
        "metrics:read",
        "server:read",
        "integrations:read",
    ],
    "viewer": [
        "projects:read",
        "iot:read",
        "metrics:read",
        "server:read",
    ],
}


@dataclass
class Principal:
    """Represents the authenticated caller (human user, machine client, or IoT device)."""

    identity_type: str  # "user" | "client" | "device"
    subject_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    device_id: Optional[uuid.UUID] = None
    device_uid: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    email: Optional[str] = None
    client_identifier: Optional[str] = None
    roles: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    allowed_project_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def has_scope(self, required_scope: str) -> bool:
        if self.is_admin:
            return True
        return required_scope in self.scopes or required_scope in self.permissions

    def require_scope(self, required_scope: str) -> None:
        if not self.has_scope(required_scope):
            raise PermissionDeniedError(
                message=f"Missing required scope: {required_scope}",
                code="INSUFFICIENT_SCOPE",
                details={"required_scope": required_scope},
            )

    def require_any_scope(self, required_scopes: list[str]) -> None:
        if self.is_admin:
            return
        if not any(self.has_scope(s) for s in required_scopes):
            raise PermissionDeniedError(
                message=f"Missing required scope (one of: {', '.join(required_scopes)})",
                code="INSUFFICIENT_SCOPE",
                details={"required_scopes": required_scopes},
            )

    def can_access_project(self, target_project_id: uuid.UUID) -> bool:
        if self.is_admin:
            return True
        if self.project_id and self.project_id == target_project_id:
            return True
        if target_project_id in self.allowed_project_ids:
            return True
        return False

    def require_project_access(self, target_project_id: uuid.UUID) -> None:
        if not self.can_access_project(target_project_id):
            raise PermissionDeniedError(
                message="Cross-project access denied",
                code="CROSS_PROJECT_ACCESS_DENIED",
                details={"project_id": str(target_project_id)},
            )


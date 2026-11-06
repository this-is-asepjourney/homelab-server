"""Service for API client registration, scope assignment, and hashed API key lifecycle."""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.core.security import generate_api_key, hash_password
from app.modules.audit.service import AuditService
from app.modules.clients.models import ApiClient, ApiKey
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import ApiClientCreate, ApiKeyCreate
from app.modules.permissions.models import Scope
from app.modules.permissions.repository import PermissionsRepository
from app.modules.projects.repository import ProjectRepository


class ClientService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ClientRepository(db)
        self.project_repo = ProjectRepository(db)
        self.perm_repo = PermissionsRepository(db)
        self.audit = AuditService(db)

    def resolve_client(self, identifier: str | uuid.UUID) -> ApiClient:
        if isinstance(identifier, uuid.UUID):
            client = self.repo.get_by_id(identifier)
        else:
            try:
                uid = uuid.UUID(str(identifier))
                client = self.repo.get_by_id(uid)
            except ValueError:
                client = self.repo.get_by_client_id(str(identifier))
        if not client:
            raise NotFoundError(message="API client not found", code="CLIENT_NOT_FOUND")
        return client

    def _resolve_scopes(self, scope_names: list[str]) -> list[Scope]:
        scopes: list[Scope] = []
        for s_name in scope_names:
            scope = self.perm_repo.get_scope_by_name(s_name)
            if not scope:
                scope = self.perm_repo.create_scope(name=s_name, description=s_name)
            scopes.append(scope)
        return scopes

    def list_clients(
        self,
        principal: Principal,
        project_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ApiClient], int]:
        if project_id:
            principal.require_project_access(project_id)
        allowed_ids = None if principal.is_admin else principal.allowed_project_ids
        offset = (page - 1) * page_size
        return self.repo.list_clients(
            project_id=project_id,
            allowed_project_ids=allowed_ids,
            offset=offset,
            limit=page_size,
        )

    def create_client(self, payload: ApiClientCreate, principal: Principal) -> ApiClient:
        project = self.project_repo.get_by_id(payload.project_id)
        if not project:
            raise NotFoundError(message="Target project not found", code="PROJECT_NOT_FOUND")
        principal.require_project_access(project.id)

        if self.repo.get_by_client_id(payload.client_id):
            raise ConflictError(
                message=f"API client '{payload.client_id}' already exists",
                code="CLIENT_ID_EXISTS",
            )

        secret_hash = hash_password(payload.client_secret) if payload.client_secret else None
        scopes = self._resolve_scopes(payload.scopes)

        client = ApiClient(
            project_id=project.id,
            client_id=payload.client_id.strip(),
            name=payload.name,
            client_type=payload.client_type,
            client_secret_hash=secret_hash,
            is_active=True,
            scopes=scopes,
        )
        created = self.repo.create_client(client)
        self.audit.record(
            action="client.created",
            resource="api_clients",
            resource_id=str(created.id),
            project_id=project.id,
            client_id=created.id,
            principal=principal,
            details={"client_id": created.client_id, "scopes": payload.scopes},
        )
        return created

    def get_client(self, client_identifier: str, principal: Principal) -> ApiClient:
        client = self.resolve_client(client_identifier)
        principal.require_project_access(client.project_id)
        return client

    def issue_api_key(
        self, client_identifier: str, payload: ApiKeyCreate, principal: Principal
    ) -> tuple[ApiKey, str]:
        client = self.resolve_client(client_identifier)
        principal.require_project_access(client.project_id)

        raw_key, key_prefix, key_hash = generate_api_key()
        expires_at = None
        if payload.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

        api_key = self.repo.create_api_key(
            ApiKey(
                client_id=client.id,
                name=payload.name,
                key_prefix=key_prefix,
                key_hash=key_hash,
                expires_at=expires_at,
            )
        )
        self.audit.record(
            action="client.api_key_issued",
            resource="api_keys",
            resource_id=str(api_key.id),
            project_id=client.project_id,
            client_id=client.id,
            principal=principal,
            details={"key_prefix": key_prefix, "name": payload.name},
        )
        return api_key, raw_key

    def revoke_api_key(
        self, client_identifier: str, key_id: uuid.UUID, principal: Principal
    ) -> ApiKey:
        client = self.resolve_client(client_identifier)
        principal.require_project_access(client.project_id)

        api_key = self.repo.get_api_key(key_id)
        if not api_key or api_key.client_id != client.id:
            raise NotFoundError(message="API key not found for this client", code="API_KEY_NOT_FOUND")

        revoked = self.repo.revoke_api_key(api_key)
        self.audit.record(
            action="client.api_key_revoked",
            resource="api_keys",
            resource_id=str(revoked.id),
            project_id=client.project_id,
            client_id=client.id,
            principal=principal,
            details={"key_prefix": revoked.key_prefix},
        )
        return revoked

    def assign_scopes(
        self, client_identifier: str, scope_names: list[str], principal: Principal
    ) -> ApiClient:
        client = self.resolve_client(client_identifier)
        principal.require_project_access(client.project_id)

        client.scopes = self._resolve_scopes(scope_names)
        updated = self.repo.save_client(client)
        self.audit.record(
            action="client.scopes_updated",
            resource="api_clients",
            resource_id=str(updated.id),
            project_id=updated.project_id,
            client_id=updated.id,
            principal=principal,
            details={"scopes": scope_names},
        )
        return updated


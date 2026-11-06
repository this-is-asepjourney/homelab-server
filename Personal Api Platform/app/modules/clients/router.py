"""HTTP router for API clients, hashed API keys, and scope assignments."""

from typing import Optional
import uuid

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import require_any_scope
from app.modules.clients.models import ApiClient
from app.modules.clients.schemas import (
    ApiClientCreate,
    ApiClientRead,
    ApiKeyCreate,
    ApiKeyIssuedResponse,
    ApiKeyRead,
    ClientScopesUpdate,
)
from app.modules.clients.service import ClientService
from app.schemas import success_response

router = APIRouter(prefix="/clients", tags=["API Clients"])


def serialize_client(client: ApiClient) -> dict:
    return ApiClientRead(
        id=client.id,
        project_id=client.project_id,
        client_id=client.client_id,
        name=client.name,
        client_type=client.client_type,
        is_active=client.is_active,
        scopes=sorted(s.name for s in client.scopes),
        created_at=client.created_at,
        updated_at=client.updated_at,
    ).model_dump(mode="json")


@router.get("")
def list_clients(
    project_id: Optional[uuid.UUID] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_any_scope("clients:read", "projects:read")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    clients, total = service.list_clients(
        principal, project_id=project_id, page=page, page_size=page_size
    )
    return success_response(
        data=[serialize_client(c) for c in clients],
        message="API clients retrieved successfully",
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def register_client(
    payload: ApiClientCreate,
    principal: Principal = Depends(require_any_scope("clients:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    client = service.create_client(payload, principal)
    return success_response(
        data=serialize_client(client),
        message="API client registered successfully",
    )


@router.get("/{client_id}")
def get_client(
    client_id: str,
    principal: Principal = Depends(require_any_scope("clients:read", "projects:read")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    client = service.get_client(client_id, principal)
    return success_response(
        data=serialize_client(client),
        message="API client retrieved successfully",
    )


@router.post("/{client_id}/keys", status_code=status.HTTP_201_CREATED)
def issue_api_key(
    client_id: str,
    payload: Optional[ApiKeyCreate] = Body(default=None),
    principal: Principal = Depends(require_any_scope("clients:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    req = payload or ApiKeyCreate()
    api_key, raw_key = service.issue_api_key(client_id, req, principal)
    issued = ApiKeyIssuedResponse(
        id=api_key.id,
        client_id=api_key.client_id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
        raw_key=raw_key,
    )
    return success_response(
        data=issued.model_dump(mode="json"),
        message="API key issued successfully. Store raw_key securely; it will not be shown again.",
    )


@router.delete("/{client_id}/keys/{key_id}")
def revoke_api_key(
    client_id: str,
    key_id: uuid.UUID,
    principal: Principal = Depends(require_any_scope("clients:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    revoked = service.revoke_api_key(client_id, key_id, principal)
    return success_response(
        data=ApiKeyRead.model_validate(revoked).model_dump(mode="json"),
        message="API key revoked successfully",
    )


@router.put("/{client_id}/scopes")
def assign_client_scopes(
    client_id: str,
    payload: ClientScopesUpdate,
    principal: Principal = Depends(require_any_scope("clients:manage", "projects:manage")),
    db: Session = Depends(get_db),
):
    service = ClientService(db)
    updated = service.assign_scopes(client_id, payload.scopes, principal)
    return success_response(
        data=serialize_client(updated),
        message="Client scopes updated successfully",
    )


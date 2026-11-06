"""FastAPI authentication and authorization dependencies (Hybrid User JWT + M2M API Keys + Device Credentials)."""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.permissions import DEFAULT_ROLES, Principal
from app.core.security import decode_access_token, hash_secret_token
from app.modules.clients.models import ApiClient, ApiKey
from app.modules.iot.models import Device, DeviceCredential
from app.modules.projects.models import Project, UserProjectMembership
from app.modules.users.models import User


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _authenticate_api_key(db: Session, raw_key: str) -> Principal:
    key_hash = hash_secret_token(raw_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    api_key = db.scalar(stmt)
    if not api_key:
        raise AuthenticationError(message="Invalid API key", code="INVALID_API_KEY")

    if api_key.revoked_at is not None:
        raise AuthenticationError(message="API key has been revoked", code="REVOKED_API_KEY")

    now = datetime.now(timezone.utc)
    expires_at = _ensure_aware(api_key.expires_at)
    if expires_at is not None and expires_at <= now:
        raise AuthenticationError(message="API key has expired", code="EXPIRED_API_KEY")

    client = db.get(ApiClient, api_key.client_id)
    if not client or not client.is_active:
        raise AuthenticationError(message="API client is inactive", code="INACTIVE_CLIENT")

    project = db.get(Project, client.project_id)
    if not project or project.status != "active":
        raise AuthenticationError(message="Owning project is inactive", code="INACTIVE_PROJECT")

    scopes = {s.name for s in client.scopes}
    return Principal(
        identity_type="client",
        subject_id=client.id,
        client_id=client.id,
        project_id=client.project_id,
        client_identifier=client.client_id,
        scopes=scopes,
        allowed_project_ids={client.project_id},
    )


def _authenticate_device_credential(db: Session, raw_credential: str) -> Principal:
    cred_hash = hash_secret_token(raw_credential)
    stmt = select(DeviceCredential).where(DeviceCredential.credential_hash == cred_hash)
    cred = db.scalar(stmt)
    if not cred:
        raise AuthenticationError(
            message="Invalid device credential", code="INVALID_DEVICE_CREDENTIAL"
        )
    if cred.revoked_at is not None:
        raise AuthenticationError(
            message="Device credential has been revoked", code="REVOKED_DEVICE_CREDENTIAL"
        )
    device = db.get(Device, cred.device_id)
    if not device or device.status == "disabled":
        raise AuthenticationError(message="Device is disabled or not found", code="INACTIVE_DEVICE")

    return Principal(
        identity_type="device",
        subject_id=device.id,
        device_id=device.id,
        device_uid=device.device_uid,
        project_id=device.project_id,
        scopes={"iot:write", "iot:read"},
        allowed_project_ids={device.project_id},
    )


def _authenticate_jwt(db: Session, token: str) -> Principal:
    payload = decode_access_token(token)
    identity_type = payload.get("identity_type", "user")
    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError(message="Token missing subject", code="INVALID_TOKEN")

    try:
        subject_uuid = uuid.UUID(str(sub))
    except ValueError as exc:
        raise AuthenticationError(message="Invalid token subject", code="INVALID_TOKEN") from exc

    if identity_type == "client":
        client = db.get(ApiClient, subject_uuid)
        if not client or not client.is_active:
            raise AuthenticationError(message="API client is inactive", code="INACTIVE_CLIENT")
        scopes = {s.name for s in client.scopes}
        return Principal(
            identity_type="client",
            subject_id=client.id,
            client_id=client.id,
            project_id=client.project_id,
            client_identifier=client.client_id,
            scopes=scopes,
            allowed_project_ids={client.project_id},
        )

    user = db.get(User, subject_uuid)
    if not user or not user.is_active:
        raise AuthenticationError(message="User account is inactive or not found", code="INACTIVE_USER")

    role_names = {r.name for r in user.roles}
    permissions: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            permissions.add(perm.name)
        if role.name in DEFAULT_ROLES:
            permissions.update(DEFAULT_ROLES[role.name])

    memberships = db.scalars(
        select(UserProjectMembership).where(UserProjectMembership.user_id == user.id)
    ).all()
    allowed_projects = {m.project_id for m in memberships}

    return Principal(
        identity_type="user",
        subject_id=user.id,
        user_id=user.id,
        email=user.email,
        roles=role_names,
        permissions=permissions,
        scopes=permissions,
        allowed_project_ids=allowed_projects,
    )


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_device_credential: Optional[str] = Header(default=None, alias="X-Device-Credential"),
) -> Principal:
    """Resolve the current Principal from X-API-Key, X-Device-Credential, or Bearer token."""
    if x_api_key:
        return _authenticate_api_key(db, x_api_key.strip())

    if x_device_credential:
        return _authenticate_device_credential(db, x_device_credential.strip())

    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationError(
                message="Invalid Authorization header format; expected Bearer <token>",
                code="INVALID_AUTH_HEADER",
            )
        token_value = parts[1].strip()
        if token_value.startswith("pap_key_"):
            return _authenticate_api_key(db, token_value)
        if token_value.startswith("pap_dev_"):
            return _authenticate_device_credential(db, token_value)
        return _authenticate_jwt(db, token_value)

    raise AuthenticationError(
        message="Authentication credentials were not provided",
        code="AUTHENTICATION_REQUIRED",
    )


def require_scopes(*required_scopes: str) -> Callable[..., Principal]:
    """Dependency factory requiring the caller to possess all specified scopes."""

    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        for scope in required_scopes:
            principal.require_scope(scope)
        return principal

    return _dependency


def require_any_scope(*required_scopes: str) -> Callable[..., Principal]:
    """Dependency factory requiring the caller to possess at least one of the specified scopes."""

    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        principal.require_any_scope(list(required_scopes))
        return principal

    return _dependency


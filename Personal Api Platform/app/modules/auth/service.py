"""Authentication service implementing hybrid user login, refresh-token rotation, and M2M client credentials."""

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.permissions import DEFAULT_ROLES, Principal
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_secret_token,
    verify_password,
)
from app.modules.audit.service import AuditService
from app.modules.auth.models import RefreshToken
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    ClientCredentialsRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.modules.clients.models import ApiClient
from app.modules.users.models import User
from app.modules.users.repository import UserRepository


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuthRepository(db)
        self.user_repo = UserRepository(db)
        self.audit = AuditService(db)
        self.settings = get_settings()

    def _build_user_claims(self, user: User) -> tuple[list[str], list[str]]:
        roles = [r.name for r in user.roles]
        perms: set[str] = set()
        for r in user.roles:
            for p in r.permissions:
                perms.add(p.name)
            if r.name in DEFAULT_ROLES:
                perms.update(DEFAULT_ROLES[r.name])
        return roles, sorted(perms)

    def login(
        self,
        payload: LoginRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> TokenResponse:
        user = self.user_repo.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            self.audit.record(
                action="auth.login_failed",
                resource="auth",
                status="failure",
                ip_address=ip_address,
                details={"email": payload.email.strip().lower()},
            )
            raise AuthenticationError(
                message="Invalid email or password",
                code="INVALID_CREDENTIALS",
            )
        if not user.is_active:
            raise AuthenticationError(
                message="User account is disabled",
                code="USER_DISABLED",
            )

        roles, perms = self._build_user_claims(user)
        access_token, expires_in = create_access_token(
            subject=str(user.id),
            identity_type="user",
            roles=roles,
            permissions=perms,
            scopes=perms,
        )

        raw_rt, rt_hash = generate_refresh_token()
        rt_expires = datetime.now(timezone.utc) + timedelta(
            days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        session_record = self.repo.create_refresh_token(
            RefreshToken(
                user_id=user.id,
                token_hash=rt_hash,
                user_agent=user_agent,
                ip_address=ip_address,
                expires_at=rt_expires,
            )
        )

        self.audit.record(
            action="auth.login",
            resource="auth",
            user_id=user.id,
            resource_id=str(session_record.id),
            ip_address=ip_address,
            details={"email": user.email},
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_rt,
            token_type="Bearer",
            expires_in=expires_in,
            session_id=session_record.id,
        )

    def authenticate_client_credentials(
        self,
        payload: ClientCredentialsRequest,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        client = self.db.scalar(
            select(ApiClient).where(ApiClient.client_id == payload.client_id.strip())
        )
        if (
            not client
            or not client.is_active
            or not client.client_secret_hash
            or not verify_password(payload.client_secret, client.client_secret_hash)
        ):
            self.audit.record(
                action="auth.client_login_failed",
                resource="auth",
                status="failure",
                ip_address=ip_address,
                details={"client_id": payload.client_id},
            )
            raise AuthenticationError(
                message="Invalid client credentials",
                code="INVALID_CLIENT_CREDENTIALS",
            )

        scopes = sorted(s.name for s in client.scopes)
        access_token, expires_in = create_access_token(
            subject=str(client.id),
            identity_type="client",
            scopes=scopes,
            project_id=str(client.project_id),
        )
        self.audit.record(
            action="auth.client_token_issued",
            resource="auth",
            client_id=client.id,
            project_id=client.project_id,
            ip_address=ip_address,
            details={"client_id": client.client_id, "scopes": scopes},
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=None,
            token_type="Bearer",
            expires_in=expires_in,
        )

    def refresh_session(
        self,
        payload: RefreshTokenRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> TokenResponse:
        token_hash = hash_secret_token(payload.refresh_token.strip())
        existing = self.repo.get_by_token_hash(token_hash)
        if not existing:
            raise AuthenticationError(
                message="Invalid refresh token",
                code="INVALID_REFRESH_TOKEN",
            )
        if existing.revoked_at is not None:
            # Reuse of a revoked refresh token revokes all user sessions as a precaution
            self.repo.revoke_all_user_sessions(existing.user_id)
            self.audit.record(
                action="auth.refresh_token_reuse_detected",
                resource="auth",
                user_id=existing.user_id,
                resource_id=str(existing.id),
                status="failure",
                ip_address=ip_address,
            )
            raise AuthenticationError(
                message="Refresh token has been revoked",
                code="REVOKED_REFRESH_TOKEN",
            )

        now = datetime.now(timezone.utc)
        if _ensure_aware(existing.expires_at) <= now:
            raise AuthenticationError(
                message="Refresh token has expired",
                code="EXPIRED_REFRESH_TOKEN",
            )

        user = self.user_repo.get_by_id(existing.user_id)
        if not user or not user.is_active:
            raise AuthenticationError(
                message="User account is inactive",
                code="INACTIVE_USER",
            )

        # Rotate refresh token: issue new one and mark old one revoked + replaced_by_id
        raw_new_rt, new_rt_hash = generate_refresh_token()
        new_rt_expires = now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        new_session = RefreshToken(
            user_id=user.id,
            token_hash=new_rt_hash,
            user_agent=user_agent or existing.user_agent,
            ip_address=ip_address or existing.ip_address,
            expires_at=new_rt_expires,
        )
        self.db.add(new_session)
        self.db.flush()

        existing.revoked_at = now
        existing.replaced_by_id = new_session.id
        self.db.commit()
        self.db.refresh(new_session)

        roles, perms = self._build_user_claims(user)
        access_token, expires_in = create_access_token(
            subject=str(user.id),
            identity_type="user",
            roles=roles,
            permissions=perms,
            scopes=perms,
        )

        self.audit.record(
            action="auth.token_refreshed",
            resource="auth",
            user_id=user.id,
            resource_id=str(new_session.id),
            ip_address=ip_address,
            details={"rotated_from": str(existing.id)},
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_new_rt,
            token_type="Bearer",
            expires_in=expires_in,
            session_id=new_session.id,
        )

    def logout(self, principal: Principal, payload: LogoutRequest) -> dict:
        revoked_count = 0
        if payload.refresh_token:
            rt_hash = hash_secret_token(payload.refresh_token.strip())
            record = self.repo.get_by_token_hash(rt_hash)
            if record and (principal.is_admin or record.user_id == principal.user_id):
                if record.revoked_at is None:
                    self.repo.revoke_session(record)
                    revoked_count += 1
        elif payload.revoke_all and principal.user_id:
            revoked_count = self.repo.revoke_all_user_sessions(principal.user_id)
        elif principal.user_id:
            sessions = self.repo.list_user_sessions(principal.user_id)
            for s in sessions:
                if s.revoked_at is None:
                    self.repo.revoke_session(s)
                    revoked_count += 1
                    break

        self.audit.record(
            action="auth.logout",
            resource="auth",
            principal=principal,
            details={"revoked_sessions": revoked_count},
        )
        return {"revoked_sessions": revoked_count}

    def list_sessions(self, principal: Principal) -> list[RefreshToken]:
        if not principal.user_id:
            return []
        return self.repo.list_user_sessions(principal.user_id)

    def revoke_session_by_id(self, principal: Principal, session_id: uuid.UUID) -> RefreshToken:
        record = self.repo.get_by_id(session_id)
        if not record:
            raise NotFoundError(message="Session not found", code="SESSION_NOT_FOUND")
        if not principal.is_admin and record.user_id != principal.user_id:
            raise PermissionDeniedError(
                message="Cannot revoke another user's session",
                code="SESSION_ACCESS_DENIED",
            )
        revoked = self.repo.revoke_session(record)
        self.audit.record(
            action="auth.session_revoked",
            resource="auth_sessions",
            resource_id=str(session_id),
            principal=principal,
        )
        return revoked


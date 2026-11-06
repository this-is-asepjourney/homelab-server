"""HTTP router for authentication, refresh-token rotation, and session management."""

from typing import Optional
import uuid

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.dependencies import get_current_principal
from app.modules.auth.schemas import (
    ClientCredentialsRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    SessionRead,
)
from app.modules.auth.service import AuthService
from app.schemas import success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    token_resp = service.login(payload, ip_address=ip, user_agent=ua)
    return success_response(
        data=token_resp.model_dump(mode="json"),
        message="Authenticated successfully",
    )


@router.post("/token")
def issue_client_token(
    payload: ClientCredentialsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    ip = request.client.host if request.client else None
    token_resp = service.authenticate_client_credentials(payload, ip_address=ip)
    return success_response(
        data=token_resp.model_dump(mode="json"),
        message="Client access token issued successfully",
    )


@router.post("/refresh")
def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    token_resp = service.refresh_session(payload, ip_address=ip, user_agent=ua)
    return success_response(
        data=token_resp.model_dump(mode="json"),
        message="Access token refreshed successfully",
    )


@router.post("/logout")
def logout(
    payload: Optional[LogoutRequest] = Body(default=None),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    req = payload or LogoutRequest()
    result = service.logout(principal, req)
    return success_response(data=result, message="Session logged out successfully")


@router.get("/me")
def get_me(
    principal: Principal = Depends(get_current_principal),
):
    return success_response(
        data={
            "identity_type": principal.identity_type,
            "subject_id": str(principal.subject_id),
            "user_id": str(principal.user_id) if principal.user_id else None,
            "client_id": str(principal.client_id) if principal.client_id else None,
            "device_id": str(principal.device_id) if principal.device_id else None,
            "device_uid": principal.device_uid,
            "project_id": str(principal.project_id) if principal.project_id else None,
            "email": principal.email,
            "client_identifier": principal.client_identifier,
            "roles": sorted(principal.roles),
            "permissions": sorted(principal.permissions),
            "scopes": sorted(principal.scopes),
            "allowed_project_ids": [str(pid) for pid in sorted(principal.allowed_project_ids, key=str)],
        },
        message="Current identity retrieved successfully",
    )


@router.get("/sessions")
def list_sessions(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    sessions = service.list_sessions(principal)
    data = [SessionRead.model_validate(s).model_dump(mode="json") for s in sessions]
    return success_response(data=data, message="Sessions retrieved successfully")


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    revoked = service.revoke_session_by_id(principal, session_id)
    return success_response(
        data=SessionRead.model_validate(revoked).model_dump(mode="json"),
        message="Session revoked successfully",
    )


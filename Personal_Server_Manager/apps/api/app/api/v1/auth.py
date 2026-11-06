from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.config import settings
from apps.api.app.core.security import (
    verify_password,
    hash_password,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from apps.api.app.core.dependencies import get_current_user, get_client_ip
from apps.api.app.models.entities import User, UserSession
from apps.api.app.schemas.all_schemas import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    PasswordChangeRequest,
    UserResponse,
)
from apps.api.app.services.audit_service import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Store hashed refresh token in session
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_token(refresh_token),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=get_client_ip(request),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    db.commit()

    log_activity(
        db,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
        ip_address=get_client_ip(request),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }

@router.post("/refresh")
def refresh_session(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    decoded = decode_token(payload.refresh_token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = decoded.get("sub")
    token_hashed = hash_token(payload.refresh_token)
    session = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.refresh_token_hash == token_hashed
    ).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User disabled or not found")

    new_access_token = create_access_token(subject=user.id)
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Invalidate all user sessions
    db.query(UserSession).filter(UserSession.user_id == current_user.id).delete()
    db.commit()
    log_activity(
        db,
        action="auth.logout",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id
    )
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.updated_at = datetime.now(timezone.utc)
    # Revoke existing sessions
    db.query(UserSession).filter(UserSession.user_id == current_user.id).delete()
    db.commit()

    log_activity(
        db,
        action="auth.change_password",
        resource_type="user",
        resource_id=current_user.id,
        user_id=current_user.id
    )
    return {"message": "Password changed successfully. Please log in again."}


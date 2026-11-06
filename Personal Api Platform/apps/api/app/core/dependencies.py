from typing import Optional
from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.security import decode_token, hash_token
from apps.api.app.models.entities import User, Agent, Server, AgentToken

security = HTTPBearer(auto_error=False)

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def resolve_server(db: Session, server_id: str) -> Optional[Server]:
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server and server_id in ("homelab-primary", "default-server"):
        server = db.query(Server).filter(Server.name == "Homelab-Primary").first()
        if not server:
            server = db.query(Server).order_by(Server.created_at.asc()).first()
    return server

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(auth.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated"
        )
    return user

def require_role(*allowed_roles: str):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles and user.role != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires one of {allowed_roles}"
            )
        return user
    return role_checker

def get_current_agent(
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    x_server_id: Optional[str] = Header(None, alias="X-Server-Id"),
    db: Session = Depends(get_db)
) -> Server:
    if not x_agent_token or not x_server_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent authentication required (X-Agent-Token & X-Server-Id)"
        )
    hashed = hash_token(x_agent_token)
    server = resolve_server(db, x_server_id)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
        
    # Check registered agent or token
    token_valid = False
    if server.agent and server.agent.credential_hash == hashed and not server.agent.revoked_at:
        token_valid = True
    else:
        db_token = db.query(AgentToken).filter(
            AgentToken.server_id == server.id,
            AgentToken.token_hash == hashed
        ).first()
        if db_token:
            token_valid = True
            
    if not token_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked agent credentials"
        )
    return server

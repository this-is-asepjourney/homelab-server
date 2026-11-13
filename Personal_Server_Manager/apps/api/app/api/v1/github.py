from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from apps.api.app.database.session import get_db
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import User
from apps.api.app.services.audit_service import log_activity
from apps.api.app.services.github_service import (
    get_stored_token,
    save_github_token,
    remove_github_token,
    get_github_profile,
    list_user_repositories,
    list_repository_branches,
    create_repo_webhook,
)

router = APIRouter(prefix="/github", tags=["GitHub Integration"])


class ConnectTokenRequest(BaseModel):
    token: str


class WebhookSetupRequest(BaseModel):
    owner: str
    repo: str
    webhook_url: str
    secret: Optional[str] = None


@router.get("/status")
def get_github_status(current_user: User = Depends(get_current_user)):
    """Check if GitHub is connected and return profile details."""
    token = get_stored_token()
    if not token:
        return {
            "connected": False,
            "message": "GitHub belum terhubung. Masukkan Personal Access Token (PAT) untuk mengaktifkan integrasi penuh."
        }

    try:
        profile = get_github_profile(token)
        # Masked token for display (e.g. ghp_...1234)
        preview = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
        return {
            "connected": True,
            "token_preview": preview,
            "user": profile,
            "scopes": profile.get("scopes", []),
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "message": "Token GitHub tersimpan tetapi tidak valid atau kadaluarsa."
        }


@router.post("/connect")
def connect_github(
    payload: ConnectTokenRequest,
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    """Validate and store GitHub Personal Access Token."""
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token GitHub tidak boleh kosong.")

    try:
        profile = get_github_profile(token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal verifikasi token GitHub: {str(e)}")

    success = save_github_token(token)
    if not success:
        raise HTTPException(status_code=500, detail="Gagal menyimpan token ke penyimpanan server.")

    log_activity(
        db,
        action="github.connect",
        resource_type="integration",
        resource_id=profile.get("login") or "github",
        user_id=current_user.id,
        details={"username": profile.get("login"), "public_repos": profile.get("public_repos")}
    )

    return {
        "status": "success",
        "message": f"Berhasil menghubungkan akun GitHub ({profile.get('login')}) dengan akses penuh!",
        "user": profile
    }


@router.post("/disconnect")
def disconnect_github(
    current_user: User = Depends(require_role("owner", "admin")),
    db: Session = Depends(get_db)
):
    """Disconnect GitHub integration."""
    remove_github_token()
    log_activity(
        db,
        action="github.disconnect",
        resource_type="integration",
        resource_id="github",
        user_id=current_user.id
    )
    return {
        "status": "success",
        "message": "Integrasi GitHub berhasil diputuskan."
    }


@router.get("/repos")
def get_repositories(current_user: User = Depends(get_current_user)):
    """List all accessible repositories for the connected GitHub account."""
    token = get_stored_token()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub belum terhubung.")

    try:
        repos = list_user_repositories(token)
        return {
            "total": len(repos),
            "repositories": repos
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/repos/{owner}/{repo}/branches")
def get_repository_branches(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user)
):
    """List branch names for a repository."""
    token = get_stored_token()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub belum terhubung.")

    try:
        branches = list_repository_branches(owner, repo, token)
        return {
            "owner": owner,
            "repo": repo,
            "branches": branches
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/repos/webhook")
def setup_webhook_on_github(
    payload: WebhookSetupRequest,
    current_user: User = Depends(require_role("owner", "admin", "operator")),
    db: Session = Depends(get_db)
):
    """Automatically create webhook in GitHub repository."""
    token = get_stored_token()
    if not token:
        raise HTTPException(status_code=400, detail="GitHub belum terhubung.")

    try:
        hook_data = create_repo_webhook(
            owner=payload.owner,
            repo=payload.repo,
            payload_url=payload.webhook_url,
            secret=payload.secret,
            token=token
        )
        log_activity(
            db,
            action="github.setup_webhook",
            resource_type="webhook",
            resource_id=f"{payload.owner}/{payload.repo}",
            user_id=current_user.id,
            details={"hook_id": hook_data.get("id"), "url": payload.webhook_url}
        )
        return {
            "status": "success",
            "message": f"Webhook otomatis berhasil dipasang di GitHub {payload.owner}/{payload.repo}!",
            "hook": hook_data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from apps.api.app.core.config import settings
from apps.api.app.core.security import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)

GITHUB_SETTINGS_FILE = os.path.join(settings.STORAGE_BASE_DIR, "github_settings.json")


def get_stored_token() -> Optional[str]:
    """Retrieve decrypted GitHub token from storage or environment variable."""
    env_token = os.getenv("GITHUB_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()

    if not os.path.exists(GITHUB_SETTINGS_FILE):
        return None

    try:
        with open(GITHUB_SETTINGS_FILE, "r") as f:
            data = json.load(f)
            encrypted = data.get("encrypted_token")
            if encrypted:
                return decrypt_secret(encrypted)
    except Exception as e:
        logger.warning(f"Failed to read GitHub settings file: {e}")

    return None


def save_github_token(token: str) -> bool:
    """Save encrypted GitHub token to persistent storage."""
    try:
        os.makedirs(settings.STORAGE_BASE_DIR, exist_ok=True)
        encrypted = encrypt_secret(token.strip())
        with open(GITHUB_SETTINGS_FILE, "w") as f:
            json.dump({"encrypted_token": encrypted}, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save GitHub token: {e}")
        return False


def remove_github_token() -> bool:
    """Remove GitHub token from persistent storage."""
    try:
        if os.path.exists(GITHUB_SETTINGS_FILE):
            os.remove(GITHUB_SETTINGS_FILE)
        return True
    except Exception as e:
        logger.error(f"Failed to delete GitHub settings file: {e}")
        return False


def github_api_request(
    endpoint: str,
    method: str = "GET",
    token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute authenticated GitHub REST API request."""
    tok = token or get_stored_token()
    if not tok:
        raise ValueError("GitHub token tidak ditemukan. Hubungkan GitHub token terlebih dahulu.")

    url = f"https://api.github.com{endpoint}" if endpoint.startswith("/") else endpoint
    data_bytes = json.dumps(payload).encode("utf-8") if payload else None

    req = urllib.request.Request(url, data=data_bytes, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "Homelab-PSM-Server/2.0")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if payload:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            body = resp.read().decode("utf-8")
            scopes_header = resp.headers.get("X-OAuth-Scopes", "")
            scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
            parsed = json.loads(body) if body else {}
            return {
                "data": parsed,
                "status_code": resp.status,
                "scopes": scopes
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("message", err_body)
        except Exception:
            msg = err_body or str(e)
        raise RuntimeError(f"GitHub API Error ({e.code}): {msg}")
    except Exception as e:
        raise RuntimeError(f"Gagal menghubungi GitHub API: {str(e)}")


def get_github_profile(token: Optional[str] = None) -> Dict[str, Any]:
    """Validate token and retrieve connected GitHub user profile."""
    res = github_api_request("/user", token=token)
    user_data = res.get("data", {})
    return {
        "login": user_data.get("login"),
        "id": user_data.get("id"),
        "name": user_data.get("name") or user_data.get("login"),
        "avatar_url": user_data.get("avatar_url"),
        "html_url": user_data.get("html_url"),
        "public_repos": user_data.get("public_repos", 0),
        "total_private_repos": user_data.get("total_private_repos", 0),
        "scopes": res.get("scopes", []),
    }


def list_user_repositories(token: Optional[str] = None) -> List[Dict[str, Any]]:
    """List accessible GitHub repositories (public and private) sorted by update time."""
    res = github_api_request("/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator", token=token)
    repos = res.get("data", [])
    result = []
    for r in repos:
        result.append({
            "id": r.get("id"),
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "private": r.get("private", False),
            "html_url": r.get("html_url"),
            "clone_url": r.get("clone_url"),
            "default_branch": r.get("default_branch") or "main",
            "description": r.get("description"),
            "language": r.get("language"),
            "updated_at": r.get("updated_at"),
            "visibility": r.get("visibility", "private" if r.get("private") else "public"),
        })
    return result


def list_repository_branches(owner: str, repo: str, token: Optional[str] = None) -> List[str]:
    """List branch names for a specific repository."""
    res = github_api_request(f"/repos/{owner}/{repo}/branches?per_page=100", token=token)
    branches = res.get("data", [])
    return [b.get("name") for b in branches if b.get("name")]


def create_repo_webhook(
    owner: str,
    repo: str,
    payload_url: str,
    secret: Optional[str] = None,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """Create push webhook on a GitHub repository."""
    payload = {
        "name": "web",
        "active": True,
        "events": ["push"],
        "config": {
            "url": payload_url,
            "content_type": "json",
            "insecure_ssl": "1",  # Support LAN/Self-signed certs
        }
    }
    if secret:
        payload["config"]["secret"] = secret

    res = github_api_request(f"/repos/{owner}/{repo}/hooks", method="POST", token=token, payload=payload)
    return res.get("data", {})


def inject_auth_into_git_url(repo_url: str, token: Optional[str] = None) -> str:
    """Inject x-access-token into GitHub HTTPS URL for seamless private repo cloning."""
    tok = token or get_stored_token()
    if not tok or not repo_url or "github.com" not in repo_url:
        return repo_url

    # Clean any existing auth info
    if "@github.com" in repo_url:
        return repo_url

    clean_url = repo_url
    if clean_url.startswith("https://github.com/"):
        return clean_url.replace("https://github.com/", f"https://x-access-token:{tok}@github.com/")
    elif clean_url.startswith("http://github.com/"):
        return clean_url.replace("http://github.com/", f"https://x-access-token:{tok}@github.com/")

    return repo_url

"""Cryptographic security utilities: Argon2id password hashing, JWT, API keys, and device credentials."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Optional
import uuid

import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

try:
    from pwdlib import PasswordHash

    _pwd_hasher = PasswordHash.recommended()
except Exception:  # pragma: no cover - fallback when pwdlib[argon2] is not installed locally
    _pwd_hasher = None


def hash_password(password: str) -> str:
    """Hash a user password using Argon2id (or scrypt fallback if Argon2 C extension is absent)."""
    if _pwd_hasher is not None:
        return _pwd_hasher.hash(password)
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(derived).decode("ascii")
    return f"$scrypt$n=16384,r=8,p=1${salt_b64}${dk_b64}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored password hash in constant time."""
    if not plain_password or not password_hash:
        return False
    if password_hash.startswith("$scrypt$"):
        try:
            parts = password_hash.split("$")
            salt = base64.b64decode(parts[3])
            expected = base64.b64decode(parts[4])
            derived = hashlib.scrypt(
                plain_password.encode("utf-8"),
                salt=salt,
                n=16384,
                r=8,
                p=1,
                dklen=len(expected),
            )
            return hmac.compare_digest(derived, expected)
        except Exception:
            return False
    if _pwd_hasher is not None:
        try:
            return _pwd_hasher.verify(plain_password, password_hash)
        except Exception:
            return False
    return False


def hash_secret_token(raw_token: str) -> str:
    """Compute a SHA-256 hex digest of a high-entropy token (API key, refresh token, device credential)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_secret_token(raw_token: str, expected_hash: str) -> bool:
    """Verify a raw token against its SHA-256 hex digest using constant-time comparison."""
    if not raw_token or not expected_hash:
        return False
    computed = hash_secret_token(raw_token)
    return hmac.compare_digest(computed, expected_hash)


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (raw_key, key_prefix, key_hash)."""
    token_part = secrets.token_urlsafe(32)
    raw_key = f"pap_key_{token_part}"
    key_prefix = raw_key[:16]
    key_hash = hash_secret_token(raw_key)
    return raw_key, key_prefix, key_hash


def generate_refresh_token() -> tuple[str, str]:
    """Generate a refresh token. Returns (raw_token, token_hash)."""
    raw_token = f"pap_rt_{secrets.token_urlsafe(40)}"
    return raw_token, hash_secret_token(raw_token)


def generate_device_credential() -> tuple[str, str]:
    """Generate a per-device credential. Returns (raw_credential, credential_hash)."""
    raw_cred = f"pap_dev_{secrets.token_urlsafe(32)}"
    return raw_cred, hash_secret_token(raw_cred)


def create_access_token(
    subject: str,
    identity_type: str = "user",
    roles: Optional[list[str]] = None,
    permissions: Optional[list[str]] = None,
    scopes: Optional[list[str]] = None,
    project_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    """Create a signed JWT access token with issuer, audience, expiry, and claims."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = now + delta

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "identity_type": identity_type,
        "roles": roles or [],
        "permissions": permissions or [],
        "scopes": scopes or [],
    }
    if project_id:
        payload["project_id"] = str(project_id)

    encoded = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded, int(delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate and decode a PAP JWT access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            message="Access token has expired",
            code="TOKEN_EXPIRED",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(
            message="Invalid access token",
            code="INVALID_TOKEN",
        ) from exc


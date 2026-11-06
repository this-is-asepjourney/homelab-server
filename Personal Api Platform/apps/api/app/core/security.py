import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
try:
    import jwt
except ImportError:
    from jose import jwt  # type: ignore
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from apps.api.app.core.config import settings

ph = PasswordHasher()

def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return ph.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        # Fallback check for plain sha256 or bcrypt if migrated
        return False

def hash_token(token: str) -> str:
    """SHA-256 hash for storing refresh tokens or agent credentials safely."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
    to_encode = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except Exception:
        return None

# --- Fernet Encryption for Environment Variables ---
def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_MASTER_KEY.encode()
    if len(key) != 44:
        # Generate valid 32-byte urlsafe base64 key from sha256
        key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
    return Fernet(key)

def encrypt_secret(plain_text: str) -> str:
    """Encrypt sensitive string into ciphertext."""
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_secret(ciphertext: str) -> str:
    """Decrypt ciphertext back to plaintext."""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


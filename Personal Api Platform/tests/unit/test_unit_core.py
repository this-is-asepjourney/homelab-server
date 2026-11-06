"""Unit tests for core security, permissions, config validation, and log redaction."""

from datetime import timedelta
import uuid

import pytest

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, BadRequestError, PermissionDeniedError
from app.core.logging import redact_value
from app.core.permissions import Principal
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    verify_password,
    verify_secret_token,
)
from app.integrations.mysql import MySQLReadOnlyAdapter
from app.integrations.prometheus import PrometheusAdapter
from app.modules.database_registry.schemas import DatabaseConnectionCreate


def test_password_hashing_and_verification():
    hashed = hash_password("MySecretPass#2026")
    assert hashed != "MySecretPass#2026"
    assert verify_password("MySecretPass#2026", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_api_key_generation_and_hash_verification():
    raw_key, prefix, key_hash = generate_api_key()
    assert raw_key.startswith("pap_key_")
    assert prefix == raw_key[:16]
    assert key_hash != raw_key
    assert verify_secret_token(raw_key, key_hash) is True
    assert verify_secret_token("pap_key_wrong", key_hash) is False


def test_jwt_create_and_decode():
    uid = str(uuid.uuid4())
    token, expires_in = create_access_token(
        subject=uid,
        identity_type="user",
        roles=["developer"],
        scopes=["projects:read"],
    )
    assert expires_in > 0
    decoded = decode_access_token(token)
    assert decoded["sub"] == uid
    assert decoded["identity_type"] == "user"
    assert "projects:read" in decoded["scopes"]


def test_jwt_expired_rejected():
    token, _ = create_access_token(
        subject=str(uuid.uuid4()),
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(AuthenticationError) as exc_info:
        decode_access_token(token)
    assert exc_info.value.code == "TOKEN_EXPIRED"


def test_principal_scope_and_project_isolation():
    proj_a = uuid.uuid4()
    proj_b = uuid.uuid4()
    principal = Principal(
        identity_type="client",
        subject_id=uuid.uuid4(),
        project_id=proj_a,
        scopes={"inventory:read"},
        allowed_project_ids={proj_a},
    )
    principal.require_scope("inventory:read")
    principal.require_project_access(proj_a)

    with pytest.raises(PermissionDeniedError) as scope_err:
        principal.require_scope("inventory:write")
    assert scope_err.value.code == "INSUFFICIENT_SCOPE"

    with pytest.raises(PermissionDeniedError) as proj_err:
        principal.require_project_access(proj_b)
    assert proj_err.value.code == "CROSS_PROJECT_ACCESS_DENIED"


def test_psm_database_protection_guard():
    settings = Settings(
        PAP_DATABASE_URL="postgresql+psycopg://appuser:secret@100.106.63.90:5432/psm",
        ALLOW_PSM_AS_PAP_CORE=False,
    )
    with pytest.raises(RuntimeError, match="Refusing to use 'psm'"):
        settings.validate_core_database_target()

    safe_settings = Settings(
        PAP_DATABASE_URL="postgresql+psycopg://pap_user:secret@100.106.63.90:5432/pap_core",
    )
    safe_settings.validate_core_database_target()


def test_mysql_adapter_rejects_root_identity():
    with pytest.raises(PermissionDeniedError) as exc_info:
        MySQLReadOnlyAdapter(username="root")
    assert exc_info.value.code == "PRIVILEGED_DB_USER_FORBIDDEN"


def test_database_connection_schema_rejects_raw_password_and_root():
    with pytest.raises(ValueError, match="secret_reference"):
        DatabaseConnectionCreate(
            project_id=uuid.uuid4(),
            name="bad-secret-conn",
            engine="mysql",
            database_name="stock_umkm",
            username="pap_stock_reader",
            secret_reference="my-plaintext-password-123",
        )

    with pytest.raises(ValueError, match="Privileged database account"):
        DatabaseConnectionCreate(
            project_id=uuid.uuid4(),
            name="bad-root-conn",
            engine="mysql",
            database_name="stock_umkm",
            username="root",
            secret_reference="STOCK_DB_PASSWORD",
        )


def test_promql_validation():
    assert PrometheusAdapter.validate_promql('up{job="prometheus"}') == 'up{job="prometheus"}'
    with pytest.raises(BadRequestError):
        PrometheusAdapter.validate_promql("up; DROP TABLE users;--")


def test_secret_redaction_in_structured_logs():
    raw_data = {
        "user": "admin@homelab.local",
        "password": "SuperSecretPassword123",
        "nested": {
            "raw_key": "pap_key_secret123",
            "api_key": "12345",
            "normal_field": "visible_value",
        },
    }
    redacted = redact_value(raw_data)
    assert redacted["password"] == "***REDACTED***"
    assert redacted["nested"]["raw_key"] == "***REDACTED***"
    assert redacted["nested"]["api_key"] == "***REDACTED***"
    assert redacted["nested"]["normal_field"] == "visible_value"


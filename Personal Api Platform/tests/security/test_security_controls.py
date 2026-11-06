"""Security tests verifying authentication, RBAC/scopes, isolation, anti-spoofing, and SQL guards."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.middleware import SlidingWindowRateLimiter
from app.core.security import create_access_token
from app.services.bootstrap import seed_platform_registry


def test_invalid_and_expired_tokens_rejected(client: TestClient):
    # No token
    res_no_auth = client.get("/api/v1/projects")
    assert res_no_auth.status_code == 401
    assert res_no_auth.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    # Tampered/invalid JWT
    res_bad_jwt = client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert res_bad_jwt.status_code == 401
    assert res_bad_jwt.json()["error"]["code"] == "INVALID_TOKEN"

    # Expired JWT
    expired_jwt, _ = create_access_token(
        subject="00000000-0000-0000-0000-000000000001",
        expires_delta=timedelta(minutes=-5),
    )
    res_exp = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {expired_jwt}"},
    )
    assert res_exp.status_code == 401
    assert res_exp.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_revoked_api_key_rejected(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)
    issue_res = client.post(
        "/api/v1/clients/pos-cashier-backend/keys",
        headers=admin_headers,
        json={"name": "temp-key"},
    )
    key_id = issue_res.json()["data"]["id"]
    raw_key = issue_res.json()["data"]["raw_key"]

    # Works before revocation
    ok_res = client.get(
        "/api/v1/integrations/stock-umkm/products",
        headers={"X-API-Key": raw_key},
    )
    assert ok_res.status_code == 200

    # Revoke key
    rev_res = client.delete(
        f"/api/v1/clients/pos-cashier-backend/keys/{key_id}",
        headers=admin_headers,
    )
    assert rev_res.status_code == 200

    # Rejected after revocation
    fail_res = client.get(
        "/api/v1/integrations/stock-umkm/products",
        headers={"X-API-Key": raw_key},
    )
    assert fail_res.status_code == 401
    assert fail_res.json()["error"]["code"] == "REVOKED_API_KEY"


def test_missing_scope_and_cross_project_access_rejected(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)

    # Issue key for POS Cashier (has inventory:read, NOT iot:manage or docker:restart)
    issue_res = client.post(
        "/api/v1/clients/pos-cashier-backend/keys",
        headers=admin_headers,
        json={"name": "pos-scoped-key"},
    )
    pos_key = issue_res.json()["data"]["raw_key"]
    pos_headers = {"X-API-Key": pos_key}

    # Missing scope: POS Cashier attempting to access IoT devices -> 403 INSUFFICIENT_SCOPE
    iot_res = client.get("/api/v1/iot/devices", headers=pos_headers)
    assert iot_res.status_code == 403
    assert iot_res.json()["error"]["code"] == "INSUFFICIENT_SCOPE"

    # Grant projects:read to pos-cashier-backend, then attempt cross-project access to stock-umkm
    client.put(
        "/api/v1/clients/pos-cashier-backend/scopes",
        headers=admin_headers,
        json={"scopes": ["projects:read", "inventory:read"]},
    )
    cross_res = client.get("/api/v1/projects/stock-umkm", headers=pos_headers)
    assert cross_res.status_code == 403
    assert cross_res.json()["error"]["code"] == "CROSS_PROJECT_ACCESS_DENIED"


def test_sql_injection_and_unrestricted_query_blocked(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)
    conns = client.get("/api/v1/database/connections", headers=admin_headers).json()["data"]
    conn_id = conns[0]["id"]

    # 1. Unrestricted SQL endpoint is explicitly forbidden
    query_res = client.post(
        "/api/v1/database/query",
        headers=admin_headers,
        json={"sql": "SELECT * FROM users;"},
    )
    assert query_res.status_code == 403
    assert query_res.json()["error"]["code"] == "UNRESTRICTED_SQL_FORBIDDEN"

    # 2. SQL injection attempt in schema table parameter is rejected
    sqli_res = client.get(
        f"/api/v1/database/sources/{conn_id}/schema?table=products;DROP TABLE users--",
        headers=admin_headers,
    )
    assert sqli_res.status_code == 400
    assert sqli_res.json()["error"]["code"] == "INVALID_TABLE_IDENTIFIER"

    # 3. Non-allowlisted table inspection is rejected
    unapproved_res = client.get(
        f"/api/v1/database/sources/{conn_id}/schema?table=users",
        headers=admin_headers,
    )
    assert unapproved_res.status_code == 403
    assert unapproved_res.json()["error"]["code"] == "TABLE_NOT_ALLOWLISTED"


def test_unauthorized_device_telemetry_and_spoofing_blocked(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)
    iot_proj = client.get("/api/v1/projects/iot-dashboard", headers=admin_headers).json()["data"]

    dev1 = client.post(
        "/api/v1/iot/devices",
        headers=admin_headers,
        json={"project_id": iot_proj["id"], "device_uid": "ESP32-DEV-01"},
    ).json()["data"]
    dev2 = client.post(
        "/api/v1/iot/devices",
        headers=admin_headers,
        json={"project_id": iot_proj["id"], "device_uid": "ESP32-DEV-02"},
    ).json()["data"]

    # Device 1 attempts to spoof telemetry for Device 2 by changing payload device_id
    spoof_res = client.post(
        "/api/v1/iot/devices/ESP32-DEV-02/telemetry",
        headers={"X-Device-Credential": dev1["raw_credential"]},
        json={
            "device_id": "ESP32-DEV-02",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": 99.9,
        },
    )
    assert spoof_res.status_code == 403
    assert spoof_res.json()["error"]["code"] == "DEVICE_IDENTITY_MISMATCH"

    # Device 1 attempts to send payload claiming to be ESP32-DEV-02 to its own endpoint
    spoof_payload_res = client.post(
        "/api/v1/iot/devices/ESP32-DEV-01/telemetry",
        headers={"X-Device-Credential": dev1["raw_credential"]},
        json={
            "device_id": "ESP32-DEV-02",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": 99.9,
        },
    )
    assert spoof_payload_res.status_code == 403
    assert spoof_payload_res.json()["error"]["code"] == "DEVICE_IDENTITY_MISMATCH"

    # Device credential rotation immediately invalidates old credential
    rot_res = client.post(
        f"/api/v1/iot/devices/{dev2['id']}/credentials/rotate",
        headers=admin_headers,
    )
    assert rot_res.status_code == 200
    old_cred_res = client.post(
        "/api/v1/iot/devices/ESP32-DEV-02/telemetry",
        headers={"X-Device-Credential": dev2["raw_credential"]},
        json={
            "device_id": "ESP32-DEV-02",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": 40.0,
        },
    )
    assert old_cred_res.status_code == 401
    assert old_cred_res.json()["error"]["code"] == "REVOKED_DEVICE_CREDENTIAL"


def test_unauthorized_docker_operation_and_default_disabled_guard(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)
    issue_res = client.post(
        "/api/v1/clients/iot-dashboard-backend/keys",
        headers=admin_headers,
        json={"name": "iot-key"},
    )
    iot_key = issue_res.json()["data"]["raw_key"]

    # Client without docker:restart is rejected with 403
    unauth_docker = client.post(
        "/api/v1/docker/containers/pap-api/restart",
        headers={"X-API-Key": iot_key},
    )
    assert unauth_docker.status_code == 403
    assert unauth_docker.json()["error"]["code"] == "INSUFFICIENT_SCOPE"

    # Even for admin, Docker management is disabled by default in initial release
    disabled_docker = client.post(
        "/api/v1/docker/containers/pap-api/restart",
        headers=admin_headers,
    )
    assert disabled_docker.status_code == 503
    assert disabled_docker.json()["error"]["code"] == "DOCKER_EXECUTOR_DISABLED"


def test_rate_limiter_sliding_window():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("client-1")[0] is True
    assert limiter.is_allowed("client-1")[0] is True
    assert limiter.is_allowed("client-1")[0] is True
    allowed, retry_after = limiter.is_allowed("client-1")
    assert allowed is False
    assert retry_after >= 1


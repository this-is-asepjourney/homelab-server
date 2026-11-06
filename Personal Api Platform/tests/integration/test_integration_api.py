"""Integration tests covering PAP endpoints, ERD persistence, Stock UMKM, POS, IoT, and Monitoring."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.services.bootstrap import seed_platform_registry


def test_system_health_and_readiness(client: TestClient):
    res_health = client.get("/health")
    assert res_health.status_code == 200
    body = res_health.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert "X-Request-ID" in res_health.headers

    res_ready = client.get("/api/v1/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["data"]["status"] == "ready"

    res_info = client.get("/api/v1/system/info")
    assert res_info.status_code == 200
    assert res_info.json()["data"]["architecture"] == "Modular Monolith"

    res_ver = client.get("/api/v1/system/version")
    assert res_ver.status_code == 200
    assert res_ver.json()["data"]["api_version"] == "v1"


def test_all_erd_tables_created(db_session: Session):
    inspector = inspect(db_session.get_bind())
    tables = set(inspector.get_table_names())
    expected_erd_tables = {
        "users",
        "projects",
        "user_project_memberships",
        "api_clients",
        "api_keys",
        "scopes",
        "client_scopes",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "database_connections",
        "integrations",
        "devices",
        "device_credentials",
        "refresh_tokens",
        "audit_logs",
        "webhook_subscriptions",
        "webhook_deliveries",
    }
    assert expected_erd_tables.issubset(tables)


def test_auth_login_refresh_rotation_and_sessions(client: TestClient, db_session: Session):
    # Create admin user via fixture or login flow
    from app.modules.users.schemas import UserCreate
    from app.modules.users.service import UserService

    UserService(db_session).create_user(
        UserCreate(
            email="operator@homelab.local",
            password="OperatorPassword!123",
            full_name="Homelab Operator",
            roles=["operator"],
        )
    )

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "operator@homelab.local", "password": "OperatorPassword!123"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()["data"]
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Inspect /auth/me
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["data"]["email"] == "operator@homelab.local"
    assert "operator" in me_res.json()["data"]["roles"]

    # List sessions
    sess_res = client.get("/api/v1/auth/sessions", headers=headers)
    assert sess_res.status_code == 200
    assert len(sess_res.json()["data"]) == 1

    # Rotate refresh token
    refresh_res = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()["data"]
    assert new_tokens["refresh_token"] != refresh_token

    # Logout with new refresh token
    logout_res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["data"]["revoked_sessions"] == 1


def test_bootstrap_projects_and_stock_umkm_pos_workflow(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    # Seed Phase 3 projects (Stock UMKM, POS Cashier, IoT Dashboard, Personal Server Manager)
    seed_result = seed_platform_registry(db_session)
    assert seed_result["projects_created"] == 4
    assert seed_result["clients_created"] == 4
    assert seed_result["devices_seeded"] == 3

    # Issue an API key for POS Cashier backend client
    key_res = client.post(
        "/api/v1/clients/pos-cashier-backend/keys",
        headers=admin_headers,
        json={"name": "pos-prod-key", "expires_in_days": 30},
    )
    assert key_res.status_code == 201
    raw_pos_key = key_res.json()["data"]["raw_key"]
    pos_headers = {"X-API-Key": raw_pos_key}

    # POS Cashier reads Stock UMKM products and inventory using its API key
    prod_res = client.get("/api/v1/integrations/stock-umkm/products", headers=pos_headers)
    assert prod_res.status_code == 200
    products = prod_res.json()["data"]
    assert any(p["product_id"] == "123" for p in products)

    # Create a webhook subscription on POS Cashier project for inventory.updated events
    proj_res = client.get("/api/v1/projects/pos-cashier", headers=admin_headers)
    pos_project_id = proj_res.json()["data"]["id"]

    wh_res = client.post(
        "/api/v1/webhooks",
        headers=admin_headers,
        json={
            "project_id": pos_project_id,
            "event_type": "inventory.updated",
            "target_reference": "http://192.168.25.101:3000/api/webhooks/inventory",
            "secret_reference": "POS_WEBHOOK_SECRET",
        },
    )
    assert wh_res.status_code == 201
    webhook_id = wh_res.json()["data"]["id"]

    # Stock UMKM publishes an inventory.updated event (per Blueprint Section 9.1)
    event_payload = {
        "event_id": "evt-stock-0001",
        "event_type": "inventory.updated",
        "source": "stock_umkm",
        "occurred_at": "2026-11-02T07:30:00+07:00",
        "data": {"product_id": "123", "quantity": 19},
    }
    ev_res1 = client.post(
        "/api/v1/integrations/stock-umkm/events",
        headers=pos_headers,
        json=event_payload,
    )
    assert ev_res1.status_code == 202
    assert ev_res1.json()["data"]["idempotent_replay"] is False
    assert ev_res1.json()["data"]["webhook_deliveries"] == 1

    # Duplicate event delivery with same event_id is safely idempotent
    ev_res2 = client.post(
        "/api/v1/integrations/stock-umkm/events",
        headers=pos_headers,
        json=event_payload,
    )
    assert ev_res2.status_code == 202
    assert ev_res2.json()["data"]["idempotent_replay"] is True
    assert ev_res2.json()["data"]["webhook_deliveries"] == 0

    # Inventory lookup reflects the updated stock quantity (19)
    inv_res = client.get(
        "/api/v1/integrations/stock-umkm/inventory?product_id=123",
        headers=pos_headers,
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["data"][0]["quantity"] == 19

    # Check webhook deliveries
    deliv_res = client.get(f"/api/v1/webhooks/{webhook_id}/deliveries", headers=admin_headers)
    assert deliv_res.status_code == 200
    assert len(deliv_res.json()["data"]) == 1


def test_iot_device_lifecycle_telemetry_prometheus_and_commands(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)
    iot_proj = client.get("/api/v1/projects/iot-dashboard", headers=admin_headers).json()["data"]

    # Register ESP32 device HPM55-0002
    reg_res = client.post(
        "/api/v1/iot/devices",
        headers=admin_headers,
        json={
            "project_id": iot_proj["id"],
            "device_uid": "HPM55-0002",
            "name": "Heater Line 2 Sensor",
            "device_type": "esp32",
            "metadata": {"location": "Line-2"},
        },
    )
    assert reg_res.status_code == 201
    device_data = reg_res.json()["data"]
    raw_device_cred = device_data["raw_credential"]
    assert raw_device_cred.startswith("pap_dev_")

    # Publish telemetry using the device's own credential (Blueprint Section 9.4)
    telemetry_res = client.post(
        "/api/v1/iot/devices/HPM55-0002/telemetry",
        headers={"X-Device-Credential": raw_device_cred},
        json={
            "device_id": "HPM55-0002",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "temperature": 185.5,
            "counter": 120,
            "current": 2.4,
        },
    )
    assert telemetry_res.status_code == 201

    # Verify device status is now 'online' and last_seen_at is populated
    status_res = client.get("/api/v1/iot/devices/HPM55-0002/status", headers=admin_headers)
    assert status_res.status_code == 200
    assert status_res.json()["data"]["status"] == "online"
    assert status_res.json()["data"]["last_seen_at"] is not None
    assert (
        status_res.json()["data"]["topics"]["telemetry"]
        == "pap/iot/HPM55-0002/telemetry"
    )

    # Verify telemetry appears in Prometheus /metrics scrape endpoint
    prom_scrape = client.get("/metrics")
    assert prom_scrape.status_code == 200
    assert 'pap_iot_device_temperature_celsius{device_id="HPM55-0002",device_type="esp32"} 185.5' in prom_scrape.text

    # Issue an authorized command to the device
    cmd_res = client.post(
        "/api/v1/iot/devices/HPM55-0002/commands",
        headers=admin_headers,
        json={
            "command": "set_sampling_interval",
            "parameters": {"interval_sec": 10},
            "correlation_id": "corr-hpm55-001",
            "ttl_seconds": 300,
        },
    )
    assert cmd_res.status_code == 201
    assert cmd_res.json()["data"]["correlation_id"] == "corr-hpm55-001"

    # Device acknowledges command
    ack_res = client.post(
        "/api/v1/iot/devices/HPM55-0002/commands/corr-hpm55-001/ack",
        headers={"X-Device-Credential": raw_device_cred},
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["data"]["status"] == "acknowledged"


def test_database_registry_metrics_monitoring_and_audit_logs(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    seed_platform_registry(db_session)

    # List database connections and inspect approved schema
    conns_res = client.get("/api/v1/database/connections", headers=admin_headers)
    assert conns_res.status_code == 200
    conns = conns_res.json()["data"]
    assert len(conns) >= 1
    stock_conn = next(c for c in conns if c["name"] == "stock-umkm-mysql")
    conn_id = stock_conn["id"]
    assert "password" not in stock_conn
    assert stock_conn["secret_reference"] == "STOCK_DB_PASSWORD"

    schema_res = client.get(
        f"/api/v1/database/sources/{conn_id}/schema?table=products",
        headers=admin_headers,
    )
    assert schema_res.status_code == 200
    assert "products" in schema_res.json()["data"]["allowed_tables"]

    # Query metrics and monitoring endpoints
    srv_metrics = client.get("/api/v1/metrics/server", headers=admin_headers)
    assert srv_metrics.status_code == 200
    assert srv_metrics.json()["data"]["container_limits"]["mem_limit"] == "256m"

    prom_q = client.get("/api/v1/metrics/prometheus/query?query=up", headers=admin_headers)
    assert prom_q.status_code == 200

    mon_overview = client.get("/api/v1/monitoring/overview", headers=admin_headers)
    assert mon_overview.status_code == 200
    assert mon_overview.json()["data"]["projects_total"] >= 3

    # Verify audit logs recorded privileged operations
    audit_res = client.get("/api/v1/audit-logs", headers=admin_headers)
    assert audit_res.status_code == 200
    assert audit_res.json()["meta"]["total"] >= 1


def test_alembic_upgrade_and_downgrade(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from pathlib import Path

    db_file = tmp_path / "alembic_test.sqlite3"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_cfg, "head")
    eng = create_engine(db_url)
    tables_after_upgrade = set(inspect(eng).get_table_names())
    assert "users" in tables_after_upgrade
    assert "projects" in tables_after_upgrade
    assert "audit_logs" in tables_after_upgrade
    eng.dispose()

    command.downgrade(alembic_cfg, "base")
    eng2 = create_engine(db_url)
    tables_after_downgrade = set(inspect(eng2).get_table_names())
    assert "users" not in tables_after_downgrade
    eng2.dispose()


def test_three_projects_connected_via_pap_main_api(
    client: TestClient, db_session: Session, admin_headers: dict[str, str]
):
    """Verify Personal Server Manager and IoT Dashboard communicate via PAP as the Main API."""
    from app.core.config import settings

    seed_platform_registry(db_session)

    psm_headers = {"X-API-Key": settings.PAP_PSM_SERVICE_KEY}
    iot_headers = {"X-API-Key": settings.PAP_IOT_SERVICE_KEY}

    # 1. Hub overview lists all connected projects, IoT Fleet summary, and MQTT configuration
    hub_res = client.get("/api/v1/integrations/hub/overview", headers=psm_headers)
    assert hub_res.status_code == 200
    hub_data = hub_res.json()["data"]
    assert hub_data["main_api"]["name"] == "Personal API Platform"
    project_slugs = {p["slug"] for p in hub_data["connected_projects"]}
    assert "personal-server-manager" in project_slugs
    assert "iot-dashboard" in project_slugs
    assert hub_data["iot_dashboard"]["summary"]["total_devices"] >= 3
    assert hub_data["mqtt_broker"]["local_host"] == "192.168.25.101"
    assert hub_data["mqtt_broker"]["tailscale_host"] == "100.106.63.90"
    assert hub_data["mqtt_broker"]["username"] == "useriot"
    assert hub_data["mqtt_broker"]["port"] == 1883
    assert hub_data["mqtt_broker"]["enabled"] is True

    # 2. Personal Server Manager pushes its live server/project/container state to PAP Main API
    sync_res = client.post(
        "/api/v1/integrations/psm/sync",
        headers=psm_headers,
        json={
            "servers": [
                {"id": 1, "name": "Homelab-Node-01", "hostname": "192.168.25.101", "status": "online"}
            ],
            "projects": [
                {"id": 1, "name": "Personal API Platform", "slug": "personal-api-platform"},
                {"id": 2, "name": "IoT Heatpress Dashboard", "slug": "iot-dashboard"},
            ],
            "containers": [
                {"name": "pap-api", "status": "running"},
                {"name": "heatpress_api", "status": "running"},
            ],
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["data"]["status"] == "synced"
    assert sync_res.json()["data"]["servers_count"] == 1

    # PSM state endpoint returns the synchronized state
    state_res = client.get("/api/v1/integrations/psm/state", headers=iot_headers)
    assert state_res.status_code == 200
    assert state_res.json()["data"]["servers"][0]["name"] == "Homelab-Node-01"

    # 3. IoT Dashboard compatibility endpoints (/api/devices/*) and /api/v1/iot/fleet/* work seamlessly
    hier_res = client.get("/api/devices/hierarchy")
    assert hier_res.status_code == 200
    hier = hier_res.json()
    assert hier["category"] == "Heatpress"
    model_names = {m["id"]: m for m in hier["models"]}
    assert "HPM 55" in model_names
    assert len(model_names["HPM 55"]["devices"]) >= 1

    # Register a new Heatpress unit via /api/devices/ and verify it appears in PAP v1 IoT registry
    create_dev = client.post(
        "/api/devices/",
        headers=iot_headers,
        json={
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "name": "HPM 55 Line 3",
            "model": "HPM 55",
            "category": "heatpress",
        },
    )
    assert create_dev.status_code == 201
    created_body = create_dev.json()
    assert created_body["mac_address"] == "AA:BB:CC:DD:EE:FF"

    # Update the device via /api/devices/{mac}
    update_dev = client.put(
        "/api/devices/AA:BB:CC:DD:EE:FF",
        headers=iot_headers,
        json={"name": "HPM 55 Line 3 Updated"},
    )
    assert update_dev.status_code == 200
    assert update_dev.json()["name"] == "HPM 55 Line 3 Updated"

    # Verify PSM can fetch the updated IoT fleet via PAP Main API
    fleet_v1 = client.get("/api/v1/iot/fleet/hierarchy", headers=psm_headers)
    assert fleet_v1.status_code == 200
    v1_models = {m["id"]: m for m in fleet_v1.json()["data"]["models"]}
    hpm_devices = v1_models["HPM 55"]["devices"]
    assert any(d["mac_address"] == "AA:BB:CC:DD:EE:FF" and d["name"] == "HPM 55 Line 3 Updated" for d in hpm_devices)

    # Delete the test device via /api/devices/{mac}
    del_dev = client.delete("/api/devices/AA:BB:CC:DD:EE:FF", headers=iot_headers)
    assert del_dev.status_code == 200



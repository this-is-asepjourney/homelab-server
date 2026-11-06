"""Tests for IoT Dashboard API & Personal API Platform (Main API) integration."""

from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


def test_health_and_pap_status_endpoints():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["api"] == "ok"
    assert "pap_api" in body

    res_api_health = client.get("/api/health")
    assert res_api_health.status_code == 200

    pap_status = client.get("/api/pap/status")
    assert pap_status.status_code == 200
    res_data = pap_status.json()
    assert res_data["main_api"] == "Personal API Platform"
    assert "mqtt_broker" in res_data
    assert res_data["mqtt_broker"]["local_host"] == "192.168.25.101"
    assert res_data["mqtt_broker"]["tailscale_host"] == "100.106.63.90"
    assert res_data["mqtt_broker"]["username"] == "useriot"
    assert res_data["mqtt_broker"]["port"] == 1883


def test_devices_hierarchy_and_pap_sync():
    hier_res = client.get("/api/devices/hierarchy")
    assert hier_res.status_code == 200
    hier = hier_res.json()
    assert hier["category"] == "Heatpress"
    assert hier["summary"]["total_devices"] >= 3
    model_ids = {m["id"] for m in hier["models"]}
    assert {"HPM 55", "AF-450", "APM-LOGO", "comingsoon"}.issubset(model_ids)

    sync_res = client.post("/api/pap/sync")
    assert sync_res.status_code == 200
    assert sync_res.json()["status"] == "success"
    assert sync_res.json()["total_devices"] >= 3


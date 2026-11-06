"""Heatpress IoT Fleet Service & Routers for PAP Main API (/api/v1/iot/fleet/* and /api/devices/*)."""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import Principal
from app.core.security import generate_device_credential
from app.dependencies import require_any_scope
from app.integrations.prometheus import PrometheusAdapter
from app.modules.iot.models import Device, DeviceCredential
from app.modules.iot.repository import IotRepository
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.schemas import success_response
from app.services.bootstrap import HEATPRESS_FLEET_DEVICES_SEED

ALL_MQTT_METRICS = "sysctrl_.+|event_cnt_.+|event_handling_.+|machine_time_.+|heatpress_.+"

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "HPM 55": {
        "name": "HPM 55",
        "type": "Pneumatic Double Station",
        "status": "active",
        "icon": "bx-flame",
        "badge_color": "primary",
        "description": (
            "Mesin heatpress pneumatik double station bertekanan tinggi untuk transfer sublimasi, "
            "sablon DTF, dan heat seal presisi."
        ),
        "specs": {
            "system": "Pneumatic Dual-Bed Shuttle",
            "pressure": "4 - 8 Bar (Air Compressor)",
            "temp_range": "50°C - 250°C",
            "station": "Dual Platen 40 x 50 cm",
            "target_product": "Jersey, Kaos, Sublimation Garment",
        },
    },
    "AF-450": {
        "name": "AF-450",
        "type": "Automatic Flat Press 450",
        "status": "active",
        "icon": "bx-layer",
        "badge_color": "teal",
        "description": (
            "Mesin flatbed heat press otomatis seri 450 dengan pemanas presisi tinggi, "
            "auto-open elektromagnetik, dan pemantauan suhu real-time."
        ),
        "specs": {
            "system": "Electromagnetic Auto-Open Flatbed",
            "pressure": "Adjustable Mechanical Cam Clamp",
            "temp_range": "50°C - 220°C",
            "station": "Single Flatbed 40 x 50 cm",
            "target_product": "T-Shirt, Hoodies, Flat Fabric Garment",
        },
    },
    "APM-LOGO": {
        "name": "APM-LOGO",
        "type": "Auto Positioning Motion Logo",
        "status": "active",
        "icon": "bx-purchase-tag-alt",
        "badge_color": "amber",
        "description": (
            "Mesin heatpress khusus logo, badge, dan label pakaian dengan penempatan posisi otomatis "
            "(Auto Positioning Motion) dan laser guide."
        ),
        "specs": {
            "system": "Auto Positioning & Micro Press",
            "pressure": "Precision Pneumatic Micro-cylinder",
            "temp_range": "50°C - 230°C",
            "station": "Compact Platen 15 x 15 cm / Laser Pointer",
            "target_product": "Label Kerah, Logo Dada, Pocket, Patch",
        },
    },
    "comingsoon": {
        "name": "Coming Soon",
        "type": "Next-Gen Intelligent Press",
        "status": "coming_soon",
        "icon": "bx-time-five",
        "badge_color": "purple",
        "description": (
            "Slot ekspansi mesin heatpress generasi pintar masa depan dengan sensor tekanan digital "
            "terintegrasi (load cell) dan multi-zone heating."
        ),
        "specs": {
            "system": "Multi-Zone Smart Heat & IoT Load-Cell",
            "pressure": "Digital Real-time Force Feedback",
            "temp_range": "30°C - 300°C Multi-Zone",
            "station": "Smart Modular Platen",
            "target_product": "Next-Gen Expansion Line",
        },
    },
}


class FleetDeviceCreate(BaseModel):
    mac_address: str
    name: str
    mcid: Optional[str] = None
    category: Optional[str] = "Heatpress"
    device_type: Optional[str] = "ESP32"
    model: Optional[str] = "HPM 55"
    location: Optional[str] = None
    description: Optional[str] = None

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("mcid")
    @classmethod
    def normalize_mcid(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


class FleetDeviceUpdate(BaseModel):
    name: Optional[str] = None
    mcid: Optional[str] = None
    category: Optional[str] = None
    device_type: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class FleetService:
    """Unified Heatpress IoT Fleet service backed by PAP's core 'devices' table and Prometheus."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.iot_repo = IotRepository(db)
        self.project_repo = ProjectRepository(db)
        self.prometheus = PrometheusAdapter()

    def ensure_iot_project_and_seed(self) -> Project:
        project = self.project_repo.get_by_slug("iot-dashboard")
        if not project:
            project = self.project_repo.create(
                Project(
                    slug="iot-dashboard",
                    name="IoT Dashboard",
                    description="Heatpress IoT Fleet dashboard for ESP32 device registry, status, and telemetry",
                    status="active",
                )
            )
            for dev_seed in HEATPRESS_FLEET_DEVICES_SEED:
                if not self.iot_repo.get_by_uid(dev_seed["device_uid"]):
                    created_dev = self.iot_repo.create_device(
                        Device(
                            project_id=project.id,
                            device_uid=dev_seed["device_uid"],
                            name=dev_seed["name"],
                            device_type=dev_seed["device_type"],
                            status=dev_seed["status"],
                            metadata_json=dev_seed["metadata"],
                        )
                    )
                    _, cred_hash = generate_device_credential()
                    self.iot_repo.create_credential(
                        DeviceCredential(device_id=created_dev.id, credential_hash=cred_hash)
                    )
        return project

    def _device_to_fleet_dict(self, d: Device, online_macs: Optional[set[str]] = None) -> dict[str, Any]:
        meta = d.metadata_json or {}
        mac = str(meta.get("mac_address") or d.device_uid).upper()
        is_online = (
            (mac in online_macs)
            if online_macs is not None
            else (d.status == "online")
        )
        return {
            "id": str(d.id),
            "project_id": str(d.project_id),
            "mac_address": mac,
            "device_uid": d.device_uid,
            "name": d.name or mac,
            "mcid": meta.get("mcid"),
            "category": meta.get("category", "Heatpress"),
            "device_type": d.device_type or meta.get("device_type", "ESP32"),
            "model": meta.get("model", "HPM 55"),
            "location": meta.get("location"),
            "description": meta.get("description"),
            "status": "online" if is_online else d.status,
            "online": is_online,
            "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }

    def get_online_macs(self) -> set[str]:
        online: set[str] = set()
        try:
            data = self.prometheus.instant_query(f'count by (MAC) ({{__name__=~"{ALL_MQTT_METRICS}"}})')
            for r in data.get("result", []):
                metric = r.get("metric", {})
                mac = (metric.get("MAC") or metric.get("mac") or "").upper()
                if mac:
                    online.add(mac)
        except Exception:
            pass

        # Also include devices marked online in PAP database
        for d in self.iot_repo.list_devices():
            if d.status == "online":
                meta = d.metadata_json or {}
                mac = str(meta.get("mac_address") or d.device_uid).upper()
                online.add(mac)
        return online

    def list_fleet_devices(
        self,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        category: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        self.ensure_iot_project_and_seed()
        all_devs = self.iot_repo.list_devices()
        online_macs = self.get_online_macs()
        items = [self._device_to_fleet_dict(d, online_macs) for d in all_devs]

        if category:
            cat_l = category.lower().strip()
            items = [i for i in items if (i.get("category") or "").lower() == cat_l]

        if model:
            mod_clean = model.replace("-", " ").lower().strip()
            items = [
                i
                for i in items
                if mod_clean in (i.get("model") or "").replace("-", " ").lower()
            ]

        if search:
            q = search.lower().strip()
            items = [
                i
                for i in items
                if q in (i.get("name") or "").lower()
                or q in (i.get("mac_address") or "").lower()
                or q in (i.get("mcid") or "").lower()
                or q in (i.get("location") or "").lower()
                or q in (i.get("model") or "").lower()
                or q in (i.get("device_type") or "").lower()
            ]

        return items[skip : skip + limit]

    def get_fleet_stats(self) -> dict[str, int]:
        devices = self.list_fleet_devices(limit=500)
        total = len(devices)
        mapped = sum(1 for d in devices if d.get("mcid") and str(d["mcid"]).strip())
        online = sum(1 for d in devices if d.get("online"))
        return {
            "total": total,
            "online": online,
            "offline": max(0, total - online),
            "mapped": mapped,
            "unmapped": max(0, total - mapped),
        }

    def get_fleet_statuses(self) -> dict[str, bool]:
        devices = self.list_fleet_devices(limit=500)
        return {d["mac_address"]: bool(d.get("online")) for d in devices}

    def sync_from_prometheus(self) -> list[dict[str, Any]]:
        project = self.ensure_iot_project_and_seed()
        try:
            data = self.prometheus.instant_query("count by (MAC, model) (sysctrl_STS)")
            results = data.get("result", [])
            for r in results:
                metric = r.get("metric", {})
                mac = (metric.get("MAC") or metric.get("mac") or "").strip().upper()
                if not mac:
                    continue
                raw_model = (metric.get("model") or "Heatpress").strip()
                clean_model = raw_model.replace("-", " ").upper()
                if "AF" in clean_model or "450" in clean_model:
                    canonical_model = "AF-450"
                    default_name = "AF-450 Auto Flat 1"
                    default_loc = "Lini 2 - Flatbed"
                    default_desc = "Automatic Flat Heat Press 450 Series"
                    default_mcid = "AF-450-01"
                elif "APM" in clean_model or "LOGO" in clean_model:
                    canonical_model = "APM-LOGO"
                    default_name = "APM-LOGO Precision 1"
                    default_loc = "Lini 3 - Apparel Logo"
                    default_desc = "Auto Positioning Motion Heat Press for Logo & Label"
                    default_mcid = "APM-01"
                elif "HPM" in clean_model or "55" in clean_model:
                    canonical_model = "HPM 55"
                    default_name = "HPM 55 Press 1"
                    default_loc = "Lini 1 - Sublimasi"
                    default_desc = "Pneumatic Double Station Heat Press"
                    default_mcid = "HP-55-01"
                else:
                    canonical_model = raw_model
                    default_name = f"{canonical_model} Press ({mac[-5:]})"
                    default_loc = "Area Produksi"
                    default_desc = "Auto-discovered from Prometheus MQTT telemetry"
                    default_mcid = f"{canonical_model}-01"

                existing = self.iot_repo.get_by_uid(mac)
                if not existing:
                    created = self.iot_repo.create_device(
                        Device(
                            project_id=project.id,
                            device_uid=mac,
                            name=default_name,
                            device_type="ESP32",
                            status="online",
                            last_seen_at=datetime.now(timezone.utc),
                            metadata_json={
                                "mac_address": mac,
                                "mcid": default_mcid,
                                "category": "Heatpress",
                                "model": canonical_model,
                                "location": default_loc,
                                "description": default_desc,
                            },
                        )
                    )
                    _, cred_hash = generate_device_credential()
                    self.iot_repo.create_credential(
                        DeviceCredential(device_id=created.id, credential_hash=cred_hash)
                    )
        except Exception:
            pass
        return self.list_fleet_devices(limit=500)

    def get_hierarchy(self) -> dict[str, Any]:
        devices = self.sync_from_prometheus()
        model_devices: dict[str, list[dict[str, Any]]] = {
            "HPM 55": [],
            "AF-450": [],
            "APM-LOGO": [],
            "comingsoon": [],
        }
        other_devices: dict[str, list[dict[str, Any]]] = {}

        for d in devices:
            mod_upper = (d.get("model") or "").upper().replace("-", " ").strip()
            if "HPM" in mod_upper or "55" in mod_upper:
                model_devices["HPM 55"].append(d)
            elif "AF" in mod_upper or "450" in mod_upper:
                model_devices["AF-450"].append(d)
            elif "APM" in mod_upper or "LOGO" in mod_upper:
                model_devices["APM-LOGO"].append(d)
            elif "COMING" in mod_upper:
                model_devices["comingsoon"].append(d)
            else:
                key = d.get("model") or "General"
                other_devices.setdefault(key, []).append(d)

        models_list: list[dict[str, Any]] = []
        for mid, cfg in MODEL_CONFIGS.items():
            devs = model_devices.get(mid, [])
            online_c = sum(1 for x in devs if x.get("online"))
            models_list.append(
                {
                    "id": mid,
                    "name": cfg["name"],
                    "category": "Heatpress",
                    "type": cfg["type"],
                    "status": cfg["status"],
                    "icon": cfg["icon"],
                    "badge_color": cfg["badge_color"],
                    "description": cfg["description"],
                    "specs": cfg["specs"],
                    "devices": devs,
                    "device_count": len(devs),
                    "online_count": online_c,
                    "offline_count": len(devs) - online_c,
                }
            )

        for custom_mod, devs in other_devices.items():
            online_c = sum(1 for x in devs if x.get("online"))
            models_list.append(
                {
                    "id": custom_mod,
                    "name": custom_mod,
                    "category": "Heatpress",
                    "type": "Custom Heatpress",
                    "status": "active",
                    "icon": "bx-chip",
                    "badge_color": "sky",
                    "description": f"Model kustom: {custom_mod}",
                    "specs": {},
                    "devices": devs,
                    "device_count": len(devs),
                    "online_count": online_c,
                    "offline_count": len(devs) - online_c,
                }
            )

        total_units = len(devices)
        total_online = sum(1 for d in devices if d.get("online"))
        return {
            "category": "Heatpress",
            "title": "Heatpress IoT Fleet Monitoring (PAP Main API)",
            "description": "Hirarki armada mesin heatpress: HPM 55, AF-450, APM-LOGO, dan Coming Soon",
            "summary": {
                "total_devices": total_units,
                "online": total_online,
                "offline": total_units - total_online,
                "active_models": 3,
                "total_models": len(models_list),
            },
            "models": models_list,
        }

    def get_single_device(self, mac_address: str) -> dict[str, Any]:
        self.ensure_iot_project_and_seed()
        mac_upper = mac_address.strip().upper()
        dev = self.iot_repo.get_by_uid(mac_upper) or self.iot_repo.get_by_uid(mac_address.strip())
        if not dev:
            for d in self.iot_repo.list_devices():
                meta = d.metadata_json or {}
                if str(meta.get("mac_address", "")).upper() == mac_upper:
                    dev = d
                    break
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")
        return self._device_to_fleet_dict(dev, self.get_online_macs())

    def create_fleet_device(self, payload: FleetDeviceCreate) -> dict[str, Any]:
        project = self.ensure_iot_project_and_seed()
        mac_upper = payload.mac_address.strip().upper()
        if self.iot_repo.get_by_uid(mac_upper):
            raise HTTPException(
                status_code=400,
                detail=f"Device dengan MAC {mac_upper} sudah terdaftar",
            )
        created = self.iot_repo.create_device(
            Device(
                project_id=project.id,
                device_uid=mac_upper,
                name=payload.name.strip(),
                device_type=payload.device_type or "ESP32",
                status="online",
                last_seen_at=datetime.now(timezone.utc),
                metadata_json={
                    "mac_address": mac_upper,
                    "mcid": payload.mcid,
                    "category": payload.category or "Heatpress",
                    "model": payload.model or "HPM 55",
                    "location": payload.location,
                    "description": payload.description,
                },
            )
        )
        _, cred_hash = generate_device_credential()
        self.iot_repo.create_credential(
            DeviceCredential(device_id=created.id, credential_hash=cred_hash)
        )
        return self._device_to_fleet_dict(created, self.get_online_macs())

    def update_fleet_device(self, mac_address: str, payload: FleetDeviceUpdate) -> dict[str, Any]:
        self.ensure_iot_project_and_seed()
        mac_upper = mac_address.strip().upper()
        dev = self.iot_repo.get_by_uid(mac_upper) or self.iot_repo.get_by_uid(mac_address.strip())
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")

        meta = dict(dev.metadata_json or {})
        meta["mac_address"] = mac_upper
        if payload.name is not None:
            dev.name = payload.name.strip()
        if payload.device_type is not None:
            dev.device_type = payload.device_type.strip()
        if payload.mcid is not None:
            meta["mcid"] = payload.mcid.strip() if payload.mcid else None
        if payload.category is not None:
            meta["category"] = payload.category.strip()
        if payload.model is not None:
            meta["model"] = payload.model.strip()
        if payload.location is not None:
            meta["location"] = payload.location.strip() if payload.location else None
        if payload.description is not None:
            meta["description"] = payload.description.strip() if payload.description else None

        dev.metadata_json = meta
        saved = self.iot_repo.save_device(dev)
        return self._device_to_fleet_dict(saved, self.get_online_macs())

    def delete_fleet_device(self, mac_address: str) -> dict[str, Any]:
        self.ensure_iot_project_and_seed()
        mac_upper = mac_address.strip().upper()
        dev = self.iot_repo.get_by_uid(mac_upper) or self.iot_repo.get_by_uid(mac_address.strip())
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")
        self.iot_repo.delete_device(dev)
        return {"message": f"Device {mac_upper} berhasil dihapus", "mac_address": mac_upper}

    def get_device_last_seen(self, mac_address: str) -> dict[str, Any]:
        dev_dict = self.get_single_device(mac_address)
        last_seen_iso = dev_dict.get("last_seen")
        seconds_ago: Optional[int] = None
        if last_seen_iso:
            try:
                dt = datetime.fromisoformat(last_seen_iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                seconds_ago = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
            except Exception:
                seconds_ago = None
        return {
            "mac_address": dev_dict["mac_address"],
            "online": dev_dict["online"],
            "last_seen": last_seen_iso,
            "seconds_ago": seconds_ago,
        }


# 1. Versioned PAP v1 Fleet Router (/api/v1/iot/fleet/*)
v1_fleet_router = APIRouter(prefix="/iot/fleet", tags=["IoT Fleet"])


@v1_fleet_router.get("/devices")
def v1_list_fleet_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    principal: Principal = Depends(require_any_scope("iot:read", "metrics:read")),
    db: Session = Depends(get_db),
):
    data = FleetService(db).list_fleet_devices(
        skip=skip, limit=limit, search=search, category=category, model=model
    )
    return success_response(data=data, message="IoT fleet devices retrieved successfully")


@v1_fleet_router.get("/stats")
def v1_get_fleet_stats(
    principal: Principal = Depends(require_any_scope("iot:read", "metrics:read")),
    db: Session = Depends(get_db),
):
    return success_response(
        data=FleetService(db).get_fleet_stats(),
        message="IoT fleet statistics retrieved successfully",
    )


@v1_fleet_router.get("/statuses")
def v1_get_fleet_statuses(
    principal: Principal = Depends(require_any_scope("iot:read", "metrics:read")),
    db: Session = Depends(get_db),
):
    return success_response(
        data=FleetService(db).get_fleet_statuses(),
        message="IoT fleet online statuses retrieved successfully",
    )


@v1_fleet_router.get("/hierarchy")
def v1_get_fleet_hierarchy(
    principal: Principal = Depends(require_any_scope("iot:read", "metrics:read")),
    db: Session = Depends(get_db),
):
    return success_response(
        data=FleetService(db).get_hierarchy(),
        message="IoT fleet hierarchy retrieved successfully",
    )


@v1_fleet_router.post("/sync-prometheus")
def v1_sync_fleet_prometheus(
    principal: Principal = Depends(require_any_scope("iot:read", "iot:manage", "metrics:read")),
    db: Session = Depends(get_db),
):
    devices = FleetService(db).sync_from_prometheus()
    return success_response(
        data={"devices": devices, "count": len(devices)},
        message=f"Synchronized {len(devices)} fleet devices with Prometheus",
    )


# 2. Direct Compatibility Router for IoT Dashboard Web & API (/api/devices/* and /api/health)
compat_devices_router = APIRouter(tags=["IoT Dashboard Compatibility"])


@compat_devices_router.get("/api/health")
def compat_iot_health(db: Session = Depends(get_db)):
    prom = PrometheusAdapter().check_health()
    prom_ok = bool(prom.get("reachable"))
    return {
        "status": "healthy",
        "api": "ok",
        "pap_main_api": "connected",
        "prometheus": "ok" if prom_ok else "standby",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@compat_devices_router.get("/api/devices/stats")
def compat_device_stats(db: Session = Depends(get_db)):
    return FleetService(db).get_fleet_stats()


@compat_devices_router.get("/api/devices/statuses")
def compat_device_statuses(db: Session = Depends(get_db)):
    return FleetService(db).get_fleet_statuses()


@compat_devices_router.get("/api/devices/hierarchy")
def compat_device_hierarchy(db: Session = Depends(get_db)):
    return FleetService(db).get_hierarchy()


@compat_devices_router.post("/api/devices/sync-prometheus")
def compat_sync_prometheus(db: Session = Depends(get_db)):
    devices = FleetService(db).sync_from_prometheus()
    return {
        "status": "success",
        "source": "personal-api-platform",
        "message": f"Berhasil sinkronisasi {len(devices)} device dari PAP & Prometheus",
        "devices": devices,
    }


@compat_devices_router.get("/api/devices/")
@compat_devices_router.get("/api/devices", include_in_schema=False)
def compat_list_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return FleetService(db).list_fleet_devices(
        skip=skip, limit=limit, search=search, category=category, model=model
    )


@compat_devices_router.post("/api/devices/", status_code=status.HTTP_201_CREATED)
@compat_devices_router.post("/api/devices", status_code=status.HTTP_201_CREATED, include_in_schema=False)
def compat_create_device(payload: FleetDeviceCreate, db: Session = Depends(get_db)):
    return FleetService(db).create_fleet_device(payload)


@compat_devices_router.get("/api/devices/{mac_address}")
def compat_get_device(mac_address: str, db: Session = Depends(get_db)):
    return FleetService(db).get_single_device(mac_address)


@compat_devices_router.put("/api/devices/{mac_address}")
def compat_update_device(
    mac_address: str, payload: FleetDeviceUpdate, db: Session = Depends(get_db)
):
    return FleetService(db).update_fleet_device(mac_address, payload)


@compat_devices_router.delete("/api/devices/{mac_address}")
def compat_delete_device(mac_address: str, db: Session = Depends(get_db)):
    return FleetService(db).delete_fleet_device(mac_address)


@compat_devices_router.get("/api/devices/{mac_address}/status")
def compat_get_device_status(mac_address: str, db: Session = Depends(get_db)):
    dev = FleetService(db).get_single_device(mac_address)
    return {"mac_address": dev["mac_address"], "online": dev["online"]}


@compat_devices_router.get("/api/devices/{mac_address}/last-seen")
def compat_get_device_last_seen(mac_address: str, db: Session = Depends(get_db)):
    return FleetService(db).get_device_last_seen(mac_address)


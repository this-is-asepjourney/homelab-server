from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ─────────────────────────────────────────────
# Base Schemas
# ─────────────────────────────────────────────

class DeviceBase(BaseModel):
    name: Optional[str] = None
    mcid: Optional[str] = None          # Machine ID — mapping utama MAC ↔ MCID
    category: Optional[str] = "Heatpress"  # Hirarki Kategori (default: Heatpress)
    device_type: Optional[str] = None   # Tipe hardware: ESP32, MC, dsb
    model: Optional[str] = None         # HPM 55, AF-450, APM-LOGO, comingsoon
    location: Optional[str] = None
    description: Optional[str] = None


class DeviceCreate(DeviceBase):
    mac_address: str
    name: str

    @field_validator('mac_address')
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        """Normalize MAC address to uppercase so DB always stores consistently.
        Ensures lookup against Prometheus tags (which may be any case) works
        correctly when both sides are normalized before comparison.
        """
        return v.strip().upper()

    @field_validator('mcid')
    @classmethod
    def normalize_mcid(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace from MCID."""
        return v.strip() if v else None


class DeviceUpdate(DeviceBase):
    pass


class Device(DeviceBase):
    mac_address: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Enhanced Response Schemas
# ─────────────────────────────────────────────

class DeviceWithStatus(Device):
    """Device info + online/offline status + last seen timestamp."""
    online: bool = False
    last_seen: Optional[datetime] = None


class StatsResponse(BaseModel):
    """Ringkasan statistik device."""
    total: int
    online: int
    offline: int
    mapped: int      # Device yang sudah punya MCID
    unmapped: int    # Device yang belum punya MCID


class HealthResponse(BaseModel):
    """API health check response."""
    status: str                         # "healthy" | "degraded"
    api: str = "ok"
    prometheus: str = "unknown"
    pap_api: str = "connected"
    pap_url: Optional[str] = None
    timestamp: datetime


class LastSeenResponse(BaseModel):
    """Last seen info untuk satu device."""
    mac_address: str
    online: bool
    last_seen: Optional[datetime] = None
    seconds_ago: Optional[int] = None


# ─────────────────────────────────────────────
# Hierarchy Schemas (Heatpress Fleet)
# ─────────────────────────────────────────────

class ModelHierarchyItem(BaseModel):
    """Informasi satu model dalam hirarki Heatpress."""
    id: str
    name: str
    category: str = "Heatpress"
    type: Optional[str] = None
    status: str                         # "active" | "coming_soon"
    icon: Optional[str] = None
    badge_color: Optional[str] = None
    description: Optional[str] = None
    specs: Optional[Dict[str, str]] = None
    devices: List[DeviceWithStatus] = []
    device_count: int = 0
    online_count: int = 0
    offline_count: int = 0


class HierarchyResponse(BaseModel):
    """Respon struktur hirarki Heatpress lengkap."""
    category: str = "Heatpress"
    title: str = "Heatpress Monitoring System"
    description: str = "Hirarki armada mesin Heatpress: HPM 55, AF-450, APM-LOGO & Coming Soon"
    summary: Dict[str, int]
    models: List[ModelHierarchyItem]


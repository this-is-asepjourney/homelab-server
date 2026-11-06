"""Pydantic schemas for homelab service monitoring and platform overview."""

from typing import Any

from pydantic import BaseModel


class MonitoringOverview(BaseModel):
    projects_total: int
    active_clients_total: int
    devices_total: int
    devices_online: int
    webhooks_active: int
    services: list[dict[str, Any]]


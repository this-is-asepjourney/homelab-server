from typing import Dict, Any, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from apps.api.app.core.dependencies import get_current_user, require_role
from apps.api.app.models.entities import User
from apps.api.app.services.alert_service import (
    load_notification_settings,
    save_notification_settings,
    get_recent_alerts,
    clear_alerts,
    send_discord_webhook,
    send_telegram_message,
    record_alert
)

router = APIRouter(prefix="/notifications", tags=["Alerts & Notifications"])

class NotificationSettingsUpdate(BaseModel):
    enabled: bool = False
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    cpu_threshold: float = 90.0
    memory_threshold: float = 90.0
    disk_threshold: float = 90.0
    notify_server_offline: bool = True
    notify_deployments: bool = True

@router.get("/settings")
def get_settings(current_user: User = Depends(get_current_user)):
    return load_notification_settings()

@router.post("/settings")
def update_settings(
    payload: NotificationSettingsUpdate,
    current_user: User = Depends(require_role("owner", "admin"))
):
    saved = save_notification_settings(payload.model_dump())
    return {"message": "Notification settings updated successfully", "settings": saved}

@router.post("/test")
def test_notification(
    current_user: User = Depends(require_role("owner", "admin")),
):
    cfg = load_notification_settings()
    results = {"discord": False, "telegram": False}

    test_title = "PSM Test Notification"
    test_message = f"Hello from Personal Server Manager! Alert test dispatched by user '{current_user.name}' ({current_user.email}). All systems operational."

    if cfg.get("discord_webhook_url"):
        results["discord"] = send_discord_webhook(cfg["discord_webhook_url"], test_title, test_message, "info")

    if cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"):
        results["telegram"] = send_telegram_message(
            cfg["telegram_bot_token"],
            cfg["telegram_chat_id"],
            f"🔔 *[PSM Test Alert]*\n{test_message}"
        )

    record_alert("system", "Control Plane", "info", test_title, test_message)

    return {
        "status": "tested",
        "results": results,
        "details": {
            "discord_configured": bool(cfg.get("discord_webhook_url")),
            "telegram_configured": bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"))
        }
    }

@router.get("/alerts")
def list_alerts(current_user: User = Depends(get_current_user)):
    return get_recent_alerts()

@router.post("/alerts/clear")
def clear_all_alerts(current_user: User = Depends(require_role("owner", "admin"))):
    clear_alerts()
    return {"message": "All alerts cleared"}


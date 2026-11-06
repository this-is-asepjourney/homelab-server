import os
import json
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(settings.STORAGE_BASE_DIR, "notification_settings.json")

# In-memory alerts ring buffer & throttle tracker
_active_alerts: List[Dict[str, Any]] = []
_last_alert_timestamps: Dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 600  # 10 minutes throttle per server + issue

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "discord_webhook_url": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "cpu_threshold": 90.0,
    "memory_threshold": 90.0,
    "disk_threshold": 90.0,
    "notify_server_offline": True,
    "notify_deployments": True,
}

def load_notification_settings() -> Dict[str, Any]:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                return merged
    except Exception as e:
        logger.warning(f"Could not load notification settings: {e}")
    return dict(DEFAULT_CONFIG)

def save_notification_settings(new_settings: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    current = load_notification_settings()
    current.update(new_settings)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write notification settings: {e}")
    return current

def record_alert(server_id: str, server_name: str, level: str, title: str, description: str):
    """Store alert in memory for UI presentation."""
    global _active_alerts
    alert_item = {
        "id": f"alt-{int(time.time() * 1000)}",
        "server_id": server_id,
        "server_name": server_name,
        "level": level,  # 'info', 'warning', 'critical'
        "title": title,
        "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    _active_alerts.insert(0, alert_item)
    if len(_active_alerts) > 50:
        _active_alerts = _active_alerts[:50]

def get_recent_alerts() -> List[Dict[str, Any]]:
    return _active_alerts

def clear_alerts():
    global _active_alerts
    _active_alerts.clear()

def send_discord_webhook(webhook_url: str, title: str, message: str, level: str = "warning") -> bool:
    if not webhook_url or not webhook_url.startswith("http"):
        return False

    colors = {
        "info": 3447003,      # Blue
        "warning": 16753920,  # Orange
        "critical": 15158332, # Red
        "success": 3066993,   # Green
    }
    payload = {
        "username": "PSM Homelab Guard",
        "embeds": [
            {
                "title": f"🚨 {title}" if level in ["warning", "critical"] else f"ℹ️ {title}",
                "description": message,
                "color": colors.get(level, 3447003),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Personal Server Manager"}
            }
        ]
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "PSM-Alert-Bot"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status in (200, 204)
    except Exception as e:
        logger.warning(f"Discord webhook notification failed: {e}")
        return False

def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status == 200
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")
        return False

def dispatch_external_alert(title: str, message: str, level: str = "warning") -> Dict[str, bool]:
    cfg = load_notification_settings()
    results = {"discord": False, "telegram": False}

    if not cfg.get("enabled", False):
        return results

    if cfg.get("discord_webhook_url"):
        results["discord"] = send_discord_webhook(cfg["discord_webhook_url"], title, message, level)

    if cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"):
        tele_text = f"*🚨 [PSM Alert]* *{title}*\n\n{message}\n\n_Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_"
        results["telegram"] = send_telegram_message(cfg["telegram_bot_token"], cfg["telegram_chat_id"], tele_text)

    return results

def check_metrics_and_alert(server_id: str, server_name: str, metrics: Dict[str, Any]):
    """Evaluates telemetry data against alert thresholds with cooldown throttling."""
    cfg = load_notification_settings()
    if not cfg.get("enabled", False):
        return

    now = time.time()
    cpu = metrics.get("cpu_usage", 0.0)
    mem = metrics.get("memory_usage", 0.0)
    disk = metrics.get("disk_usage", 0.0)

    # 1. CPU Alert
    cpu_thresh = cfg.get("cpu_threshold", 90.0)
    if cpu >= cpu_thresh:
        key = f"{server_id}-cpu"
        if now - _last_alert_timestamps.get(key, 0) > ALERT_COOLDOWN_SECONDS:
            _last_alert_timestamps[key] = now
            title = f"High CPU Utilization on {server_name}"
            msg = f"Host **{server_name}** CPU utilization reached **{cpu:.1f}%** (Threshold: {cpu_thresh:.1f}%)."
            record_alert(server_id, server_name, "critical", title, msg)
            dispatch_external_alert(title, msg, level="critical")

    # 2. Memory Alert
    mem_thresh = cfg.get("memory_threshold", 90.0)
    if mem >= mem_thresh:
        key = f"{server_id}-mem"
        if now - _last_alert_timestamps.get(key, 0) > ALERT_COOLDOWN_SECONDS:
            _last_alert_timestamps[key] = now
            title = f"High RAM Consumption on {server_name}"
            msg = f"Host **{server_name}** RAM utilization is at **{mem:.1f}%** (Threshold: {mem_thresh:.1f}%)."
            record_alert(server_id, server_name, "critical", title, msg)
            dispatch_external_alert(title, msg, level="critical")

    # 3. Disk Alert
    disk_thresh = cfg.get("disk_threshold", 90.0)
    if disk >= disk_thresh:
        key = f"{server_id}-disk"
        if now - _last_alert_timestamps.get(key, 0) > ALERT_COOLDOWN_SECONDS:
            _last_alert_timestamps[key] = now
            title = f"Disk Space Warning on {server_name}"
            msg = f"Host **{server_name}** root disk partition reached **{disk:.1f}%** capacity (Threshold: {disk_thresh:.1f}%)."
            record_alert(server_id, server_name, "warning", title, msg)
            dispatch_external_alert(title, msg, level="warning")


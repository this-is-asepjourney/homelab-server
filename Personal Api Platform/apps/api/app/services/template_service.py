"""Homelab App Template Catalog for 1-Click Deployments."""
from typing import List, Dict, Any, Optional

HOMELAB_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "vaultwarden",
        "name": "Vaultwarden",
        "category": "Security",
        "description": "Lightweight, self-hosted Bitwarden-compatible password manager written in Rust. Uses < 50MB RAM.",
        "icon": "ShieldCheck",
        "badge": "Popular",
        "default_port": 8080,
        "environment_variables": {
            "SIGNUPS_ALLOWED": "true",
            "WEBSOCKET_ENABLED": "true",
            "INVITATIONS_ALLOWED": "true"
        },
        "compose_yaml": """services:
  vaultwarden:
    image: vaultwarden/server:latest
    container_name: ${CONTAINER_NAME:-vaultwarden}
    restart: unless-stopped
    ports:
      - "${HOST_PORT:-8080}:80"
    environment:
      - SIGNUPS_ALLOWED=${SIGNUPS_ALLOWED:-true}
      - WEBSOCKET_ENABLED=${WEBSOCKET_ENABLED:-true}
    volumes:
      - vaultwarden_data:/data

volumes:
  vaultwarden_data:
"""
    },
    {
        "id": "adguard-home",
        "name": "AdGuard Home",
        "category": "Networking",
        "description": "Network-wide software for blocking ads, tracking, and malware across all devices via local DNS filtering.",
        "icon": "ShieldAlert",
        "badge": "Recommended",
        "default_port": 3000,
        "environment_variables": {
            "WEB_PORT": "3000"
        },
        "compose_yaml": """services:
  adguardhome:
    image: adguard/adguardhome:latest
    container_name: ${CONTAINER_NAME:-adguard-home}
    restart: unless-stopped
    ports:
      - "${HOST_PORT:-3000}:3000/tcp"
      - "53:53/tcp"
      - "53:53/udp"
    volumes:
      - adguard_work:/opt/adguardhome/work
      - adguard_conf:/opt/adguardhome/conf

volumes:
  adguard_work:
  adguard_conf:
"""
    },
    {
        "id": "nginx-proxy-manager",
        "name": "Nginx Proxy Manager",
        "category": "Networking",
        "description": "Reverse proxy with a clean web UI, automated free Let's Encrypt SSL certificate provisioning, and access lists.",
        "icon": "Network",
        "badge": "Essential",
        "default_port": 81,
        "environment_variables": {
            "ADMIN_PORT": "81",
            "HTTP_PORT": "8081",
            "HTTPS_PORT": "8443"
        },
        "compose_yaml": """services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: ${CONTAINER_NAME:-nginx-proxy-manager}
    restart: unless-stopped
    ports:
      - "${ADMIN_PORT:-81}:81"
      - "${HTTP_PORT:-8081}:80"
      - "${HTTPS_PORT:-8443}:443"
    volumes:
      - npm_data:/data
      - npm_letsencrypt:/etc/letsencrypt

volumes:
  npm_data:
  npm_letsencrypt:
"""
    },
    {
        "id": "cloudflared-tunnel",
        "name": "Cloudflare Tunnel",
        "category": "Networking",
        "description": "Expose your homelab services securely to the internet without opening any ports on your home router.",
        "icon": "Cloud",
        "badge": "Zero-Trust",
        "default_port": 0,
        "environment_variables": {
            "TUNNEL_TOKEN": "eyJhIjoi..."
        },
        "compose_yaml": """services:
  tunnel:
    image: cloudflare/cloudflared:latest
    container_name: ${CONTAINER_NAME:-cloudflared-tunnel}
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${TUNNEL_TOKEN}
"""
    },
    {
        "id": "redis",
        "name": "Redis Standalone",
        "category": "Database",
        "description": "High-performance in-memory key-value data structure store used as a database, cache, and message broker.",
        "icon": "Database",
        "badge": "Fast",
        "default_port": 6379,
        "environment_variables": {
            "REDIS_PORT": "6379"
        },
        "compose_yaml": """services:
  redis:
    image: redis:7-alpine
    container_name: ${CONTAINER_NAME:-psm-redis}
    restart: unless-stopped
    command: redis-server --appendonly yes
    ports:
      - "${HOST_PORT:-6379}:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
"""
    },
    {
        "id": "portainer-ce",
        "name": "Portainer Community",
        "category": "Management",
        "description": "Comprehensive container management graphical user interface for Docker engines and swarms.",
        "icon": "Box",
        "badge": "Popular",
        "default_port": 9443,
        "environment_variables": {
            "PORTAINER_HTTPS_PORT": "9443"
        },
        "compose_yaml": """services:
  portainer:
    image: portainer/portainer-ce:latest
    container_name: ${CONTAINER_NAME:-portainer}
    restart: unless-stopped
    ports:
      - "${HOST_PORT:-9443}:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - portainer_data:/data

volumes:
  portainer_data:
"""
    },
    {
        "id": "uptime-kuma",
        "name": "Uptime Kuma",
        "category": "Monitoring",
        "description": "Self-hosted monitoring tool with status pages, certificate tracking, ping latency graphs, and alerts.",
        "icon": "Activity",
        "badge": "Monitoring",
        "default_port": 3003,
        "environment_variables": {
            "UPTIME_PORT": "3003"
        },
        "compose_yaml": """services:
  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: ${CONTAINER_NAME:-uptime-kuma-custom}
    restart: unless-stopped
    ports:
      - "${HOST_PORT:-3003}:3001"
    volumes:
      - uptime_kuma_data:/app/data

volumes:
  uptime_kuma_data:
"""
    },
    {
        "id": "postgres-custom",
        "name": "PostgreSQL 17",
        "category": "Database",
        "description": "Dedicated PostgreSQL 17 relational database instance with persistent storage for external homelab projects.",
        "icon": "Database",
        "badge": "Relational DB",
        "default_port": 5433,
        "environment_variables": {
            "POSTGRES_DB": "homelab_app",
            "POSTGRES_USER": "homelab",
            "POSTGRES_PASSWORD": "change_me_secure_pass_123"
        },
        "compose_yaml": """services:
  postgres:
    image: postgres:17-alpine
    container_name: ${CONTAINER_NAME:-postgres-custom}
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-homelab_app}
      POSTGRES_USER: ${POSTGRES_USER:-homelab}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change_me_secure_pass_123}
    ports:
      - "${HOST_PORT:-5433}:5432"
    volumes:
      - postgres_custom_data:/var/lib/postgresql/data

volumes:
  postgres_custom_data:
"""
    }
]

def list_templates() -> List[Dict[str, Any]]:
    return HOMELAB_TEMPLATES

def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    for t in HOMELAB_TEMPLATES:
        if t["id"] == template_id:
            return t
    return None


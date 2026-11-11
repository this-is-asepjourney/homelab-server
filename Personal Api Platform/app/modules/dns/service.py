"""Homelab Local DNS & Dynamic Virtual Host Router Service.

Manages:
1. CoreDNS static host mappings (homelab.hosts)
2. Ingress Nginx virtual host configs (conf.d/projects/*.conf)
3. Client hosts file export for zero-config LAN devices
"""

import logging
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("homelab.dns")

# Search candidate paths for DNS hosts and Router confs
BASE_CANDIDATES = [
    Path("/app"),
    Path("/opt/projects/homelab-server"),
    Path(__file__).resolve().parent.parent.parent.parent,
    Path("."),
]


def _resolve_existing_dir(subpath: str) -> Path:
    for base in BASE_CANDIDATES:
        cand = (base / subpath).resolve()
        if cand.exists():
            return cand
    # Fallback default
    cand = (BASE_CANDIDATES[0] / subpath).resolve()
    cand.mkdir(parents=True, exist_ok=True)
    return cand


def _resolve_existing_file(subpath: str, default_content: str = "") -> Path:
    for base in BASE_CANDIDATES:
        cand = (base / subpath).resolve()
        if cand.exists():
            return cand
    cand = (BASE_CANDIDATES[0] / subpath).resolve()
    cand.parent.mkdir(parents=True, exist_ok=True)
    if not cand.exists():
        cand.write_text(default_content, encoding="utf-8")
    return cand


DEFAULT_HOSTS_TEMPLATE = """# Homelab Local DNS Static Hosts Mapping
# Host Server: fa (Ubuntu 24.04 LTS)

192.168.25.101 homelab
192.168.25.101 psm.homelab
192.168.25.101 api.homelab
192.168.25.101 iot.homelab
192.168.25.101 grafana.homelab
192.168.25.101 prometheus.homelab
192.168.25.101 kuma.homelab
192.168.25.101 vault.homelab
192.168.25.101 cockpit.homelab
192.168.25.101 minio.homelab
192.168.25.101 s3.homelab

100.106.63.90 psm.tailscale.homelab
100.106.63.90 api.tailscale.homelab
100.106.63.90 iot.tailscale.homelab
100.106.63.90 grafana.tailscale.homelab
100.106.63.90 minio.tailscale.homelab
100.106.63.90 s3.tailscale.homelab
"""

BUILTIN_SERVICES = [
    {"domain": "homelab", "target": "pap-api:8000", "type": "Dashboard", "desc": "Homelab Mission Control UI"},
    {"domain": "psm.homelab", "target": "psm-web:3005", "type": "Console", "desc": "Personal Server Manager"},
    {"domain": "api.homelab", "target": "pap-api:8000", "type": "Core Gateway", "desc": "PAP Central API Gateway"},
    {"domain": "iot.homelab", "target": "iot-web:80", "type": "IoT Portal", "desc": "Heatpress Fleet Dashboard"},
    {"domain": "grafana.homelab", "target": "192.168.25.101:3001", "type": "Monitoring", "desc": "Grafana Visualizations"},
    {"domain": "prometheus.homelab", "target": "192.168.25.101:9001", "type": "Metrics", "desc": "Prometheus TSDB"},
    {"domain": "kuma.homelab", "target": "192.168.25.101:3002", "type": "Health Check", "desc": "Uptime Kuma Hub"},
    {"domain": "vault.homelab", "target": "192.168.25.101:8080", "type": "Security", "desc": "Vaultwarden Password Manager"},
    {"domain": "cockpit.homelab", "target": "192.168.25.101:9090", "type": "OS Management", "desc": "Ubuntu Cockpit Web Console"},
    {"domain": "minio.homelab", "target": "minio:9002", "type": "Storage Console", "desc": "MinIO S3 Web Console"},
    {"domain": "s3.homelab", "target": "minio:9000", "type": "Storage API", "desc": "MinIO S3 Object Storage API"},
]


class DnsService:
    """Manages local DNS and virtual host routing."""

    @classmethod
    def get_hosts_file_path(cls) -> Path:
        return _resolve_existing_file("dns/homelab.hosts", DEFAULT_HOSTS_TEMPLATE)

    @classmethod
    def get_projects_vhost_dir(cls) -> Path:
        return _resolve_existing_dir("router/conf.d/projects")

    @classmethod
    def sanitize_domain(cls, raw: str) -> str:
        domain = raw.strip().lower()
        if not domain.endswith(".homelab") and not domain.endswith(".local"):
            domain = f"{domain}.homelab"
        return re.sub(r"[^a-zA-Z0-9.-]", "-", domain)

    @classmethod
    def list_domains(cls) -> List[Dict[str, Any]]:
        """List all active domains (built-in + deployed projects)."""
        results = []
        host_ip = os.getenv("HOST_IP", "192.168.25.101")
        tailscale_ip = os.getenv("TAILSCALE_HOST", "100.106.63.90")

        # 1. Built-in system domains
        for svc in BUILTIN_SERVICES:
            results.append({
                "domain": svc["domain"],
                "url": f"http://{svc['domain']}",
                "target": svc["target"],
                "category": svc["type"],
                "description": svc["desc"],
                "is_system": True,
                "ip_lan": host_ip,
                "ip_tailscale": tailscale_ip,
            })

        # 2. Deployed project domains from vhost directory
        vhost_dir = cls.get_projects_vhost_dir()
        if vhost_dir.exists():
            for conf_file in vhost_dir.glob("*.conf"):
                try:
                    text = conf_file.read_text(encoding="utf-8")
                    srv_match = re.search(r"server_name\s+([^;]+);", text)
                    proxy_match = re.search(r"proxy_pass\s+([^;]+);", text)
                    if srv_match and proxy_match:
                        domain_names = srv_match.group(1).strip().split()
                        primary_domain = domain_names[0] if domain_names else conf_file.stem
                        proxy_target = proxy_match.group(1).replace("http://", "").strip()
                        results.append({
                            "domain": primary_domain,
                            "url": f"http://{primary_domain}",
                            "target": proxy_target,
                            "category": "Project App",
                            "description": f"Deployed Project ({conf_file.stem})",
                            "is_system": False,
                            "ip_lan": host_ip,
                            "ip_tailscale": tailscale_ip,
                        })
                except Exception as e:
                    logger.warning("Error reading vhost %s: %s", conf_file, e)

        return results

    @classmethod
    def register_domain_route(
        cls,
        domain: str,
        target_port: int,
        target_host: str = "host.docker.internal",
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates an Nginx virtual host for domain and adds DNS host mapping."""
        clean_domain = cls.sanitize_domain(domain)
        slug = project_name or clean_domain.replace(".homelab", "").replace(".local", "")
        vhost_dir = cls.get_projects_vhost_dir()
        vhost_file = vhost_dir / f"{clean_domain}.conf"

        # 1. Write Nginx virtual host config
        conf_content = f"""# Virtual Host for Project: {slug}
server {{
    listen 80;
    server_name {clean_domain} {slug}.fa.local;

    location / {{
        proxy_pass http://{target_host}:{target_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""
        vhost_file.write_text(conf_content, encoding="utf-8")

        # 2. Append domain to homelab.hosts if missing
        hosts_file = cls.get_hosts_file_path()
        if hosts_file.exists():
            existing = hosts_file.read_text(encoding="utf-8")
            host_ip = os.getenv("HOST_IP", "192.168.25.101")
            entry_line = f"{host_ip} {clean_domain}"
            if clean_domain not in existing:
                with open(hosts_file, "a", encoding="utf-8") as f:
                    f.write(f"\n{entry_line}")

        # 3. Reload Nginx Router if possible
        cls.reload_router()

        return {
            "success": True,
            "domain": clean_domain,
            "url": f"http://{clean_domain}",
            "target": f"{target_host}:{target_port}",
            "config_file": str(vhost_file),
        }

    @classmethod
    def remove_domain_route(cls, domain: str) -> bool:
        """Removes a virtual host config and DNS mapping."""
        clean_domain = cls.sanitize_domain(domain)
        vhost_dir = cls.get_projects_vhost_dir()
        vhost_file = vhost_dir / f"{clean_domain}.conf"
        removed = False

        if vhost_file.exists():
            try:
                vhost_file.unlink()
                removed = True
            except Exception:
                pass

        # Clean from homelab.hosts
        hosts_file = cls.get_hosts_file_path()
        if hosts_file.exists():
            try:
                lines = hosts_file.read_text(encoding="utf-8").splitlines()
                filtered = [ln for ln in lines if clean_domain not in ln]
                hosts_file.write_text("\n".join(filtered) + "\n", encoding="utf-8")
            except Exception:
                pass

        cls.reload_router()
        return removed

    @classmethod
    def reload_router(cls) -> None:
        """Attempts to signal the router container to reload its configuration."""
        for cname in ["homelab_router", "homelab-router"]:
            try:
                res = subprocess.run(
                    ["docker", "exec", cname, "nginx", "-s", "reload"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                )
                if res.returncode == 0:
                    break
            except Exception:
                pass

    @classmethod
    def generate_hosts_file_content(cls) -> str:
        """Generates ready-to-copy /etc/hosts or Windows hosts file format."""
        domains = cls.list_domains()
        host_ip = os.getenv("HOST_IP", "192.168.25.101")
        tailscale_ip = os.getenv("TAILSCALE_HOST", "100.106.63.90")

        lines = [
            "# ==================================================================",
            "# HOMELAB SERVER LOCAL DOMAIN MAPPINGS (Dell OptiPlex fa)",
            f"# Generated automatically by PAP Core • {len(domains)} Domains Active",
            "# ==================================================================",
            f"# A. LAN Connection (Rumah / Kantor - {host_ip})",
        ]
        for d in domains:
            lines.append(f"{host_ip:<16} {d['domain']}")

        lines.extend([
            "",
            f"# B. Tailscale Connection (Remote / Di Luar Rumah - {tailscale_ip})",
        ])
        for d in domains:
            lines.append(f"{tailscale_ip:<16} {d['domain'].replace('.homelab', '.tailscale.homelab')}")

        return "\n".join(lines) + "\n"

    @classmethod
    def check_dns_status(cls) -> Dict[str, Any]:
        """Verifies if Local DNS (port 53) and Ingress Router (port 80) are active."""
        host_ip = os.getenv("HOST_IP", "192.168.25.101")

        # 1. Check TCP Port 53 (DNS)
        dns_tcp = False
        try:
            with socket.create_connection((host_ip, 53), timeout=0.8):
                dns_tcp = True
        except Exception:
            # Also test localhost
            try:
                with socket.create_connection(("127.0.0.1", 53), timeout=0.5):
                    dns_tcp = True
            except Exception:
                dns_tcp = False

        # 2. Check Port 80 (Ingress Router)
        router_http = False
        try:
            with socket.create_connection((host_ip, 80), timeout=0.8):
                router_http = True
        except Exception:
            router_http = False

        return {
            "dns_server_port_53": "ONLINE" if dns_tcp else "INITIALIZING",
            "ingress_router_port_80": "ONLINE" if router_http else "INITIALIZING",
            "host_lan_ip": host_ip,
            "host_tailscale_ip": os.getenv("TAILSCALE_HOST", "100.106.63.90"),
            "domain_zone": ".homelab (and .fa.local)",
            "total_domains_active": len(cls.list_domains()),
        }


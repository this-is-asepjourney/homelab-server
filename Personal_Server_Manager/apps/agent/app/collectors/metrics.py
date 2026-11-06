import os
import platform
import socket
import time
import psutil
from typing import Dict, Any, List
from apps.agent.app.docker.client import docker_manager

_last_net_io = None
_last_net_time = None
_last_disk_io = None
_last_disk_time = None


def get_system_info() -> Dict[str, Any]:
    uname = platform.uname()
    return {
        "hostname": uname.node,
        "os_name": uname.system,
        "os_version": uname.release,
        "architecture": uname.machine,
        "processor": uname.processor,
        "python_version": platform.python_version(),
    }


def collect_network_interfaces() -> List[Dict[str, Any]]:
    interfaces = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        pernic_io = psutil.net_io_counters(pernic=True)

        for iface_name, addr_list in addrs.items():
            ipv4 = ""
            netmask = ""
            ipv6 = ""
            mac = ""
            for addr in addr_list:
                if addr.family == socket.AF_INET:
                    ipv4 = addr.address
                    netmask = addr.netmask or ""
                elif addr.family == socket.AF_INET6:
                    if not ipv6:
                        ipv6 = addr.address.split("%")[0]
                elif hasattr(psutil, "AF_LINK") and addr.family == psutil.AF_LINK:
                    mac = addr.address

            st = stats.get(iface_name)
            io = pernic_io.get(iface_name)

            iface_type = "ethernet"
            lower_name = iface_name.lower()
            if lower_name == "lo" or "loopback" in lower_name:
                iface_type = "loopback"
            elif "tailscale" in lower_name or "ts" in lower_name or "tun" in lower_name or "wg" in lower_name:
                iface_type = "vpn"
            elif "docker" in lower_name or "br-" in lower_name or "veth" in lower_name:
                iface_type = "docker"
            elif "wl" in lower_name or "wlan" in lower_name or "wifi" in lower_name:
                iface_type = "wireless"

            interfaces.append({
                "name": iface_name,
                "type": iface_type,
                "is_up": bool(st.isup) if st else False,
                "speed_mbps": int(st.speed) if st and st.speed else 0,
                "mtu": int(st.mtu) if st and st.mtu else 1500,
                "ipv4": ipv4,
                "netmask": netmask,
                "ipv6": ipv6,
                "mac": mac,
                "rx_bytes": int(io.bytes_recv) if io else 0,
                "tx_bytes": int(io.bytes_sent) if io else 0,
                "rx_packets": int(io.packets_recv) if io else 0,
                "tx_packets": int(io.packets_sent) if io else 0,
                "err_in": int(io.errin) if io else 0,
                "err_out": int(io.errout) if io else 0,
            })
    except Exception:
        pass
    return interfaces


def collect_listening_ports_and_connections() -> Dict[str, Any]:
    listening_ports = []
    seen_ports = set()
    conn_counts = {
        "established": 0,
        "listen": 0,
        "time_wait": 0,
        "close_wait": 0,
        "total": 0,
    }

    KNOWN_SERVICES = {
        22: "SSH Server",
        53: "DNS (systemd-resolved / AdGuard)",
        80: "Nextcloud / HTTP Web",
        443: "HTTPS Web",
        1883: "Mosquitto MQTT Broker",
        3000: "Web Service / AdGuard UI",
        3001: "Grafana Dashboard",
        3002: "Uptime Kuma",
        3005: "PSM Web Console",
        5432: "PostgreSQL Database",
        6379: "Redis Cache",
        8000: "PSM Control Plane API",
        8080: "Vaultwarden / Web Proxy",
        9000: "Portainer / Sonar",
        9001: "Prometheus Snap",
        9090: "Cockpit Web Console",
        9443: "Portainer HTTPS",
    }

    try:
        conns = psutil.net_connections(kind="inet")
        for c in conns:
            conn_counts["total"] += 1
            st = (c.status or "").upper()
            if st == "ESTABLISHED":
                conn_counts["established"] += 1
            elif st == "LISTEN":
                conn_counts["listen"] += 1
            elif st == "TIME_WAIT":
                conn_counts["time_wait"] += 1
            elif st == "CLOSE_WAIT":
                conn_counts["close_wait"] += 1

            if st == "LISTEN" and c.laddr:
                port = c.laddr.port
                proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
                key = f"{proto}:{port}"
                if key in seen_ports:
                    continue
                seen_ports.add(key)

                proc_name = KNOWN_SERVICES.get(port, "")
                if c.pid and not proc_name:
                    try:
                        proc_name = psutil.Process(c.pid).name()
                    except Exception:
                        proc_name = "system-service"
                elif not proc_name:
                    proc_name = "container/service"

                listening_ports.append({
                    "port": port,
                    "protocol": proto,
                    "bind_address": c.laddr.ip,
                    "pid": c.pid or 0,
                    "service": proc_name,
                    "status": "LISTEN",
                })
    except Exception:
        pass

    listening_ports.sort(key=lambda x: x["port"])
    return {
        "listening_ports": listening_ports,
        "connection_stats": conn_counts,
    }


def get_metrics_snapshot() -> Dict[str, Any]:
    global _last_net_io, _last_net_time, _last_disk_io, _last_disk_time

    now = time.time()

    # CPU
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True) or 1

    # Load average (Linux/Unix)
    load_avg = [0.0, 0.0, 0.0]
    if hasattr(os, "getloadavg"):
        try:
            load_avg = [round(x, 2) for x in os.getloadavg()]
        except Exception:
            pass

    # Memory & Swap
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Primary Disk
    disk = psutil.disk_usage("/") if platform.system() != "Windows" else psutil.disk_usage("C:\\")

    # Disk I/O Read/Write
    disk_read_bytes = 0
    disk_write_bytes = 0
    disk_read_count = 0
    disk_write_count = 0
    disk_read_rate = 0.0
    disk_write_rate = 0.0
    try:
        dio = psutil.disk_io_counters()
        if dio:
            disk_read_bytes = int(dio.read_bytes)
            disk_write_bytes = int(dio.write_bytes)
            disk_read_count = int(dio.read_count)
            disk_write_count = int(dio.write_count)
            if _last_disk_io and _last_disk_time:
                elapsed_d = max(now - _last_disk_time, 0.001)
                disk_read_rate = max(0.0, (dio.read_bytes - _last_disk_io.read_bytes) / elapsed_d)
                disk_write_rate = max(0.0, (dio.write_bytes - _last_disk_io.write_bytes) / elapsed_d)
            _last_disk_io = dio
            _last_disk_time = now
    except Exception:
        pass

    # Disk partitions (Used & Unused/Free)
    partitions_data = []
    seen_mounts = set()
    try:
        for p in psutil.disk_partitions(all=False):
            if "cdrom" in p.opts or not p.fstype:
                continue
            if p.mountpoint in seen_mounts:
                continue
            seen_mounts.add(p.mountpoint)
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions_data.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "opts": p.opts,
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "percent": round(usage.percent, 1),
                })
            except (PermissionError, Exception):
                pass
    except Exception:
        pass

    # Network delta & counters
    net_io = psutil.net_io_counters()
    rx_rate = 0.0
    tx_rate = 0.0
    if _last_net_io and _last_net_time:
        elapsed = max(now - _last_net_time, 0.001)
        rx_rate = max(0.0, (net_io.bytes_recv - _last_net_io.bytes_recv) / elapsed)
        tx_rate = max(0.0, (net_io.bytes_sent - _last_net_io.bytes_sent) / elapsed)

    _last_net_io = net_io
    _last_net_time = now

    # Network interfaces & listening ports
    net_interfaces = collect_network_interfaces()
    ports_and_conns = collect_listening_ports_and_connections()

    # Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = int(now - boot_time)

    # Per-container live stats from Docker
    container_stats = []
    try:
        container_stats = docker_manager.get_all_container_stats()
    except Exception:
        pass

    return {
        "cpu_usage": round(cpu_percent, 1),
        "cpu_cores": cpu_cores,
        "load_avg": load_avg,
        "memory_usage": round(mem.percent, 1),
        "memory_used_bytes": mem.used,
        "memory_total_bytes": mem.total,
        "memory_available_bytes": mem.available,
        "swap_used_bytes": swap.used,
        "swap_total_bytes": swap.total,
        "disk_usage": round(disk.percent, 1),
        "disk_used_bytes": disk.used,
        "disk_free_bytes": disk.free,
        "disk_total_bytes": disk.total,
        "disk_read_bytes": disk_read_bytes,
        "disk_write_bytes": disk_write_bytes,
        "disk_read_count": disk_read_count,
        "disk_write_count": disk_write_count,
        "disk_read_bytes_per_sec": round(disk_read_rate, 1),
        "disk_write_bytes_per_sec": round(disk_write_rate, 1),
        "disk_partitions": partitions_data,
        "network_rx_bytes_per_sec": round(rx_rate, 1),
        "network_tx_bytes_per_sec": round(tx_rate, 1),
        "network_total_rx_bytes": int(net_io.bytes_recv),
        "network_total_tx_bytes": int(net_io.bytes_sent),
        "network_packets_recv": int(net_io.packets_recv),
        "network_packets_sent": int(net_io.packets_sent),
        "network_err_in": int(net_io.errin),
        "network_err_out": int(net_io.errout),
        "network_drop_in": int(net_io.dropin),
        "network_drop_out": int(net_io.dropout),
        "network_interfaces": net_interfaces,
        "listening_ports": ports_and_conns["listening_ports"],
        "connection_stats": ports_and_conns["connection_stats"],
        "uptime_seconds": uptime_seconds,
        "container_stats": container_stats,
    }

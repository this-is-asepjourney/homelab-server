"""Homelab Unified Backup Engine.

Backs up all databases (PostgreSQL: psm, pap_core; MySQL: eternal_db, stock_umkm; InfluxDB: eternal_telemetry)
and service configurations (Docker, CoreDNS, Ingress Router, Prometheus, Mosquitto, Telegraf, .env)
into standalone timestamped compressed tarballs (.tar.gz).
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger("homelab.backups")

# Persistent directory for storing homelab backup archives
BACKUP_DIR = Path(os.getenv("BACKUP_STORAGE_DIR", "/app/backups")).resolve()
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


class BackupService:
    """Orchestrates full and partial backups across all Homelab Server projects."""

    @classmethod
    def get_backup_dir(cls) -> Path:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        return BACKUP_DIR

    @classmethod
    def _export_postgres_database(
        cls, db_name: str, out_dir: Path
    ) -> Dict[str, Any]:
        """Dumps a PostgreSQL database using pg_dump if available, or SQLAlchemy fallback."""
        out_sql = out_dir / f"{db_name}.sql"
        host = os.getenv("POSTGRES_HOST", "192.168.25.101")
        port = os.getenv("POSTGRES_PORT", "5432")
        user = os.getenv("POSTGRES_USER", "appuser")
        password = os.getenv("POSTGRES_PASSWORD", "admin12345")

        # 1. Attempt native pg_dump if available
        pg_dump_bin = shutil.which("pg_dump")
        if pg_dump_bin:
            env = os.environ.copy()
            env["PGPASSWORD"] = password
            cmd = [
                pg_dump_bin,
                "-h", host,
                "-p", str(port),
                "-U", user,
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "-f", str(out_sql),
                db_name,
            ]
            try:
                res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=90)
                if res.returncode == 0 and out_sql.exists() and out_sql.stat().st_size > 0:
                    return {
                        "status": "success",
                        "method": "pg_dump",
                        "database": db_name,
                        "file": out_sql.name,
                        "size_bytes": out_sql.stat().st_size,
                    }
                logger.warning("pg_dump failed for %s: %s; falling back to SQLAlchemy", db_name, res.stderr)
            except Exception as e:
                logger.warning("pg_dump error for %s: %s; falling back to SQLAlchemy", db_name, e)

        # 2. SQLAlchemy Introspection Fallback (100% resilient)
        candidates = [
            f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}",
            f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}",
            f"postgresql+psycopg://{user}:{password}@host.docker.internal:{port}/{db_name}",
            f"postgresql+psycopg://postgres:{password}@{host}:{port}/{db_name}",
        ]
        eng = None
        for conn_str in candidates:
            try:
                test_eng = create_engine(conn_str, connect_args={"connect_timeout": 3})
                with test_eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                eng = test_eng
                break
            except Exception:
                continue

        if not eng:
            return {"status": "skipped_unreachable", "database": db_name, "error": "Database unreachable"}

        try:
            inspector = inspect(eng)
            table_names = inspector.get_table_names()
            total_rows = 0
            with open(out_sql, "w", encoding="utf-8") as f:
                f.write(f"-- Homelab Backup for PostgreSQL Database: {db_name}\n")
                f.write(f"-- Generated At: {datetime.now(timezone.utc).isoformat()}\n\n")
                f.write("BEGIN;\n\n")

                with eng.connect() as conn:
                    for tbl in table_names:
                        try:
                            rows = conn.execute(text(f'SELECT * FROM "{tbl}"')).mappings().all()
                            total_rows += len(rows)
                            f.write(f"-- Table: {tbl} ({len(rows)} rows)\n")
                            for r in rows:
                                cols = list(r.keys())
                                vals = []
                                for k in cols:
                                    v = r[k]
                                    if v is None:
                                        vals.append("NULL")
                                    elif isinstance(v, (int, float)):
                                        vals.append(str(v))
                                    elif isinstance(v, bool):
                                        vals.append("TRUE" if v else "FALSE")
                                    else:
                                        escaped = str(v).replace("'", "''")
                                        vals.append(f"'{escaped}'")
                                col_str = ", ".join([f'"{c}"' for c in cols])
                                val_str = ", ".join(vals)
                                f.write(f'INSERT INTO "{tbl}" ({col_str}) VALUES ({val_str}) ON CONFLICT DO NOTHING;\n')
                            f.write("\n")
                        except Exception as te:
                            f.write(f"-- Warning: Failed to dump table {tbl}: {te}\n")

                f.write("COMMIT;\n")

            return {
                "status": "success",
                "method": "sqlalchemy_stream",
                "database": db_name,
                "file": out_sql.name,
                "tables_count": len(table_names),
                "total_rows": total_rows,
                "size_bytes": out_sql.stat().st_size,
            }
        except Exception as e:
            return {"status": "error", "database": db_name, "error": str(e)}

    @classmethod
    def _export_mysql_database(cls, db_name: str, out_dir: Path) -> Dict[str, Any]:
        """Dumps a MySQL database (e.g. eternal_db, stock_umkm)."""
        out_sql = out_dir / f"{db_name}.sql"
        host = os.getenv("MYSQL_HOST") or os.getenv("STOCK_DB_HOST", "192.168.25.101")
        port = os.getenv("MYSQL_PORT") or os.getenv("STOCK_DB_PORT", "3306")
        user = os.getenv("MYSQL_USER") or os.getenv("STOCK_DB_USER", "appuser")
        password = os.getenv("MYSQL_PASSWORD") or os.getenv("STOCK_DB_PASSWORD", "admin12345")

        # 1. Native mysqldump / mariadb-dump
        dump_bin = shutil.which("mariadb-dump") or shutil.which("mysqldump")
        if dump_bin:
            cmd = [
                dump_bin,
                "-h", host,
                "-P", str(port),
                "-u", user,
                f"-p{password}",
                "--skip-lock-tables",
                "--result-file", str(out_sql),
                db_name,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                if res.returncode == 0 and out_sql.exists() and out_sql.stat().st_size > 0:
                    return {
                        "status": "success",
                        "method": "mysqldump",
                        "database": db_name,
                        "file": out_sql.name,
                        "size_bytes": out_sql.stat().st_size,
                    }
            except Exception:
                pass

        # 2. Fallback via SQLAlchemy PyMySQL
        candidates = [
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}",
            f"mysql+pymysql://{user}:{password}@host.docker.internal:{port}/{db_name}",
            f"mysql+pymysql://root:{os.getenv('MYSQL_ROOT_PASSWORD', password)}@{host}:{port}/{db_name}",
        ]
        eng = None
        for conn_str in candidates:
            try:
                test_eng = create_engine(conn_str, connect_args={"connect_timeout": 3})
                with test_eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                eng = test_eng
                break
            except Exception:
                continue

        if not eng:
            return {"status": "skipped_unreachable", "database": db_name, "error": f"MySQL {db_name} unreachable"}

        try:
            inspector = inspect(eng)
            table_names = inspector.get_table_names()
            total_rows = 0
            with open(out_sql, "w", encoding="utf-8") as f:
                f.write(f"-- Homelab Backup for MySQL Database: {db_name}\n")
                f.write(f"-- Generated At: {datetime.now(timezone.utc).isoformat()}\n\n")
                f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

                with eng.connect() as conn:
                    for tbl in table_names:
                        try:
                            rows = conn.execute(text(f"SELECT * FROM `{tbl}`")).mappings().all()
                            total_rows += len(rows)
                            f.write(f"-- Table: `{tbl}` ({len(rows)} rows)\n")
                            for r in rows:
                                cols = list(r.keys())
                                vals = []
                                for k in cols:
                                    v = r[k]
                                    if v is None:
                                        vals.append("NULL")
                                    elif isinstance(v, (int, float)):
                                        vals.append(str(v))
                                    elif isinstance(v, bool):
                                        vals.append("1" if v else "0")
                                    else:
                                        escaped = str(v).replace("'", "''").replace("\\", "\\\\")
                                        vals.append(f"'{escaped}'")
                                col_str = ", ".join([f"`{c}`" for c in cols])
                                val_str = ", ".join(vals)
                                f.write(f"INSERT INTO `{tbl}` ({col_str}) VALUES ({val_str});\n")
                            f.write("\n")
                        except Exception as te:
                            f.write(f"-- Warning: Failed to dump table {tbl}: {te}\n")

                f.write("SET FOREIGN_KEY_CHECKS = 1;\n")

            return {
                "status": "success",
                "method": "sqlalchemy_stream",
                "database": db_name,
                "file": out_sql.name,
                "tables_count": len(table_names),
                "total_rows": total_rows,
                "size_bytes": out_sql.stat().st_size,
            }
        except Exception as e:
            return {"status": "error", "database": db_name, "error": str(e)}

    @classmethod
    def _export_influxdb_database(cls, out_dir: Path) -> Dict[str, Any]:
        """Dumps InfluxDB timeseries data points using Flux query to annotated CSV."""
        from app.services.influxdb_service import influx_service

        bucket = os.getenv("INFLUXDB_BUCKET", getattr(influx_service, "bucket", "eternal_telemetry"))
        org = os.getenv("INFLUXDB_ORG", getattr(influx_service, "org", "homelab"))
        token = os.getenv("INFLUXDB_TOKEN", getattr(influx_service, "token", "homelab-influxdb-master-auth-token-2026"))
        base_url = (os.getenv("INFLUXDB_URL") or getattr(influx_service, "url", "http://influxdb:8086")).rstrip("/")

        out_csv = out_dir / f"{bucket}.flux.csv"

        test_urls = [
            f"{base_url}/api/v2/query?org={urllib.parse.quote(org)}",
            f"http://127.0.0.1:8086/api/v2/query?org={urllib.parse.quote(org)}",
            f"http://192.168.25.101:8086/api/v2/query?org={urllib.parse.quote(org)}",
        ]

        flux_query = f'from(bucket: "{bucket}") |> range(start: -30d)'
        payload = json.dumps({"query": flux_query, "type": "flux"}).encode("utf-8")
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/csv",
        }

        for q_url in test_urls:
            try:
                req = urllib.request.Request(q_url, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        content = resp.read()
                        out_csv.write_bytes(content)
                        return {
                            "status": "success",
                            "method": "flux_query_csv",
                            "bucket": bucket,
                            "org": org,
                            "file": out_csv.name,
                            "size_bytes": out_csv.stat().st_size,
                        }
            except Exception as e:
                logger.debug("Influx query attempt to %s failed: %s", q_url, e)
                continue

        # If InfluxDB is unreachable or empty
        return {
            "status": "skipped",
            "bucket": bucket,
            "error": "InfluxDB service unreachable or no data points found",
        }

    @classmethod
    def _collect_configs(cls, out_dir: Path) -> List[Dict[str, Any]]:
        """Collects Docker Compose, environment files, CoreDNS, and Nginx Router Virtual Host configs."""
        collected = []
        search_paths = [
            # Docker Compose
            ("/opt/projects/homelab-server/docker-compose.yml", "docker-compose.yml"),
            ("docker-compose.yml", "docker-compose.yml"),
            ("../docker-compose.yml", "docker-compose.yml"),
            # Environment file
            ("/opt/projects/homelab-server/.env", "homelab.env"),
            (".env", "homelab.env"),
            ("../.env", "homelab.env"),
            # Mosquitto MQTT Config
            ("/opt/homelab/mosquitto/config/mosquitto.conf", "mosquitto.conf"),
            ("mosquitto/config/mosquitto.conf", "mosquitto.conf"),
            ("../mosquitto/config/mosquitto.conf", "mosquitto.conf"),
            # Prometheus Config
            ("/opt/homelab/prometheus/config/prometheus.yml", "prometheus.yml"),
            ("prometheus/config/prometheus.yml", "prometheus.yml"),
            ("../prometheus/config/prometheus.yml", "prometheus.yml"),
            # IoT Telegraf Config
            ("dashboard_iot/telegraf/telegraf.conf", "telegraf.conf"),
            ("../dashboard_iot/telegraf/telegraf.conf", "telegraf.conf"),
            ("/opt/projects/homelab-server/dashboard_iot/telegraf/telegraf.conf", "telegraf.conf"),
        ]

        copied_names = set()
        for src_candidate, dest_name in search_paths:
            if dest_name in copied_names:
                continue
            p = Path(src_candidate).resolve()
            if p.exists() and p.is_file():
                dest_file = out_dir / dest_name
                try:
                    shutil.copy2(p, dest_file)
                    copied_names.add(dest_name)
                    collected.append({
                        "name": dest_name,
                        "source": str(p),
                        "size_bytes": dest_file.stat().st_size,
                    })
                except Exception as e:
                    logger.warning("Failed to copy %s: %s", p, e)

        # Collect CoreDNS configurations
        dns_out = out_dir / "dns"
        dns_out.mkdir(parents=True, exist_ok=True)
        for cand in [Path("dns"), Path("../dns"), Path("/opt/projects/homelab-server/dns"), Path("/app/dns")]:
            if cand.exists() and cand.is_dir():
                for f in cand.glob("*"):
                    if f.is_file():
                        target_f = dns_out / f.name
                        shutil.copy2(f, target_f)
                        collected.append({
                            "name": f"dns/{f.name}",
                            "source": str(f),
                            "size_bytes": target_f.stat().st_size,
                        })
                break

        # Collect Nginx Ingress configurations and all Virtual Hosts
        router_out = out_dir / "router"
        router_out.mkdir(parents=True, exist_ok=True)
        for cand in [Path("router"), Path("../router"), Path("/opt/projects/homelab-server/router"), Path("/app/router")]:
            if cand.exists() and cand.is_dir():
                for f in cand.rglob("*.conf"):
                    if f.is_file():
                        rel = f.relative_to(cand)
                        target_f = router_out / rel
                        target_f.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, target_f)
                        collected.append({
                            "name": f"router/{rel}",
                            "source": str(f),
                            "size_bytes": target_f.stat().st_size,
                        })
                break

        return collected

    @classmethod
    def create_backup(cls, scope: str = "all", note: str = "") -> Dict[str, Any]:
        """Creates a timestamped backup archive according to scope ('all', 'databases', 'configs')."""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        backup_id = f"homelab_backup_{timestamp_str}"
        archive_name = f"{backup_id}.tar.gz"
        archive_path = BACKUP_DIR / archive_name

        with tempfile.TemporaryDirectory(prefix="homelab_bup_") as tmp_dir_raw:
            tmp_dir = Path(tmp_dir_raw)
            stage_dir = tmp_dir / backup_id
            stage_dir.mkdir(parents=True, exist_ok=True)

            db_results = {}
            config_results = []

            # 1. Databases Backup (All 5 databases in Homelab)
            if scope in ("all", "databases"):
                db_dir = stage_dir / "databases"
                db_dir.mkdir(parents=True, exist_ok=True)

                # PostgreSQL PSM
                db_results["psm"] = cls._export_postgres_database("psm", db_dir)
                # PostgreSQL PAP Core
                db_results["pap_core"] = cls._export_postgres_database("pap_core", db_dir)

                # MySQL eternal_db (NFC Users, Device Locks, Access Logs)
                db_results["eternal_db"] = cls._export_mysql_database("eternal_db", db_dir)
                # MySQL stock_umkm (Products, Transactions, Inventory)
                db_results["stock_umkm"] = cls._export_mysql_database("stock_umkm", db_dir)

                # InfluxDB 2.7 TSDB (Sensor DHT11 timeseries metrics)
                db_results["influx_telemetry"] = cls._export_influxdb_database(db_dir)

            # 2. Configs Backup (Docker, DNS, Router VHosts, Mosquitto, Prometheus, Telegraf)
            if scope in ("all", "configs"):
                cfg_dir = stage_dir / "configs"
                cfg_dir.mkdir(parents=True, exist_ok=True)
                config_results = cls._collect_configs(cfg_dir)

            # 3. Create Manifest
            manifest_data = {
                "backup_id": backup_id,
                "version": "2.0",
                "created_at": now.isoformat(),
                "scope": scope,
                "note": note or "Automated Homelab Unified Full-Stack Backup",
                "system": {
                    "host": os.getenv("HOSTNAME", "fa-server"),
                    "ip": os.getenv("HOST_IP", "192.168.25.101"),
                    "tailscale": os.getenv("TAILSCALE_HOST", "100.106.63.90"),
                },
                "databases": db_results,
                "configs": config_results,
            }
            manifest_file = stage_dir / "manifest.json"
            with open(manifest_file, "w", encoding="utf-8") as mf:
                json.dump(manifest_data, mf, indent=2)

            # 4. Pack into .tar.gz
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(stage_dir, arcname=backup_id)

        # 5. Calculate SHA256 & final metadata
        sha256 = _calculate_sha256(archive_path)
        size_bytes = archive_path.stat().st_size

        manifest_data["archive"] = {
            "filename": archive_name,
            "filepath": str(archive_path),
            "size_bytes": size_bytes,
            "size_human": _format_size(size_bytes),
            "sha256": sha256,
        }

        # Store a sidecar manifest for instant list without unpacking
        sidecar_meta = BACKUP_DIR / f"{backup_id}.manifest.json"
        try:
            with open(sidecar_meta, "w", encoding="utf-8") as sf:
                json.dump(manifest_data, sf, indent=2)
        except Exception:
            pass

        return manifest_data

    @classmethod
    def verify_backup(cls, filename: str) -> Dict[str, Any]:
        """Performs a comprehensive integrity check and test-parsing of a backup archive."""
        safe_name = Path(filename).name
        target = BACKUP_DIR / safe_name
        if not target.exists() or not target.is_file():
            return {"exists": False, "filename": safe_name, "error": "Archive file not found"}

        stat = target.stat()
        computed_sha = _calculate_sha256(target)

        report: Dict[str, Any] = {
            "exists": True,
            "filename": safe_name,
            "size_bytes": stat.st_size,
            "size_human": _format_size(stat.st_size),
            "sha256": computed_sha,
            "tar_intact": False,
            "manifest_intact": False,
            "databases": {},
            "configs": {},
            "integrity_score_percent": 0,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with tarfile.open(target, "r:gz") as tar:
                members = tar.getmembers()
                report["tar_intact"] = True
                report["total_files"] = len(members)

                manifest = None
                for m in members:
                    if m.name.endswith("manifest.json"):
                        f = tar.extractfile(m)
                        if f:
                            manifest = json.load(f)
                            report["manifest_intact"] = True
                            report["manifest_meta"] = {
                                "backup_id": manifest.get("backup_id"),
                                "created_at": manifest.get("created_at"),
                                "scope": manifest.get("scope"),
                                "system": manifest.get("system"),
                            }
                            break

                # Validate individual database dumps inside archive
                total_checks = 0
                passed_checks = 0

                for m in members:
                    if "databases/" in m.name and not m.isdir():
                        base_name = Path(m.name).name
                        f = tar.extractfile(m)
                        if f:
                            head_bytes = f.read(2048).decode("utf-8", errors="ignore")
                            total_checks += 1
                            is_valid_sql = ("BEGIN" in head_bytes or "INSERT INTO" in head_bytes or "CREATE TABLE" in head_bytes or "-- Table:" in head_bytes)
                            is_valid_csv = ("#datatype" in head_bytes or "_result" in head_bytes or "table" in head_bytes)
                            is_valid = is_valid_sql or is_valid_csv or m.size > 0
                            if is_valid:
                                passed_checks += 1
                            report["databases"][base_name] = {
                                "file": base_name,
                                "size_bytes": m.size,
                                "size_human": _format_size(m.size),
                                "format": "flux_csv" if base_name.endswith(".csv") else "sql",
                                "valid": is_valid,
                            }
                    elif "configs/" in m.name and not m.isdir():
                        base_name = Path(m.name).name
                        total_checks += 1
                        if m.size > 0:
                            passed_checks += 1
                        report["configs"][base_name] = {
                            "file": base_name,
                            "size_bytes": m.size,
                            "size_human": _format_size(m.size),
                            "valid": m.size > 0,
                        }

                score = round((passed_checks / max(1, total_checks)) * 100, 1)
                report["integrity_score_percent"] = score
                report["status"] = "PASSED" if score >= 90 else "WARNING"

        except Exception as e:
            report["tar_intact"] = False
            report["error"] = str(e)
            report["status"] = "FAILED"

        return report

    @classmethod
    def list_backups(cls) -> List[Dict[str, Any]]:
        """Lists all existing backup archives sorted by creation date descending."""
        results = []
        for file in sorted(BACKUP_DIR.glob("homelab_backup_*.tar.gz"), key=os.path.getmtime, reverse=True):
            sidecar = file.with_suffix("").with_suffix(".manifest.json")
            meta = None
            if sidecar.exists():
                try:
                    with open(sidecar, "r", encoding="utf-8") as sf:
                        meta = json.load(sf)
                except Exception:
                    meta = None

            stat = file.stat()
            size_bytes = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)

            item = {
                "filename": file.name,
                "size_bytes": size_bytes,
                "size_human": _format_size(size_bytes),
                "created_at": meta.get("created_at") if meta else mtime.isoformat(),
                "scope": meta.get("scope", "all") if meta else "unknown",
                "note": meta.get("note", "") if meta else "",
                "sha256": meta.get("archive", {}).get("sha256", "") if meta else "",
                "databases": meta.get("databases", {}) if meta else {},
                "configs_count": len(meta.get("configs", [])) if meta else 0,
            }
            results.append(item)
        return results

    @classmethod
    def get_backup_manifest(cls, filename: str) -> Optional[Dict[str, Any]]:
        """Returns the manifest of a specific backup archive."""
        safe_name = Path(filename).name
        target = BACKUP_DIR / safe_name
        if not target.exists() or not target.is_file():
            return None

        # Check sidecar first
        sidecar = target.with_suffix("").with_suffix(".manifest.json")
        if sidecar.exists():
            try:
                with open(sidecar, "r", encoding="utf-8") as sf:
                    return json.load(sf)
            except Exception:
                pass

        # Read from tar.gz
        try:
            with tarfile.open(target, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("manifest.json"):
                        f = tar.extractfile(member)
                        if f:
                            return json.load(f)
        except Exception as e:
            logger.error("Error reading manifest from %s: %s", filename, e)

        return None

    @classmethod
    def delete_backup(cls, filename: str) -> bool:
        """Deletes a backup archive and its sidecar manifest safely."""
        safe_name = Path(filename).name
        target = BACKUP_DIR / safe_name
        if not target.exists() or not target.is_file():
            return False

        try:
            target.unlink()
            sidecar = target.with_suffix("").with_suffix(".manifest.json")
            if sidecar.exists():
                sidecar.unlink()
            return True
        except Exception as e:
            logger.error("Error deleting backup %s: %s", filename, e)
            return False

    @classmethod
    def prune_backups(cls, keep_days: int = 7, keep_min: int = 3) -> Dict[str, Any]:
        """Prunes backup archives older than keep_days while retaining at least keep_min latest backups."""
        backups = cls.list_backups()
        if len(backups) <= keep_min:
            return {"pruned": 0, "remaining": len(backups), "pruned_files": []}

        now_ts = datetime.now(timezone.utc).timestamp()
        cutoff_sec = max(1, keep_days) * 86400
        pruned_files = []

        # List is already sorted newest first; protect the first keep_min items
        candidates = backups[keep_min:]
        for b in candidates:
            created_at_str = b.get("created_at")
            if not created_at_str:
                continue
            try:
                # Handle ISO 8601 parsing
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str[:-1] + "+00:00"
                created_dt = datetime.fromisoformat(created_at_str)
                age_sec = now_ts - created_dt.timestamp()
                if age_sec > cutoff_sec:
                    filename = b.get("filename")
                    if filename and cls.delete_backup(filename):
                        pruned_files.append(filename)
                        logger.info("Pruned old backup archive: %s (age %.1f days)", filename, age_sec / 86400)
            except Exception as e:
                logger.debug("Skip pruning candidate %s: %s", b.get("filename"), e)
                continue

        return {
            "pruned": len(pruned_files),
            "remaining": len(backups) - len(pruned_files),
            "pruned_files": pruned_files,
        }

    @classmethod
    def get_backup_path(cls, filename: str) -> Optional[Path]:
        """Validates and returns the Path for downloading."""
        safe_name = Path(filename).name
        target = BACKUP_DIR / safe_name
        if target.exists() and target.is_file() and target.name.endswith(".tar.gz"):
            return target
        return None

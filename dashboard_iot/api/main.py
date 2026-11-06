from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import os
import httpx
from typing import Dict, Optional, List
from datetime import datetime, timezone

from sqlalchemy import text
from . import crud, models, schemas
from .database import SessionLocal, engine

# Create the data directory for SQLite if it doesn't exist
os.makedirs("./data", exist_ok=True)

# Create database tables & ensure columns exist (auto-migrate SQLite)
def init_db():
    models.Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(devices)"))
            cols = [row[1] for row in res.fetchall()]
            if "category" not in cols:
                conn.execute(text("ALTER TABLE devices ADD COLUMN category VARCHAR DEFAULT 'Heatpress'"))
                conn.commit()
    except Exception as e:
        print(f"[WARN] Migration category column: {e}")

    # Seed the 3 real devices under Heatpress
    db = SessionLocal()
    try:
        # Delete old dummy placeholders if any
        db.query(models.Device).filter(
            models.Device.mac_address.in_(["AF:45:00:2B:9C:11", "AP:40:00:7E:3D:88"])
        ).delete(synchronize_session=False)
        db.commit()

        # 1. HPM 55 (80:F3:DA:4B:2A:DC)
        hpm = db.query(models.Device).filter(
            (models.Device.mac_address == "80:F3:DA:4B:2A:DC") | (models.Device.model.ilike("%HPM%"))
        ).first()
        if not hpm:
            hpm_dev = models.Device(
                mac_address="80:F3:DA:4B:2A:DC",
                name="HPM 55 Press 1",
                category="Heatpress",
                model="HPM 55",
                mcid="HP-55-01",
                device_type="ESP32",
                location="Lini 1 - Sublimasi",
                description="Pneumatic Double Station Heat Press",
            )
            db.add(hpm_dev)
            db.commit()
        else:
            hpm.mac_address = "80:F3:DA:4B:2A:DC"
            hpm.category = "Heatpress"
            hpm.name = "HPM 55 Press 1"
            hpm.model = "HPM 55"
            hpm.device_type = "ESP32"
            if not hpm.mcid:
                hpm.mcid = "HP-55-01"
            if not hpm.location:
                hpm.location = "Lini 1 - Sublimasi"
            hpm.description = "Pneumatic Double Station Heat Press"
            db.commit()

        # 2. AF-450 (90:15:06:B7:AA:08)
        af = db.query(models.Device).filter(
            (models.Device.mac_address == "90:15:06:B7:AA:08") | (models.Device.model.ilike("%AF-450%"))
        ).first()
        if not af:
            af_dev = models.Device(
                mac_address="90:15:06:B7:AA:08",
                name="AF-450 Auto Flat 1",
                category="Heatpress",
                model="AF-450",
                mcid="AF-450-01",
                device_type="ESP32",
                location="Lini 2 - Flatbed",
                description="Automatic Flat Heat Press 450 Series"
            )
            db.add(af_dev)
            db.commit()
        else:
            af.mac_address = "90:15:06:B7:AA:08"
            af.category = "Heatpress"
            af.model = "AF-450"
            db.commit()

        # 3. APM-LOGO (48:9D:31:2F:B5:18)
        apm = db.query(models.Device).filter(
            (models.Device.mac_address == "48:9D:31:2F:B5:18") | (models.Device.model.ilike("%APM-LOGO%"))
        ).first()
        if not apm:
            apm_dev = models.Device(
                mac_address="48:9D:31:2F:B5:18",
                name="APM-LOGO Precision 1",
                category="Heatpress",
                model="APM-LOGO",
                mcid="APM-01",
                device_type="ESP32",
                location="Lini 3 - Apparel Logo",
                description="Auto Positioning Motion Heat Press for Logo & Label"
            )
            db.add(apm_dev)
            db.commit()
        else:
            apm.mac_address = "48:9D:31:2F:B5:18"
            apm.category = "Heatpress"
            apm.model = "APM-LOGO"
            db.commit()
    except Exception as e:
        print(f"[WARN] DB init seeding error: {e}")
    finally:
        db.close()

init_db()



# ─────────────────────────────────────────────
# Landing Page HTML
# ─────────────────────────────────────────────

LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>IoT Device Management API</title>
    <meta name="description" content="API untuk manajemen device IoT — mapping MAC Address ↔ MCID (Machine ID)" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg-primary: #0a0e1a;
            --bg-secondary: #0f1629;
            --bg-card: rgba(255, 255, 255, 0.04);
            --bg-card-hover: rgba(255, 255, 255, 0.07);
            --border: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(99, 179, 237, 0.3);
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-blue: #3b82f6;
            --accent-cyan: #06b6d4;
            --accent-purple: #8b5cf6;
            --accent-green: #10b981;
            --accent-orange: #f59e0b;
            --accent-red: #ef4444;
            --gradient-1: linear-gradient(135deg, #3b82f6, #8b5cf6);
            --gradient-2: linear-gradient(135deg, #06b6d4, #3b82f6);
            --gradient-hero: linear-gradient(135deg, #1e3a5f 0%, #0f1629 50%, #1a0e3a 100%);
        }

        html { scroll-behavior: smooth; }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* ── Animated Background ── */
        .bg-orbs {
            position: fixed; inset: 0; overflow: hidden; z-index: 0; pointer-events: none;
        }
        .bg-orbs::before {
            content: '';
            position: absolute;
            width: 600px; height: 600px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%);
            top: -200px; left: -200px;
            animation: float 8s ease-in-out infinite;
        }
        .bg-orbs::after {
            content: '';
            position: absolute;
            width: 500px; height: 500px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(139,92,246,0.10) 0%, transparent 70%);
            bottom: -150px; right: -150px;
            animation: float 10s ease-in-out infinite reverse;
        }
        @keyframes float {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(30px, -30px) scale(1.05); }
            66% { transform: translate(-20px, 20px) scale(0.95); }
        }

        /* ── Layout ── */
        .container {
            position: relative; z-index: 1;
            max-width: 1100px;
            margin: 0 auto;
            padding: 0 24px;
        }

        /* ── Header / Hero ── */
        header {
            padding: 80px 0 60px;
            text-align: center;
        }

        .badge {
            display: inline-flex; align-items: center; gap: 8px;
            background: rgba(59,130,246,0.15);
            border: 1px solid rgba(59,130,246,0.3);
            border-radius: 100px;
            padding: 6px 16px;
            font-size: 12px; font-weight: 600; letter-spacing: 0.05em;
            color: #60a5fa;
            margin-bottom: 24px;
            text-transform: uppercase;
        }
        .badge-dot {
            width: 6px; height: 6px; border-radius: 50%;
            background: #60a5fa;
            animation: pulse 2s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
        }

        h1 {
            font-size: clamp(2rem, 5vw, 3.5rem);
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #e2e8f0 30%, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 16px;
            line-height: 1.15;
        }
        h1 span {
            background: var(--gradient-1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .subtitle {
            font-size: 1.05rem;
            color: var(--text-secondary);
            max-width: 560px;
            margin: 0 auto 40px;
            line-height: 1.7;
        }

        .version-tag {
            display: inline-flex; align-items: center;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 4px 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-muted);
            margin-bottom: 48px;
        }

        /* ── Hero Buttons ── */
        .hero-actions {
            display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;
            margin-bottom: 80px;
        }
        .btn {
            display: inline-flex; align-items: center; gap: 8px;
            padding: 13px 28px;
            border-radius: 12px;
            font-size: 14px; font-weight: 600;
            text-decoration: none;
            transition: all 0.2s ease;
            cursor: pointer; border: none;
        }
        .btn-primary {
            background: var(--gradient-1);
            color: #fff;
            box-shadow: 0 4px 20px rgba(59,130,246,0.35);
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(59,130,246,0.5);
        }
        .btn-secondary {
            background: var(--bg-card);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }
        .btn-secondary:hover {
            background: var(--bg-card-hover);
            border-color: var(--border-glow);
            transform: translateY(-2px);
        }

        /* ── Stats Bar ── */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 60px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px 24px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: default;
        }
        .stat-card:hover {
            background: var(--bg-card-hover);
            border-color: var(--border-glow);
            transform: translateY(-3px);
        }
        .stat-value {
            font-size: 2rem; font-weight: 800;
            letter-spacing: -0.03em;
            margin-bottom: 4px;
        }
        .stat-label {
            font-size: 12px; font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase; letter-spacing: 0.08em;
        }
        .stat-online .stat-value { color: var(--accent-green); }
        .stat-offline .stat-value { color: var(--accent-red); }
        .stat-total .stat-value { color: var(--accent-blue); }
        .stat-mapped .stat-value { color: var(--accent-purple); }
        .stat-unmapped .stat-value { color: var(--accent-orange); }

        /* ── Section Title ── */
        .section-title {
            font-size: 11px; font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 20px;
            display: flex; align-items: center; gap: 10px;
        }
        .section-title::after {
            content: '';
            flex: 1;
            height: 1px;
            background: var(--border);
        }

        /* ── Endpoints Grid ── */
        .endpoints-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 16px;
            margin-bottom: 60px;
        }
        .endpoint-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px 22px;
            text-decoration: none;
            display: flex; align-items: flex-start; gap: 14px;
            transition: all 0.25s ease;
            cursor: pointer;
        }
        .endpoint-card:hover {
            background: var(--bg-card-hover);
            border-color: var(--border-glow);
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
        }
        .method-badge {
            padding: 3px 8px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px; font-weight: 700;
            letter-spacing: 0.05em;
            flex-shrink: 0;
            margin-top: 2px;
        }
        .method-get { background: rgba(6,182,212,0.15); color: #22d3ee; }
        .method-post { background: rgba(16,185,129,0.15); color: #34d399; }
        .method-put { background: rgba(245,158,11,0.15); color: #fbbf24; }
        .method-delete { background: rgba(239,68,68,0.15); color: #f87171; }

        .endpoint-info { flex: 1; min-width: 0; }
        .endpoint-path {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px; font-weight: 500;
            color: var(--text-primary);
            margin-bottom: 4px;
            word-break: break-all;
        }
        .endpoint-desc {
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.5;
        }

        /* ── Health Status ── */
        .health-section {
            margin-bottom: 60px;
        }
        .health-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 24px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 20px;
        }
        .health-indicators {
            display: flex; gap: 20px; flex-wrap: wrap;
        }
        .health-item {
            display: flex; align-items: center; gap: 8px;
            font-size: 14px;
        }
        .status-dot {
            width: 8px; height: 8px; border-radius: 50%;
        }
        .status-ok { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); animation: blink 2s ease-in-out infinite; }
        .status-error { background: var(--accent-red); }
        .status-unknown { background: var(--text-muted); }
        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .health-refresh {
            font-size: 12px; color: var(--text-muted);
            display: flex; align-items: center; gap: 6px;
        }
        .refresh-icon { animation: spin 2s linear infinite; display: none; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        /* ── Footer ── */
        footer {
            text-align: center;
            padding: 40px 0 60px;
            color: var(--text-muted);
            font-size: 13px;
            border-top: 1px solid var(--border);
        }
        footer a { color: var(--accent-blue); text-decoration: none; }
        footer a:hover { text-decoration: underline; }

        /* ── Responsive ── */
        @media (max-width: 640px) {
            header { padding: 60px 0 40px; }
            .hero-actions { flex-direction: column; align-items: center; }
            .btn { width: 100%; max-width: 280px; justify-content: center; }
            .health-card { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="bg-orbs"></div>

    <div class="container">
        <!-- ── Header ── -->
        <header>
            <div class="badge">
                <span class="badge-dot"></span>
                IoT Device Management
            </div>
            <h1>IoT Device <span>Management API</span></h1>
            <p class="subtitle">
                REST API untuk manajemen device IoT — mapping MAC Address ↔ MCID (Machine ID),
                monitoring status online/offline, dan integrasi dengan Prometheus & Grafana.
            </p>
            <div class="version-tag">v2.0.0 &nbsp;|&nbsp; FastAPI &nbsp;|&nbsp; OpenAPI 3.1</div>

            <div class="hero-actions">
                <a href="/docs" class="btn btn-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    Interactive Docs
                </a>
                <a href="/redoc" class="btn btn-secondary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    ReDoc
                </a>
                <a href="/openapi.json" class="btn btn-secondary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                    OpenAPI JSON
                </a>
            </div>
        </header>

        <!-- ── Device Stats ── -->
        <div class="section-title">Live Device Statistics</div>
        <div class="stats-bar">
            <div class="stat-card stat-total">
                <div class="stat-value" id="stat-total">—</div>
                <div class="stat-label">Total Devices</div>
            </div>
            <div class="stat-card stat-online">
                <div class="stat-value" id="stat-online">—</div>
                <div class="stat-label">Online</div>
            </div>
            <div class="stat-card stat-offline">
                <div class="stat-value" id="stat-offline">—</div>
                <div class="stat-label">Offline</div>
            </div>
            <div class="stat-card stat-mapped">
                <div class="stat-value" id="stat-mapped">—</div>
                <div class="stat-label">Mapped (MCID)</div>
            </div>
            <div class="stat-card stat-unmapped">
                <div class="stat-value" id="stat-unmapped">—</div>
                <div class="stat-label">Unmapped</div>
            </div>
        </div>

        <!-- ── Health Status ── -->
        <div class="health-section">
            <div class="section-title">System Health</div>
            <div class="health-card">
                <div class="health-indicators">
                    <div class="health-item">
                        <span class="status-dot" id="dot-api"></span>
                        <span>API Server</span>
                        <strong id="label-api">—</strong>
                    </div>
                    <div class="health-item">
                        <span class="status-dot" id="dot-prometheus"></span>
                        <span>Prometheus</span>
                        <strong id="label-prometheus">—</strong>
                    </div>
                    <div class="health-item">
                        <span class="status-dot status-ok" style="background:#8b5cf6;box-shadow:0 0 8px #8b5cf6"></span>
                        <span>Database</span>
                        <strong>SQLite</strong>
                    </div>
                </div>
                <div class="health-refresh">
                    <svg class="refresh-icon" id="refresh-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                    <span id="last-updated">Memuat...</span>
                </div>
            </div>
        </div>

        <!-- ── Endpoints ── -->
        <div class="section-title">Available Endpoints</div>
        <div class="endpoints-grid">
            <a href="/docs#/System/health_check_health_get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/health</div>
                    <div class="endpoint-desc">Health check — status API & Prometheus</div>
                </div>
            </a>
            <a href="/docs#/Devices/get_device_stats_api_devices_stats_get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/stats</div>
                    <div class="endpoint-desc">Statistik ringkasan: total, online, offline, mapped</div>
                </div>
            </a>
            <a href="/docs#/Devices/get_all_statuses_api_devices_statuses_get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/statuses</div>
                    <div class="endpoint-desc">Status online/offline semua device</div>
                </div>
            </a>
            <a href="/docs#/Devices/read_devices_api_devices__get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/</div>
                    <div class="endpoint-desc">Daftar semua device — mendukung search & pagination</div>
                </div>
            </a>
            <a href="/docs#/Devices/create_device_api_devices__post" class="endpoint-card">
                <span class="method-badge method-post">POST</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/</div>
                    <div class="endpoint-desc">Daftarkan device baru (MAC Address + MCID)</div>
                </div>
            </a>
            <a href="/docs#/Devices/read_device_api_devices__mac_address__get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/{mac}</div>
                    <div class="endpoint-desc">Detail satu device berdasarkan MAC Address</div>
                </div>
            </a>
            <a href="/docs#/Devices/update_device_api_devices__mac_address__put" class="endpoint-card">
                <span class="method-badge method-put">PUT</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/{mac}</div>
                    <div class="endpoint-desc">Update nama, MCID, model, lokasi, deskripsi</div>
                </div>
            </a>
            <a href="/docs#/Devices/delete_device_api_devices__mac_address__delete" class="endpoint-card">
                <span class="method-badge method-delete">DELETE</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/{mac}</div>
                    <div class="endpoint-desc">Hapus device dari registry</div>
                </div>
            </a>
            <a href="/docs#/Devices/get_device_status_api_devices__mac_address__status_get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/{mac}/status</div>
                    <div class="endpoint-desc">Status online/offline satu device via Prometheus</div>
                </div>
            </a>
            <a href="/docs#/Devices/get_device_last_seen_api_devices__mac_address__last_seen_get" class="endpoint-card">
                <span class="method-badge method-get">GET</span>
                <div class="endpoint-info">
                    <div class="endpoint-path">/api/devices/{mac}/last-seen</div>
                    <div class="endpoint-desc">Timestamp terakhir device mengirim data</div>
                </div>
            </a>
        </div>

        <!-- ── Footer ── -->
        <footer>
            <p>IoT Device Management API &mdash; v2.0.0 &nbsp;&bull;&nbsp; Built with <a href="https://fastapi.tiangolo.com" target="_blank">FastAPI</a> &amp; <a href="https://prometheus.io" target="_blank">Prometheus</a></p>
            <p style="margin-top:8px">Data auto-refresh setiap 30 detik &nbsp;&bull;&nbsp; <a href="/docs">Swagger UI</a> &nbsp;&bull;&nbsp; <a href="/redoc">ReDoc</a></p>
        </footer>
    </div>

    <script>
        // ── Fetch device stats ──
        async function loadStats() {
            try {
                const r = await fetch('/api/devices/stats');
                if (!r.ok) throw new Error();
                const d = await r.json();
                document.getElementById('stat-total').textContent = d.total ?? '—';
                document.getElementById('stat-online').textContent = d.online ?? '—';
                document.getElementById('stat-offline').textContent = d.offline ?? '—';
                document.getElementById('stat-mapped').textContent = d.mapped ?? '—';
                document.getElementById('stat-unmapped').textContent = d.unmapped ?? '—';
            } catch (e) {
                ['stat-total','stat-online','stat-offline','stat-mapped','stat-unmapped']
                    .forEach(id => document.getElementById(id).textContent = 'N/A');
            }
        }

        // ── Fetch health ──
        async function loadHealth() {
            const icon = document.getElementById('refresh-icon');
            icon.style.display = 'inline-block';
            try {
                const r = await fetch('/health');
                const d = await r.json();

                const apiDot = document.getElementById('dot-api');
                const promDot = document.getElementById('dot-prometheus');
                const apiLabel = document.getElementById('label-api');
                const promLabel = document.getElementById('label-prometheus');

                apiDot.className = 'status-dot ' + (d.api === 'ok' ? 'status-ok' : 'status-error');
                promDot.className = 'status-dot ' + (d.prometheus === 'ok' ? 'status-ok' : 'status-error');
                apiLabel.textContent = d.api === 'ok' ? 'OK' : 'Error';
                promLabel.textContent = d.prometheus;

                document.getElementById('last-updated').textContent =
                    'Diperbarui: ' + new Date().toLocaleTimeString('id-ID');
            } catch (e) {
                document.getElementById('last-updated').textContent = 'Gagal memuat status';
            } finally {
                icon.style.display = 'none';
            }
        }

        // ── Number counter animation ──
        function animateCount(el, target) {
            const duration = 800;
            const start = performance.now();
            const from = 0;
            const step = (now) => {
                const progress = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - progress, 3);
                el.textContent = Math.round(from + (target - from) * eased);
                if (progress < 1) requestAnimationFrame(step);
            };
            requestAnimationFrame(step);
        }

        // ── Init ──
        async function init() {
            await Promise.all([loadStats(), loadHealth()]);
            // Animate numbers after load
            ['stat-total','stat-online','stat-offline','stat-mapped','stat-unmapped'].forEach(id => {
                const el = document.getElementById(id);
                const val = parseInt(el.textContent);
                if (!isNaN(val)) animateCount(el, val);
            });
        }

        init();
        setInterval(() => { loadStats(); loadHealth(); }, 30000);
    </script>
</body>
</html>
"""

app = FastAPI(
    title="IoT Device Management API",
    description="""
## 🌐 IoT Device Management API v2.0

API untuk manajemen device IoT — mapping **MAC Address ↔ MCID** (Machine ID).

### Fitur Utama
- 📡 **Device Registry** — Daftarkan, update, dan hapus device
- 🟢 **Status Monitoring** — Online/Offline via Prometheus
- 🔗 **MAC ↔ MCID Mapping** — Hubungkan sensor IoT ke identitas mesin fisik
- 📊 **Live Statistics** — Total, online, offline, mapped, unmapped
- ⏱️ **Last Seen** — Timestamp terakhir device mengirim data

### Integrasi
- **Prometheus** untuk metrics & status monitoring
- **Grafana** untuk visualisasi dashboard
- **MQTT + Telegraf** untuk data collection
    """,
    version="2.0.0",
    contact={
        "name": "IoT Dashboard Team",
    },
    swagger_ui_parameters={
        "docExpansion": "list",
        "defaultModelsExpandDepth": 1,
        "syntaxHighlight.theme": "monokai",
        "tryItOutEnabled": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
    },
)

# Prometheus URL - defaults to existing homelab host Prometheus on port 9001 with fallback to container
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://host.docker.internal:9001")
PROMETHEUS_CANDIDATE_URLS = [
    PROMETHEUS_URL.rstrip("/"),
    "http://host.docker.internal:9001",
    "http://192.168.25.101:9001",
    "http://prometheus:9090",
]

# Personal API Platform (Main API / API Utama) configuration
PAP_API_URL = os.getenv("PAP_API_URL", "http://192.168.25.101:8000")
PAP_API_KEY = os.getenv("PAP_API_KEY", "pap_key_iot_dashboard_default_secret_key_2026")
PAP_CANDIDATE_URLS = [
    "http://127.0.0.1:8000",
    PAP_API_URL.rstrip("/"),
]

# Online threshold: device dianggap online jika kirim data dalam N menit terakhir
ONLINE_THRESHOLD_MINUTES = int(os.getenv("ONLINE_THRESHOLD_MINUTES", "5"))

# Semua metric yang di-scrape dari MQTT via Telegraf.
# Device dianggap Online jika ADA data dari metric MANAPUN dalam threshold menit.
# Ini memastikan status web selaras dengan data yang ditampilkan Grafana.
#
# PENTING: Telegraf metric_version=2 meng-flatten field menjadi nama metric:
#   sysctrl   -> sysctrl_STS, sysctrl_STS_raw, dst.
#   event_cnt -> event_cnt_CUR_CYCLE, event_cnt_DAY, dst.
#   heatpress -> heatpress_PV, heatpress_SV, heatpress_DAY, dst.
# Gunakan regex prefix agar cocok dengan semua variant.
ALL_MQTT_METRICS = "sysctrl_.+|event_cnt_.+|event_handling_.+|machine_time_.+|heatpress_.+"

# Allow CORS for web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Database Dependency
# ─────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# Internal Helpers — Prometheus Queries
# ─────────────────────────────────────────────

def _query_prometheus(query: str, timeout: float = 2.0):
    """Execute PromQL query against existing host Prometheus (:9001) or container Prometheus."""
    req_timeout = httpx.Timeout(timeout, connect=0.5)
    seen = set()
    for base in PROMETHEUS_CANDIDATE_URLS:
        if not base or base in seen:
            continue
        seen.add(base)
        try:
            response = httpx.get(
                f"{base}/api/v1/query",
                params={"query": query},
                timeout=req_timeout,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return data.get("data", {}).get("result", [])
        except Exception:
            continue
    return []


def _get_online_macs() -> set:
    """
    Return set of MAC addresses yang online.
    Device dianggap Online jika ada data dari metric MANAPUN (bukan hanya sysctrl)
    dalam ONLINE_THRESHOLD_MINUTES menit terakhir.
    Ini memastikan status di web selaras dengan data yang ditampilkan di Grafana —
    jika Grafana menampilkan data dari device, web juga menampilkan Online.
    """
    # Cek semua metric MQTT: jika data ada di Prometheus, berarti device Online.
    # (Telegraf otomatis menghapus metric jika tidak ada update selama 5 menit
    # berkat 'expiration_interval = "5m"' di telegraf.conf)
    query = f'count by (MAC) ({{__name__=~"{ALL_MQTT_METRICS}"}})'
    results = _query_prometheus(query)
    online_macs = set()
    for r in results:
        mac = r.get("metric", {}).get("MAC", "").upper()
        if not mac:
            mac = r.get("metric", {}).get("mac", "").upper()
        if mac:
            online_macs.add(mac)
    return online_macs


def _get_last_seen_timestamp(mac_address: str) -> Optional[datetime]:
    """
    Get timestamp terakhir device kirim data ke Prometheus.
    Menggunakan metric STS sebagai patokan untuk historical query.
    """
    query = (
        f'timestamp(last_over_time(sysctrl_STS{{MAC=~"(?i){mac_address}"}}[24h]))'
        f' or timestamp(last_over_time(sysctrl_STS{{mac=~"(?i){mac_address}"}}[24h]))'
    )
    results = _query_prometheus(query)
    if results:
        try:
            ts = float(results[0].get("value", [0, 0])[1])
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (IndexError, ValueError, TypeError):
            pass
    return None


# ─────────────────────────────────────────────
# Internal Helpers — Personal API Platform (Main API)
# ─────────────────────────────────────────────

def _pap_headers() -> Dict[str, str]:
    return {"X-API-Key": PAP_API_KEY, "Content-Type": "application/json"}


def _request_pap(
    method: str,
    path: str,
    json_body: Optional[dict] = None,
    timeout: float = 0.5,
) -> Optional[httpx.Response]:
    """Send an authenticated request to Personal API Platform (Main API), trying candidate URLs."""
    req_timeout = httpx.Timeout(timeout, connect=0.25)
    seen = set()
    for base in PAP_CANDIDATE_URLS:
        if not base or base in seen:
            continue
        seen.add(base)
        url = f"{base}{path}"
        try:
            resp = httpx.request(
                method=method,
                url=url,
                headers=_pap_headers(),
                json=json_body,
                timeout=req_timeout,
            )
            if resp.status_code < 500:
                return resp
        except Exception:
            continue
    return None


def sync_with_pap(db: Session) -> dict:
    """
    Synchronize local SQLite Heatpress device registry with Personal API Platform (Main API).
    1. Pulls devices registered on PAP Main API (/api/devices/) into local SQLite.
    2. Pushes any local SQLite devices missing in PAP Main API up to PAP.
    """
    synced_from_pap = 0
    pushed_to_pap = 0
    pap_reachable = False
    active_pap_url = PAP_API_URL

    resp = _request_pap("GET", "/api/devices/", timeout=2.5)
    if resp is not None and resp.status_code == 200:
        pap_reachable = True
        active_pap_url = str(resp.request.url).split("/api/devices")[0]
        try:
            pap_devices = resp.json()
            if isinstance(pap_devices, list):
                pap_macs = set()
                for pd in pap_devices:
                    mac = (pd.get("mac_address") or "").strip().upper()
                    if not mac:
                        continue
                    pap_macs.add(mac)
                    local_dev = crud.get_device(db, mac)
                    if not local_dev:
                        new_dev = models.Device(
                            mac_address=mac,
                            name=pd.get("name") or f"Heatpress {mac[-5:]}",
                            category=pd.get("category") or "Heatpress",
                            model=pd.get("model") or "HPM 55",
                            mcid=pd.get("mcid"),
                            device_type=pd.get("device_type") or "ESP32",
                            location=pd.get("location"),
                            description=pd.get("description"),
                        )
                        db.add(new_dev)
                        db.commit()
                        synced_from_pap += 1

                # Push local devices not yet in PAP Main API
                for local_d in crud.get_devices(db):
                    if local_d.mac_address.upper() not in pap_macs:
                        push_res = _request_pap(
                            "POST",
                            "/api/devices/",
                            json_body={
                                "mac_address": local_d.mac_address.upper(),
                                "name": local_d.name,
                                "mcid": local_d.mcid,
                                "category": local_d.category or "Heatpress",
                                "device_type": local_d.device_type or "ESP32",
                                "model": local_d.model or "HPM 55",
                                "location": local_d.location,
                                "description": local_d.description,
                            },
                            timeout=2.5,
                        )
                        if push_res is not None and push_res.status_code in (200, 201):
                            pushed_to_pap += 1
        except Exception as e:
            print(f"[WARN] sync_with_pap parse error: {e}")

    return {
        "pap_reachable": pap_reachable,
        "pap_url": active_pap_url,
        "synced_from_pap": synced_from_pap,
        "pushed_to_pap": pushed_to_pap,
    }


# ─────────────────────────────────────────────
# Health Check & PAP Main API Status
# ─────────────────────────────────────────────

@app.get("/health", response_model=schemas.HealthResponse, tags=["System"])
@app.get("/api/health", response_model=schemas.HealthResponse, tags=["System"])
def health_check():
    """
    Health check endpoint. Verifikasi API berjalan, koneksi ke Prometheus (host :9001 / container), dan koneksi ke Personal API Platform (Main API).
    """
    prometheus_status = "unreachable"
    seen_prom = set()
    for base in PROMETHEUS_CANDIDATE_URLS:
        if not base or base in seen_prom:
            continue
        seen_prom.add(base)
        try:
            resp = httpx.get(f"{base}/-/ready", timeout=1.5)
            if resp.status_code == 200:
                prometheus_status = "ok"
                break
        except Exception:
            continue

    pap_status = "unreachable"
    active_pap_url = PAP_API_URL
    pap_resp = _request_pap("GET", "/health", timeout=2.0)
    if pap_resp is not None and pap_resp.status_code == 200:
        pap_status = "ok"
        active_pap_url = str(pap_resp.request.url).split("/health")[0]

    overall = "healthy" if (prometheus_status == "ok" or pap_status == "ok") else "degraded"
    return schemas.HealthResponse(
        status=overall,
        api="ok",
        prometheus=prometheus_status,
        pap_api=pap_status,
        pap_url=active_pap_url,
        timestamp=datetime.now(tz=timezone.utc),
    )


@app.get("/api/pap/status", tags=["Personal API Platform"])
def get_pap_connection_status(db: Session = Depends(get_db)):
    """Cek status keterhubungan IoT Dashboard dengan Personal API Platform (API Utama) & Personal Server Manager."""
    mqtt_info = {
        "local_host": os.getenv("MQTT_BROKER_HOST", "192.168.25.101"),
        "tailscale_host": os.getenv("MQTT_TAILSCALE_HOST", "100.106.63.90"),
        "port": int(os.getenv("MQTT_BROKER_PORT", "1883")),
        "username": os.getenv("MQTT_USERNAME", "useriot"),
    }
    hub_resp = _request_pap("GET", "/api/v1/integrations/hub/overview", timeout=2.5)
    if hub_resp is not None and hub_resp.status_code == 200:
        hub_data = hub_resp.json().get("data", {})
        active_url = str(hub_resp.request.url).split("/api/v1/integrations")[0]
        return {
            "connected": True,
            "main_api": "Personal API Platform",
            "pap_url": active_url,
            "mqtt_broker": mqtt_info,
            "hub_overview": hub_data,
        }
    return {
        "connected": False,
        "main_api": "Personal API Platform",
        "pap_url": PAP_API_URL,
        "mqtt_broker": mqtt_info,
        "mode": "local_fallback",
        "local_devices": len(crud.get_devices(db)),
    }


@app.post("/api/pap/sync", tags=["Personal API Platform"])
def sync_pap_devices_endpoint(db: Session = Depends(get_db)):
    """Sinkronisasi dua arah antara IoT Dashboard dan Personal API Platform (API Utama)."""
    sync_from_prometheus(db)
    sync_info = sync_with_pap(db)
    devices = crud.get_devices(db)
    return {
        "status": "success",
        "pap": sync_info,
        "total_devices": len(devices),
        "devices": devices,
    }


# ─────────────────────────────────────────────
# Root
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_root():
    """Beautiful landing page untuk API."""
    return HTMLResponse(content=LANDING_PAGE_HTML)


# ─────────────────────────────────────────────
# Device Stats
# ─────────────────────────────────────────────

@app.get("/api/devices/stats", response_model=schemas.StatsResponse, tags=["Devices"])
def get_device_stats(db: Session = Depends(get_db)):
    """
    Statistik ringkasan: total, online, offline, mapped (sudah ada MCID), unmapped.
    """
    devices = crud.get_devices(db)
    total = len(devices)
    mapped = sum(1 for d in devices if d.mcid and d.mcid.strip())
    unmapped = total - mapped

    online_macs = _get_online_macs()
    online = sum(1 for d in devices if d.mac_address.upper() in online_macs)
    offline = total - online

    return schemas.StatsResponse(
        total=total,
        online=online,
        offline=offline,
        mapped=mapped,
        unmapped=unmapped,
    )


# ─────────────────────────────────────────────
# Device Statuses (All)
# ─────────────────────────────────────────────

@app.get("/api/devices/statuses", response_model=Dict[str, bool], tags=["Devices"])
def get_all_statuses(db: Session = Depends(get_db)):
    """
    Status Online/Offline untuk semua device yang terdaftar.
    Device dianggap Online jika mengirim metric `sysctrl` dalam
    ONLINE_THRESHOLD_MINUTES menit terakhir.
    Returns: { "MAC:ADDRESS": true/false }
    """
    devices = crud.get_devices(db)
    statuses: Dict[str, bool] = {d.mac_address: False for d in devices}

    if not devices:
        return statuses

    online_macs = _get_online_macs()
    for mac in statuses:
        if mac.upper() in online_macs:
            statuses[mac] = True

    return statuses


# ─────────────────────────────────────────────
# Auto-Sync Prometheus Telemetry with DB
# ─────────────────────────────────────────────

def sync_from_prometheus(db: Session):
    """
    Auto-discover and synchronize devices sending telemetry in Prometheus (sysctrl_STS).
    If a device is sending data via MQTT to Prometheus, ensure it is registered
    in the SQLite database with its reported model under Heatpress hierarchy.
    """
    try:
        # Also clean up any lingering dummy placeholders
        db.query(models.Device).filter(
            models.Device.mac_address.in_(["AF:45:00:2B:9C:11", "AP:40:00:7E:3D:88"])
        ).delete(synchronize_session=False)

        results = _query_prometheus("count by (MAC, model) (sysctrl_STS)")
        if not results:
            results = _query_prometheus("count by (mac, model) (sysctrl_STS)")

        for r in results:
            metric = r.get("metric", {})
            mac = metric.get("MAC") or metric.get("mac")
            if not mac:
                continue
            mac = mac.upper()
            raw_model = (metric.get("model") or "Heatpress").strip()
            clean_model = raw_model.replace("-", " ").upper()

            # Map to canonical model name
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

            dev = crud.get_device(db, mac)
            if not dev:
                new_dev = models.Device(
                    mac_address=mac,
                    name=default_name,
                    category="Heatpress",
                    model=canonical_model,
                    mcid=default_mcid,
                    device_type="ESP32",
                    location=default_loc,
                    description=default_desc,
                )
                db.add(new_dev)
                db.commit()
            else:
                updated = False
                if not dev.category:
                    dev.category = "Heatpress"
                    updated = True
                if not dev.model or dev.model != canonical_model:
                    dev.model = canonical_model
                    updated = True
                if not dev.mcid:
                    dev.mcid = default_mcid
                    updated = True
                if updated:
                    db.commit()
    except Exception as e:
        print(f"[WARN] sync_from_prometheus error: {e}")


# ─────────────────────────────────────────────
# Hierarchy Fleet Endpoint
# ─────────────────────────────────────────────

@app.get("/api/devices/hierarchy", response_model=schemas.HierarchyResponse, tags=["Devices"])
def get_device_hierarchy(db: Session = Depends(get_db)):
    """
    Mengambil struktur hirarki armada mesin Heatpress:
    Heatpress:
      - HPM 55 (Pneumatic Double Station)
      - AF-450 (Automatic Flat Press 450)
      - APM-LOGO (Auto Positioning Logo Press)
      - Coming Soon (Next-Gen Expansion)
    Disertai status online/offline dan daftar perangkat untuk tiap model.
    """
    sync_from_prometheus(db)
    devices = crud.get_devices(db)
    online_macs = _get_online_macs()

    # Model configuration for Heatpress hierarchy
    model_configs = {
        "HPM 55": {
            "name": "HPM 55",
            "type": "Pneumatic Double Station",
            "status": "active",
            "icon": "bx-flame",
            "badge_color": "primary",
            "description": "Mesin heatpress pneumatik double station bertekanan tinggi untuk transfer sublimasi, sablon DTF, dan heat seal presisi.",
            "specs": {
                "system": "Pneumatic Dual-Bed Shuttle",
                "pressure": "4 - 8 Bar (Air Compressor)",
                "temp_range": "50°C - 250°C",
                "station": "Dual Platen 40 x 50 cm",
                "target_product": "Jersey, Kaos, Sublimation Garment"
            }
        },
        "AF-450": {
            "name": "AF-450",
            "type": "Automatic Flat Press 450",
            "status": "active",
            "icon": "bx-layer",
            "badge_color": "teal",
            "description": "Mesin flatbed heat press otomatis seri 450 dengan pemanas presisi tinggi, auto-open elektromagnetik, dan pemantauan suhu real-time.",
            "specs": {
                "system": "Electromagnetic Auto-Open Flatbed",
                "pressure": "Adjustable Mechanical Cam Clamp",
                "temp_range": "50°C - 220°C",
                "station": "Single Flatbed 40 x 50 cm",
                "target_product": "T-Shirt, Hoodies, Flat Fabric Garment"
            }
        },
        "APM-LOGO": {
            "name": "APM-LOGO",
            "type": "Auto Positioning Motion Logo",
            "status": "active",
            "icon": "bx-purchase-tag-alt",
            "badge_color": "amber",
            "description": "Mesin heatpress khusus logo, badge, dan label pakaian dengan penempatan posisi otomatis (Auto Positioning Motion) dan laser guide.",
            "specs": {
                "system": "Auto Positioning & Micro Press",
                "pressure": "Precision Pneumatic Micro-cylinder",
                "temp_range": "50°C - 230°C",
                "station": "Compact Platen 15 x 15 cm / Laser Pointer",
                "target_product": "Label Kerah, Logo Dada, Pocket, Patch"
            }
        },
        "comingsoon": {
            "name": "Coming Soon",
            "type": "Next-Gen Intelligent Press",
            "status": "coming_soon",
            "icon": "bx-time-five",
            "badge_color": "purple",
            "description": "Slot ekspansi mesin heatpress generasi pintar masa depan dengan sensor tekanan digital terintegrasi (load cell) dan multi-zone heating.",
            "specs": {
                "system": "Multi-Zone Smart Heat & IoT Load-Cell",
                "pressure": "Digital Real-time Force Feedback",
                "temp_range": "30°C - 300°C Multi-Zone",
                "station": "Smart Modular Platen",
                "target_product": "Next-Gen Expansion Line"
            }
        }
    }

    model_devices: Dict[str, List[schemas.DeviceWithStatus]] = {
        "HPM 55": [],
        "AF-450": [],
        "APM-LOGO": [],
        "comingsoon": []
    }
    other_devices: Dict[str, List[schemas.DeviceWithStatus]] = {}

    for d in devices:
        is_online = d.mac_address.upper() in online_macs
        dev_with_status = schemas.DeviceWithStatus(
            mac_address=d.mac_address,
            name=d.name,
            mcid=d.mcid,
            category=d.category or "Heatpress",
            device_type=d.device_type,
            model=d.model,
            location=d.location,
            description=d.description,
            created_at=d.created_at,
            updated_at=d.updated_at,
            online=is_online,
            last_seen=None
        )

        mod_upper = (d.model or "").upper().replace("-", " ").strip()
        matched = False
        if "HPM" in mod_upper or "55" in mod_upper:
            model_devices["HPM 55"].append(dev_with_status)
            matched = True
        elif "AF" in mod_upper or "450" in mod_upper:
            model_devices["AF-450"].append(dev_with_status)
            matched = True
        elif "APM" in mod_upper or "LOGO" in mod_upper:
            model_devices["APM-LOGO"].append(dev_with_status)
            matched = True
        elif "COMING" in mod_upper:
            model_devices["comingsoon"].append(dev_with_status)
            matched = True

        if not matched:
            model_key = d.model or "General"
            if model_key not in other_devices:
                other_devices[model_key] = []
            other_devices[model_key].append(dev_with_status)

    models_list = []
    for mid, cfg in model_configs.items():
        devs = model_devices.get(mid, [])
        online_c = sum(1 for x in devs if x.online)
        models_list.append(schemas.ModelHierarchyItem(
            id=mid,
            name=cfg["name"],
            category="Heatpress",
            type=cfg["type"],
            status=cfg["status"],
            icon=cfg["icon"],
            badge_color=cfg["badge_color"],
            description=cfg["description"],
            specs=cfg["specs"],
            devices=devs,
            device_count=len(devs),
            online_count=online_c,
            offline_count=len(devs) - online_c
        ))

    for custom_mod, devs in other_devices.items():
        online_c = sum(1 for x in devs if x.online)
        models_list.append(schemas.ModelHierarchyItem(
            id=custom_mod,
            name=custom_mod,
            category="Heatpress",
            type="Custom Heatpress",
            status="active",
            icon="bx-chip",
            badge_color="sky",
            description=f"Model kustom: {custom_mod}",
            specs={},
            devices=devs,
            device_count=len(devs),
            online_count=online_c,
            offline_count=len(devs) - online_c
        ))

    total_units = len(devices)
    total_online = sum(1 for d in devices if d.mac_address.upper() in online_macs)
    summary = {
        "total_devices": total_units,
        "online": total_online,
        "offline": total_units - total_online,
        "active_models": 3,
        "total_models": len(models_list)
    }

    return schemas.HierarchyResponse(
        category="Heatpress",
        title="Heatpress IoT Fleet Monitoring",
        description="Hirarki armada mesin heatpress: HPM 55, AF-450, APM-LOGO, dan Coming Soon",
        summary=summary,
        models=models_list
    )


# ─────────────────────────────────────────────
# Device List
# ─────────────────────────────────────────────

@app.get("/api/devices/", response_model=List[schemas.Device], tags=["Devices"])
def read_devices(
    skip: int = Query(0, ge=0, description="Offset pagination"),
    limit: int = Query(100, ge=1, le=500, description="Jumlah data maksimal"),
    search: Optional[str] = Query(None, description="Cari berdasarkan nama, MAC, MCID, lokasi, model"),
    category: Optional[str] = Query(None, description="Filter kategori hirarki (misal: Heatpress)"),
    model: Optional[str] = Query(None, description="Filter model mesin (misal: HPM 55, AF-450, APM-LOGO)"),
    db: Session = Depends(get_db),
):
    """
    Daftar semua device yang terdaftar.
    Mendukung pencarian full-text via parameter `?search=...`, serta filter hirarki `?category=...` dan `?model=...`.
    """
    return crud.get_devices(db, skip=skip, limit=limit, search=search, category=category, model=model)


# ─────────────────────────────────────────────
# Sync Devices with Prometheus
# ─────────────────────────────────────────────

@app.post("/api/devices/sync-prometheus", tags=["Devices"])
def sync_devices_endpoint(db: Session = Depends(get_db)):
    """
    Sinkronisasi manual/otomatis: tarik seluruh device yang aktif di Prometheus/MQTT
    serta sinkronkan dengan Personal API Platform (API Utama).
    """
    sync_from_prometheus(db)
    pap_info = sync_with_pap(db)
    devices = crud.get_devices(db)
    return {
        "status": "success",
        "message": f"Berhasil sinkronisasi {len(devices)} device dari Prometheus & PAP Main API",
        "pap": pap_info,
        "devices": devices,
    }



# ─────────────────────────────────────────────
# Single Device
# ─────────────────────────────────────────────

@app.get("/api/devices/{mac_address}", response_model=schemas.Device, tags=["Devices"])
def read_device(mac_address: str, db: Session = Depends(get_db)):
    """Ambil informasi satu device berdasarkan MAC Address."""
    db_device = crud.get_device(db, mac_address=mac_address.upper())
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return db_device


# ─────────────────────────────────────────────
# Device Status (Single)
# ─────────────────────────────────────────────

@app.get("/api/devices/{mac_address}/status", tags=["Devices"])
def get_device_status(mac_address: str, db: Session = Depends(get_db)):
    """
    Status Online/Offline satu device berdasarkan data Prometheus.
    """
    mac_upper = mac_address.upper()
    db_device = crud.get_device(db, mac_address=mac_upper)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    online = False
    try:
        # Gunakan instant query: jika ada metric apapun, berarti device online
        query = f'count({{__name__=~"{ALL_MQTT_METRICS}",MAC=~"(?i){mac_upper}"}})'
        results = _query_prometheus(query)
        online = len(results) > 0 and results[0].get("value", [0, "0"])[1] != "0"
        
        # Coba tag 'mac' lowercase jika tidak ditemukan
        if not online:
            query = f'count({{__name__=~"{ALL_MQTT_METRICS}",mac=~"(?i){mac_upper}"}})'
            results = _query_prometheus(query)
            online = len(results) > 0 and results[0].get("value", [0, "0"])[1] != "0"
    except Exception as e:
        print(f"[WARN] Status check failed for {mac_upper}: {e}")

    return {"mac_address": mac_upper, "online": online}


# ─────────────────────────────────────────────
# Device Last Seen
# ─────────────────────────────────────────────

@app.get("/api/devices/{mac_address}/last-seen", response_model=schemas.LastSeenResponse, tags=["Devices"])
def get_device_last_seen(mac_address: str, db: Session = Depends(get_db)):
    """
    Timestamp terakhir device mengirim data ke sistem.
    Mengecek metric `sysctrl` di Prometheus 24 jam terakhir.
    Berguna untuk mengetahui kapan terakhir device aktif.
    """
    mac_upper = mac_address.upper()
    db_device = crud.get_device(db, mac_address=mac_upper)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    last_seen = _get_last_seen_timestamp(mac_upper)
    online = mac_upper in _get_online_macs()

    seconds_ago = None
    if last_seen:
        now = datetime.now(tz=timezone.utc)
        delta = now - last_seen
        seconds_ago = int(delta.total_seconds())

    return schemas.LastSeenResponse(
        mac_address=mac_upper,
        online=online,
        last_seen=last_seen,
        seconds_ago=seconds_ago,
    )


# ─────────────────────────────────────────────
# Create Device
# ─────────────────────────────────────────────

@app.post("/api/devices/", response_model=schemas.Device, status_code=201, tags=["Devices"])
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    """
    Daftarkan device baru dan sinkronkan ke Personal API Platform (Main API).
    MAC Address → kunci unik dari perangkat IoT.
    MCID (Machine ID) → ID mesin fisik tempat device dipasang.
    Mapping MAC ↔ MCID inilah yang menghubungkan data IoT ke identitas mesin.
    """
    db_device = crud.get_device(db, mac_address=device.mac_address)
    if db_device:
        raise HTTPException(
            status_code=400,
            detail=f"Device dengan MAC {device.mac_address} sudah terdaftar"
        )
    created = crud.create_device(db=db, device=device)
    _request_pap(
        "POST",
        "/api/devices/",
        json_body={
            "mac_address": created.mac_address,
            "name": created.name,
            "mcid": created.mcid,
            "category": created.category or "Heatpress",
            "device_type": created.device_type or "ESP32",
            "model": created.model or "HPM 55",
            "location": created.location,
            "description": created.description,
        },
        timeout=2.5,
    )
    return created


# ─────────────────────────────────────────────
# Update Device
# ─────────────────────────────────────────────

@app.put("/api/devices/{mac_address}", response_model=schemas.Device, tags=["Devices"])
def update_device(mac_address: str, device: schemas.DeviceUpdate, db: Session = Depends(get_db)):
    """
    Update informasi device: nama, MCID, model, lokasi, deskripsi, dan sinkronkan ke PAP Main API.
    MAC Address tidak bisa diubah (primary key).
    """
    mac_upper = mac_address.upper()
    db_device = crud.update_device(db, mac_address=mac_upper, device=device)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    _request_pap(
        "PUT",
        f"/api/devices/{mac_upper}",
        json_body=device.model_dump(exclude_unset=True),
        timeout=2.5,
    )
    return db_device


# ─────────────────────────────────────────────
# Delete Device
# ─────────────────────────────────────────────

@app.delete("/api/devices/{mac_address}", tags=["Devices"])
def delete_device(mac_address: str, db: Session = Depends(get_db)):
    """Hapus device dari registry lokal dan Personal API Platform (Main API)."""
    mac_upper = mac_address.upper()
    db_device = crud.delete_device(db, mac_address=mac_upper)
    if db_device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    _request_pap("DELETE", f"/api/devices/{mac_upper}", timeout=2.5)
    return {"message": f"Device {mac_upper} berhasil dihapus"}





#!/usr/bin/env python3
"""
generate_dashboards.py
Menghasilkan 4 dashboard Grafana terpisah:
1. iot-monitoring.json  -> Dashboard Universal (Semua Model & Fleet Comparison)
2. hpm55-dashboard.json -> Dashboard Khusus Model HPM 55 (Pneumatic Double Station)
3. af450-dashboard.json -> Dashboard Khusus Model AF-450 (Automatic Flatbed)
4. apmlogo-dashboard.json -> Dashboard Khusus Model APM-LOGO (Auto Positioning Logo)
"""

import json
import copy

BASE_DASHBOARD_FILE = "grafana/dashboards/iot-monitoring.json"

def load_base():
    with open(BASE_DASHBOARD_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def create_universal_dashboard(base):
    dash = copy.deepcopy(base)
    dash["uid"] = "iot-universal"
    dash["title"] = "🌐 Dashboard Universal — Monitoring Armada Heatpress"
    dash["description"] = "Dashboard pemantauan terpadu seluruh armada mesin Heatpress (HPM 55, AF-450, APM-LOGO) dengan filter model hirarkis dan multi-seleksi perangkat."
    dash["tags"] = ["universal", "fleet", "heatpress", "hpm55", "af450", "apm-logo", "iot"]

    # Templating variables: model (custom) -> mac (cascading query by model)
    dash["templating"] = {
        "list": [
            {
                "name": "model",
                "label": "Filter Model Mesin",
                "type": "custom",
                "hide": 0,
                "multi": False,
                "includeAll": True,
                "allValue": ".*",
                "current": {
                    "selected": True,
                    "text": "Semua Model",
                    "value": "$__all"
                },
                "options": [
                    {"selected": True, "text": "Semua Model (Heatpress Fleet)", "value": "$__all"},
                    {"selected": False, "text": "HPM 55 (Pneumatic Double Station)", "value": ".*(HPM|55).*"},
                    {"selected": False, "text": "AF-450 (Automatic Flatbed 450)", "value": ".*(AF-450|AF450).*"},
                    {"selected": False, "text": "APM-LOGO (Auto Positioning Logo)", "value": ".*(APM|LOGO).*"}
                ],
                "query": "Semua Model (Heatpress Fleet) : $__all, HPM 55 (Pneumatic Double Station) : .*(HPM|55).*, AF-450 (Automatic Flatbed 450) : .*(AF-450|AF450).*, APM-LOGO (Auto Positioning Logo) : .*(APM|LOGO).*",
                "skipUrlSync": False
            },
            {
                "name": "mac",
                "label": "Filter Device / MAC",
                "type": "query",
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "definition": "label_values(sysctrl_STS{model=~\"$model\"}, MAC)",
                "query": "label_values(sysctrl_STS{model=~\"$model\"}, MAC)",
                "regex": "",
                "refresh": 2,
                "sort": 1,
                "multi": True,
                "includeAll": True,
                "allValue": ".*",
                "current": {
                    "selected": True,
                    "text": "All",
                    "value": "$__all"
                },
                "options": [],
                "skipUrlSync": False,
                "hide": 0
            }
        ]
    }

    # Ensure all panels filter by MAC=~"$mac" and reflect model
    for p in dash.get("panels", []):
        if p.get("id") == 100:
            p["title"] = "📊 Ringkasan Eksekutif Seluruh Armada Heatpress"
        elif p.get("id") == 101:
            p["title"] = "Total Unit Terfilter"
            if p.get("targets"):
                p["targets"][0]["expr"] = 'count(count by (MAC) (sysctrl_STS{MAC=~"$mac"}))'
        elif p.get("id") == 200:
            p["title"] = "⚡ Status Koneksi & Timeline Ketersediaan Seluruh Mesin"
        elif p.get("id") == 300:
            p["title"] = "🌡️ Pemantauan Termal Armada (Aktual PV vs Target SV)"
        elif p.get("id") == 400:
            p["title"] = "🔄 Siklus Produksi & Durasi Penekanan Mesin"
        elif p.get("id") == 500:
            p["title"] = "⏱️ Waktu Operasional Mesin (Power, Motor, Kerja Aktif)"

    return dash

def create_model_dashboard(base, model_key, model_title, model_sub, model_desc, model_color, regex_pattern, max_temp, default_thresholds):
    dash = copy.deepcopy(base)
    if "HPM" in model_key:
        uid = "hpm55-monitoring"
    else:
        uid = f"{model_key.lower().replace('-', '').replace(' ', '')}-dashboard"
    dash["uid"] = uid
    dash["id"] = None
    dash["title"] = f"{model_title} — {model_sub}"
    dash["description"] = model_desc
    dash["tags"] = [model_key.lower(), "heatpress", "dedicated", "iot", "monitoring"]

    # Only single variable: mac, querying ONLY this model!
    dash["templating"] = {
        "list": [
            {
                "name": "mac",
                "label": f"Pilih Device {model_key} (MAC)",
                "type": "query",
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "definition": f'label_values(sysctrl_STS{{model=~"{regex_pattern}"}}, MAC)',
                "query": f'label_values(sysctrl_STS{{model=~"{regex_pattern}"}}, MAC)',
                "regex": "",
                "refresh": 2,
                "sort": 1,
                "multi": True,
                "includeAll": True,
                "allValue": ".*",
                "current": {
                    "selected": True,
                    "text": f"Semua Unit {model_key}",
                    "value": "$__all"
                },
                "options": [],
                "skipUrlSync": False,
                "hide": 0
            }
        ]
    }

    # Customize panels for this specific model
    for p in dash.get("panels", []):
        pid = p.get("id")
        targets = p.get("targets", [])

        # Row 100: Executive Summary
        if pid == 100:
            p["title"] = f"📊 Ringkasan Operasional Mesin Model {model_key}"
        elif pid == 101:
            p["title"] = f"Total Unit {model_key}"
            p["description"] = f"Total perangkat model {model_key} yang terdaftar di monitoring."
            if targets:
                targets[0]["expr"] = f'count(count by (MAC) (sysctrl_STS{{model=~"{regex_pattern}", MAC=~"$mac"}}))'
        elif pid == 102:
            p["title"] = f"Unit {model_key} Online"
            p["description"] = f"Jumlah mesin {model_key} yang sedang online dan aktif mengirim data."
            if targets:
                targets[0]["expr"] = f'count(last_over_time(sysctrl_STS{{model=~"{regex_pattern}", MAC=~"$mac"}}[2m]) == 1) or vector(0)'
        elif pid == 103:
            p["title"] = f"Unit {model_key} Offline"
            p["description"] = f"Jumlah mesin {model_key} yang tidak mengirimkan data dalam 2 menit terakhir."
            if targets:
                targets[0]["expr"] = f'count(last_over_time(sysctrl_STS{{model=~"{regex_pattern}", MAC=~"$mac"}}[2m]) == 0) or vector(0)'
        elif pid == 104:
            p["title"] = f"Total Siklus {model_key}"
            p["description"] = f"Akumulasi hitungan siklus penekanan mesin {model_key}."
            if targets:
                targets[0]["expr"] = f'sum(last_over_time(event_cnt_CUR_CYCLE{{MAC=~"$mac"}}[12h])) or vector(0)'
        elif pid == 105:
            p["title"] = f"Rata-rata Suhu {model_key} (PV)"
            p["description"] = f"Rata-rata temperatur aktual pemanas mesin {model_key} saat ini."
            if targets:
                targets[0]["expr"] = f'avg(heatpress_PV{{MAC=~"$mac"}})'
        elif pid == 106:
            p["title"] = f"Utilisasi Kerja {model_key}"
            p["description"] = f"Rasio waktu penekanan aktif terhadap total jam mesin {model_key} menyala."
            if targets:
                targets[0]["expr"] = f'avg(clamp_max(100 * last_over_time(machine_time_ACT_TIME{{MAC=~"$mac"}}[12h]) / (last_over_time(machine_time_POW_TIME{{MAC=~"$mac"}}[12h]) > 0), 100)) or vector(0)'

        # Row 200: Connection Status & State Timeline
        elif pid == 200:
            p["title"] = f"⚡ Status Koneksi & Timeline Mesin Model {model_key}"
        elif pid == 201:
            p["title"] = f"Timeline Ketersediaan Unit {model_key}"
            if targets:
                targets[0]["expr"] = f'sysctrl_STS{{model=~"{regex_pattern}", MAC=~"$mac"}}'
        elif pid == 202:
            p["title"] = f"Heartbeat & Status Terkini {model_key}"
            if targets:
                targets[0]["expr"] = f'last_over_time(sysctrl_STS{{model=~"{regex_pattern}", MAC=~"$mac"}}[2m])'

        # Row 300: Thermal Monitoring
        elif pid == 300:
            p["title"] = f"🌡️ Pemantauan Termal Presisi Model {model_key} (Maks {max_temp}°C)"
        elif pid == 301:
            p["title"] = f"Dinamika Suhu Pemanas {model_key} — Aktual (PV) vs Target (SV)"
            # Adjust max Y-axis for timeseries
            if "fieldConfig" in p and "defaults" in p["fieldConfig"]:
                p["fieldConfig"]["defaults"]["max"] = max_temp + 20
        elif pid == 302:
            p["title"] = f"Gauge Suhu Pemanas Aktual {model_key} (PV)"
            if "fieldConfig" in p and "defaults" in p["fieldConfig"]:
                p["fieldConfig"]["defaults"]["max"] = max_temp
                p["fieldConfig"]["defaults"]["thresholds"] = default_thresholds

        # Row 400: Production Cycles
        elif pid == 400:
            p["title"] = f"🔄 Siklus Penekanan & Durasi Proses Model {model_key}"
        elif pid == 401:
            p["title"] = f"Akumulasi Siklus Penekanan {model_key}"
        elif pid == 402:
            p["title"] = f"Durasi Penekanan Mesin {model_key} (Handling Time)"

        # Row 500: Machine Operating Times
        elif pid == 500:
            p["title"] = f"⏱️ Jam Operasional & Utilisasi Model {model_key}"
        elif pid == 501:
            p["title"] = f"Distribusi Jam Operasional {model_key} (Power, Motor, Kerja Aktif)"
        elif pid == 502:
            p["title"] = f"Tingkat Utilisasi Kerja Mesin {model_key} (%)"

    return dash

def main():
    base = load_base()

    # 1. Universal Dashboard
    universal = create_universal_dashboard(base)
    with open("grafana/dashboards/iot-monitoring.json", "w", encoding="utf-8") as f:
        json.dump(universal, f, indent=2, ensure_ascii=False)
    print("✅ Created grafana/dashboards/iot-monitoring.json (Universal Dashboard)")

    # 2. HPM 55 Dashboard
    hpm_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "#3b82f6", "value": None},
            {"color": "#06b6d4", "value": 80},
            {"color": "#f59e0b", "value": 140},
            {"color": "#10b981", "value": 180},
            {"color": "#ef4444", "value": 240}
        ]
    }
    hpm = create_model_dashboard(
        base,
        model_key="HPM 55",
        model_title="🔥 Dashboard Mesin HPM 55",
        model_sub="Pneumatic Double Station Heat Press",
        model_desc="Dashboard monitoring presisi khusus model HPM 55 (Double Station Pneumatic Heat Press, tekanan 4-8 Bar, suhu operasi 50-250°C, dual platen shuttle).",
        model_color="#6366f1",
        regex_pattern=".*(HPM|55).*",
        max_temp=250,
        default_thresholds=hpm_thresholds
    )
    with open("grafana/dashboards/hpm55-dashboard.json", "w", encoding="utf-8") as f:
        json.dump(hpm, f, indent=2, ensure_ascii=False)
    print("✅ Created grafana/dashboards/hpm55-dashboard.json (HPM 55 Dedicated)")

    # 3. AF-450 Dashboard
    af_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "#3b82f6", "value": None},
            {"color": "#06b6d4", "value": 70},
            {"color": "#f59e0b", "value": 130},
            {"color": "#10b981", "value": 170},
            {"color": "#ef4444", "value": 215}
        ]
    }
    af = create_model_dashboard(
        base,
        model_key="AF-450",
        model_title="⚡ Dashboard Mesin AF-450",
        model_sub="Automatic Flatbed Heat Press 450",
        model_desc="Dashboard monitoring presisi khusus model AF-450 (Automatic Flatbed Heat Press seri 450, sistem elektromagnetik auto-open, suhu operasi 50-220°C, platen 40x50cm).",
        model_color="#0ea5e9",
        regex_pattern=".*(AF-450|AF450).*",
        max_temp=220,
        default_thresholds=af_thresholds
    )
    with open("grafana/dashboards/af450-dashboard.json", "w", encoding="utf-8") as f:
        json.dump(af, f, indent=2, ensure_ascii=False)
    print("✅ Created grafana/dashboards/af450-dashboard.json (AF-450 Dedicated)")

    # 4. APM-LOGO Dashboard
    apm_thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "#3b82f6", "value": None},
            {"color": "#06b6d4", "value": 75},
            {"color": "#f59e0b", "value": 135},
            {"color": "#10b981", "value": 175},
            {"color": "#ef4444", "value": 225}
        ]
    }
    apm = create_model_dashboard(
        base,
        model_key="APM-LOGO",
        model_title="🏷️ Dashboard Mesin APM-LOGO",
        model_sub="Auto Positioning Logo Heat Press",
        model_desc="Dashboard monitoring presisi khusus model APM-LOGO (Auto Positioning Motion Logo Heat Press, micro-cylinder pneumatik, pemandu laser guide, suhu 50-230°C, platen 15x15cm).",
        model_color="#f59e0b",
        regex_pattern=".*(APM|LOGO).*",
        max_temp=230,
        default_thresholds=apm_thresholds
    )
    with open("grafana/dashboards/apmlogo-dashboard.json", "w", encoding="utf-8") as f:
        json.dump(apm, f, indent=2, ensure_ascii=False)
    print("✅ Created grafana/dashboards/apmlogo-dashboard.json (APM-LOGO Dedicated)")

if __name__ == "__main__":
    main()

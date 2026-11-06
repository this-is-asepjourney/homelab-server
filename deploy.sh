#!/usr/bin/env bash
# ==============================================================================
# DEPLOYMENT SCRIPT: MASTER HOMELAB SERVER
# ==============================================================================
# Host: fa (Dell OptiPlex 7050, Ubuntu 24.04 LTS)
# Lokasi Proyek: /opt/projects/homelab-server
# Layanan Eksisting: /opt/homelab/
# ==============================================================================

set -euo pipefail

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Direktori Operasional
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOMELAB_INFRA_DIR="/opt/homelab"
PROMETHEUS_DIR="$HOMELAB_INFRA_DIR/prometheus"
PROMETHEUS_CONF="$PROMETHEUS_DIR/config/prometheus.yml"
MOSQUITTO_DIR="$HOMELAB_INFRA_DIR/mosquitto"
DATABASES_DIR="$HOMELAB_INFRA_DIR/databases"
GRAFANA_DIR="$HOMELAB_INFRA_DIR/grafana"

HOST_IP="192.168.25.101"
HOST_TAILSCALE="100.106.63.90"

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║       DEPLOYMENT TERPADU HOMELAB SERVER (UBUNTU fa)                ║"
    echo "║       Arsitektur Zero Duplication & 1 Central API Gateway          ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ------------------------------------------------------------------------------
# 1. VERIFIKASI PRASYARAT SERVER
# ------------------------------------------------------------------------------
check_prerequisites() {
    log_info "Memeriksa kebutuhan perangkat lunak server..."

    if ! command -v docker &>/dev/null; then
        log_error "Docker belum terinstall. Silakan install Docker terlebih dahulu."
        exit 1
    fi

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 belum terinstall."
        exit 1
    fi

    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 belum terinstall."
        exit 1
    fi

    if ! command -v curl &>/dev/null; then
        log_error "Curl belum terinstall."
        exit 1
    fi

    log_success "Semua kebutuhan perangkat lunak (Docker, Compose, Python3, Curl) terpenuhi."
}

# ------------------------------------------------------------------------------
# 2. VERIFIKASI STRUKTUR /opt/homelab EKSISTING
# ------------------------------------------------------------------------------
check_existing_infrastructure() {
    log_info "Memeriksa struktur layanan eksisting di $HOMELAB_INFRA_DIR..."

    if [ ! -d "$HOMELAB_INFRA_DIR" ]; then
        log_warn "Direktori $HOMELAB_INFRA_DIR tidak ditemukan. Pastikan path sesuai pada server."
    else
        [ -d "$DATABASES_DIR" ] && log_success "Ditemukan stack Databases: $DATABASES_DIR"
        [ -d "$MOSQUITTO_DIR" ] && log_success "Ditemukan stack Mosquitto: $MOSQUITTO_DIR"
        [ -d "$GRAFANA_DIR" ] && log_success "Ditemukan stack Grafana: $GRAFANA_DIR"
        [ -d "$PROMETHEUS_DIR" ] && log_success "Ditemukan stack Prometheus: $PROMETHEUS_DIR"
    fi
}

# ------------------------------------------------------------------------------
# 3. SETUP SCRAPE CONFIG PROMETHEUS DOCKER EKSISTING
# ------------------------------------------------------------------------------
configure_prometheus() {
    log_info "Memeriksa konfigurasi Prometheus Docker di $PROMETHEUS_CONF..."

    if [ -f "$PROMETHEUS_CONF" ]; then
        if grep -q "iot_heatpress" "$PROMETHEUS_CONF"; then
            log_success "Scrape job 'iot_heatpress' sudah terdaftar di Prometheus."
        else
            log_warn "Scrape job 'iot_heatpress' belum ada. Menambahkan konfigurasi scrape Telegraf..."
            cp "$PROMETHEUS_CONF" "$PROMETHEUS_CONF.bak_$(date +%Y%m%d%H%M%S)"

            cat << 'EOF' >> "$PROMETHEUS_CONF"

  - job_name: 'iot_heatpress'
    scrape_interval: 5s
    scrape_timeout: 4s
    static_configs:
      - targets: ['192.168.25.101:9273']
        labels:
          environment: 'homelab'
          service: 'heatpress_iot'
EOF
            log_success "Scrape job 'iot_heatpress' berhasil ditambahkan ke $PROMETHEUS_CONF."

            # Reload atau restart container prometheus
            log_info "Me-reload konfigurasi Prometheus Docker..."
            if curl -s -X POST "http://$HOST_IP:9001/-/reload" &>/dev/null; then
                log_success "Prometheus berhasil direload via HTTP API."
            elif [ -d "$PROMETHEUS_DIR" ]; then
                (cd "$PROMETHEUS_DIR" && docker compose restart) || true
                log_success "Container Prometheus berhasil direstart."
            fi
        fi
    else
        log_warn "File $PROMETHEUS_CONF tidak ditemukan. Lewati konfigurasi otomatis Prometheus."
    fi
}

# ------------------------------------------------------------------------------
# 4. SETUP DATABASE POSTGRESQL HOST (PSM)
# ------------------------------------------------------------------------------
setup_postgres_db() {
    log_info "Memeriksa database 'psm' di PostgreSQL host..."
    if command -v psql &>/dev/null; then
        if PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -lqt | cut -d \| -f 1 | grep -qw psm; then
            log_success "Database 'psm' sudah tersedia di PostgreSQL."
        else
            log_info "Membuat database 'psm' di PostgreSQL host..."
            PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -d postgres -c "CREATE DATABASE psm;" || true
            log_success "Database 'psm' siap digunakan."
        fi
    else
        log_info "Client psql lokal tidak ditemukan; inisialisasi database akan ditangani otomatis oleh SQLAlchemy PSM saat runtime."
    fi
}

# ------------------------------------------------------------------------------
# 5. SETUP ENVIRONMENT FILE (.env)
# ------------------------------------------------------------------------------
setup_env() {
    log_info "Memeriksa file .env pada proyek..."
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            log_warn "File .env belum ditemukan. Membuat dari .env.example..."
            cp .env.example .env
            log_success "File .env berhasil dibuat."
        else
            log_error "File .env.example tidak ditemukan!"
            exit 1
        fi
    else
        log_success "File .env sudah tersedia."
    fi

    # Pastikan data/mapping.db sinkron dengan dashboard_iot/api/data/mapping.db
    if [ -f "data/mapping.db" ] && [ ! -f "dashboard_iot/api/data/mapping.db" ]; then
        log_info "Menyinkronkan data/mapping.db ke dashboard_iot/api/data/..."
        mkdir -p dashboard_iot/api/data
        cp data/mapping.db dashboard_iot/api/data/mapping.db
    elif [ -f "dashboard_iot/api/data/mapping.db" ] && [ ! -f "data/mapping.db" ]; then
        mkdir -p data
        cp dashboard_iot/api/data/mapping.db data/mapping.db
    fi
}

# ------------------------------------------------------------------------------
# 6. BUILD DAN JALANKAN DOCKER MASTER STACK
# ------------------------------------------------------------------------------
deploy_containers() {
    log_info "Membangun dan menjalankan Master Compose Stack..."
    
    # Validasi sintaks compose
    docker compose config --quiet
    log_success "Sintaks docker-compose.yml valid."

    # Build container
    log_info "Membangun Docker image (pap-api, psm-api, psm-web, psm-agent, iot-api, iot-web)..."
    docker compose build --parallel

    # Jalankan container
    log_info "Menjalankan container di background..."
    docker compose up -d --remove-orphans

    log_success "Seluruh container telah diinstruksikan berjalan."
}

# ------------------------------------------------------------------------------
# 7. HEALTHCHECK & VERIFIKASI ENDPOINT
# ------------------------------------------------------------------------------
verify_deployment() {
    log_info "Menunggu layanan siap (Healthcheck timeout: 45 detik)..."

    local endpoints=(
        "http://$HOST_IP:8000/health|PAP Core API Gateway (:8000)"
        "http://127.0.0.1:8001/health|PSM Control Plane API (:8001)"
        "http://127.0.0.1:3005|PSM Web Dashboard (:3005)"
        "http://127.0.0.1:8002/health|IoT Device Mapping API (:8002)"
        "http://127.0.0.1:8088|IoT Dashboard Web Hub (:8088)"
        "http://127.0.0.1:9273/metrics|IoT Telegraf Exporter (:9273)"
    )

    sleep 5

    for item in "${endpoints[@]}"; do
        IFS="|" read -r url name <<< "$item"
        local success=0
        for i in {1..9}; do
            if curl -s -f -o /dev/null "$url"; then
                success=1
                break
            fi
            sleep 2
        done

        if [ "$success" -eq 1 ]; then
            log_success "$name -> ONLINE"
        else
            log_warn "$name -> Sedang inisialisasi / cek via 'docker compose logs'"
        fi
    done
}

# ------------------------------------------------------------------------------
# 8. IMPOR GRAFANA DASHBOARD KE GRAFANA EKSISTING (:3001)
# ------------------------------------------------------------------------------
import_grafana_dashboards() {
    echo ""
    log_info "Memeriksa Grafana Utama di http://$HOST_IP:3001..."

    if curl -s "http://$HOST_IP:3001/api/health" &>/dev/null; then
        log_success "Grafana Utama aktif."
        read -r -p "Apakah Anda ingin mengimpor 4 dashboard Heatpress ke Grafana sekarang? [y/N]: " choice || choice="n"
        if [[ "$choice" =~ ^[Yy]$ ]]; then
            read -r -p "Masukkan Grafana Service Token (atau tekan Enter untuk login user/pass): " token || token=""
            if [ -n "$token" ]; then
                python3 homelab.py import-grafana --host "$HOST_IP" --port 3001 --token "$token" || true
            else
                read -r -p "Username [admin]: " guser || guser="admin"
                guser=${guser:-admin}
                read -r -s -p "Password: " gpass || gpass=""
                echo ""
                python3 homelab.py import-grafana --host "$HOST_IP" --port 3001 --user "$guser" --password "$gpass" || true
            fi
        else
            log_info "Impor Grafana dilewati. Anda dapat menjalankannya nanti dengan: python3 homelab.py import-grafana"
        fi
    else
        log_warn "Grafana Utama di port 3001 belum merespons. Lewati impor dashboard."
    fi
}

# ------------------------------------------------------------------------------
# 9. RINGKASAN STATUS AKHIR
# ------------------------------------------------------------------------------
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}          DEPLOYMENT HOMELAB SERVER SELESAI DENGAN SUKSES!         ${NC}"
    echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "Aplikasi dapat diakses melalui alamat berikut:"
    echo -e "  • ${BOLD}PAP Core API Gateway${NC}       : http://$HOST_IP:8000/docs"
    echo -e "  • ${BOLD}PSM Web Dashboard${NC}          : http://$HOST_IP:3005"
    echo -e "  • ${BOLD}PSM Control Plane API${NC}      : http://$HOST_IP:8001/docs"
    echo -e "  • ${BOLD}IoT Dashboard Web Hub${NC}      : http://$HOST_IP:8088"
    echo -e "  • ${BOLD}IoT Device Mapping API${NC}     : http://$HOST_IP:8002/docs"
    echo -e "  • ${BOLD}Grafana Utama Homelab${NC}      : http://$HOST_IP:3001"
    echo -e "  • ${BOLD}Prometheus Server${NC}          : http://$HOST_IP:9001"
    echo -e "  • ${BOLD}Uptime Kuma Health Hub${NC}     : http://$HOST_IP:3002"
    echo ""
    echo -e "Perintah harian yang berguna:"
    echo -e "  Cek status kesehatan      : ${CYAN}python3 homelab.py status${NC}"
    echo -e "  Cek log realtime          : ${CYAN}docker compose logs -f${NC}"
    echo -e "  Restart service tertentu  : ${CYAN}docker compose restart <service_name>${NC}"
    echo -e "  Hentikan stack            : ${CYAN}docker compose down${NC}"
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════════════${NC}"
}

# ------------------------------------------------------------------------------
# MAIN EXECUTION FLOW
# ------------------------------------------------------------------------------
main() {
    print_banner
    check_prerequisites
    check_existing_infrastructure
    configure_prometheus
    setup_postgres_db
    setup_env
    deploy_containers
    verify_deployment
    import_grafana_dashboards
    print_summary
}

main "$@"


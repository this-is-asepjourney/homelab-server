#!/usr/bin/env bash
# ==============================================================================
# DEPLOYMENT SCRIPT: MASTER HOMELAB SERVER
# ==============================================================================
# Host: fa (Dell OptiPlex 7050, Ubuntu 24.04 LTS)
# Lokasi Proyek: /opt/projects/homelab-server
# Layanan Eksisting: /opt/homelab/
# ==============================================================================

set -euo pipefail

# ANSI Colors & Formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
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
TOTAL_STAGES=7
DEPLOY_START_TIME=$(date +%s)

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║       DEPLOYMENT TERPADU HOMELAB SERVER (UBUNTU fa)                ║"
    echo "║       Arsitektur Zero Duplication & 1 Central API Gateway          ║"
    echo "║       PAP Core API + PSM + IoT Fleet + Backup Engine               ║"
    echo "║       Local DNS (CoreDNS :53) + Ingress Router (Nginx :80)         ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info() {
    echo -e "  ${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "  ${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "  ${RED}[ERROR]${NC} $1"
}

# ------------------------------------------------------------------------------
# PROGRESS BAR & SPINNER HELPERS
# ------------------------------------------------------------------------------
show_stage_progress() {
    local step="$1"
    local total="$2"
    local title="$3"
    local subtitle="${4:-}"
    local percent=$(( step * 100 / total ))
    local bar_width=22
    local filled=$(( step * bar_width / total ))
    local empty=$(( bar_width - filled ))
    local bar=""

    for ((i=0; i<filled; i++)); do bar="${bar}█"; done
    for ((i=0; i<empty; i++)); do bar="${bar}░"; done

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "  ${BOLD}[TAHAP ${step}/${total}]  [${bar}]  ${percent}%${NC}"
    echo -e "  ${BOLD}>> ${title}${NC}"
    if [ -n "$subtitle" ]; then
        echo -e "     ${DIM}${subtitle}${NC}"
    fi
    echo -e "${CYAN}════════════════════════════════════════════════════════════════════${NC}"
}

spin_command() {
    local msg="$1"
    shift
    local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    local log_tmp
    log_tmp=$(mktemp /tmp/homelab_deploy_XXXXXX.log)
    
    ("$@") > "$log_tmp" 2>&1 &
    local pid=$!
    local i=0
    local start
    start=$(date +%s)

    while kill -0 "$pid" 2>/dev/null; do
        local now
        now=$(date +%s)
        local elapsed=$(( now - start ))
        printf "\r  ${BLUE}[%s]${NC} %s... (${elapsed}s) " "${spin[$i]}" "$msg"
        i=$(( (i + 1) % 10 ))
        sleep 0.08
    done

    wait "$pid"
    local exit_code=$?
    local total_time=$(( $(date +%s) - start ))

    if [ $exit_code -eq 0 ]; then
        printf "\r  ${GREEN}[✓]${NC} %s (${total_time}s)            \n" "$msg"
        rm -f "$log_tmp"
        return 0
    else
        printf "\r  ${RED}[✗]${NC} %s (Gagal, kode %d)\n" "$msg" "$exit_code"
        echo -e "${RED}--- Output Error Terakhir: ---${NC}"
        tail -n 12 "$log_tmp" 2>/dev/null || true
        echo -e "${RED}------------------------------${NC}"
        rm -f "$log_tmp"
        return $exit_code
    fi
}

# ------------------------------------------------------------------------------
# 1. VERIFIKASI PRASYARAT SERVER
# ------------------------------------------------------------------------------
check_prerequisites() {
    show_stage_progress 1 "$TOTAL_STAGES" "Verifikasi Prasyarat Host Server" "Memeriksa ketersediaan Docker, Compose V2, Python 3, dan tool pendukung..."

    if ! command -v docker &>/dev/null; then
        log_error "Docker belum terinstall. Silakan install Docker terlebih dahulu."
        exit 1
    fi
    log_success "Docker CLI terdeteksi ($(docker --version | cut -d, -f1))."

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 belum terinstall."
        exit 1
    fi
    log_success "Docker Compose V2 terdeteksi ($(docker compose version --short))."

    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 belum terinstall."
        exit 1
    fi
    log_success "Python 3 terdeteksi ($(python3 --version))."

    if ! command -v curl &>/dev/null; then
        log_error "Curl belum terinstall."
        exit 1
    fi
    log_success "Curl HTTP client terverifikasi."
}

# ------------------------------------------------------------------------------
# 2. VERIFIKASI STRUKTUR /opt/homelab EKSISTING
# ------------------------------------------------------------------------------
check_existing_infrastructure() {
    show_stage_progress 2 "$TOTAL_STAGES" "Verifikasi Layanan Infrastruktur Eksisting" "Memeriksa direktori /opt/homelab (Databases, Mosquitto, Grafana, Prometheus)..."

    if [ ! -d "$HOMELAB_INFRA_DIR" ]; then
        log_warn "Direktori $HOMELAB_INFRA_DIR tidak ditemukan pada host. Pastikan path sesuai."
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
    show_stage_progress 3 "$TOTAL_STAGES" "Konfigurasi Scrape Metric Prometheus Host" "Memeriksa scrape job 'iot_heatpress' ke Telegraf :9273..."

    if [ -f "$PROMETHEUS_CONF" ]; then
        if grep -q "iot_heatpress" "$PROMETHEUS_CONF"; then
            log_success "Scrape job 'iot_heatpress' sudah terdaftar di $PROMETHEUS_CONF."
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

            # Reload konfigurasi Prometheus
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
# 4. SETUP DATABASE POSTGRESQL HOST & AUTO-PROVISIONING
# ------------------------------------------------------------------------------
setup_postgres_db() {
    show_stage_progress 4 "$TOTAL_STAGES" "Auto-Provisioning Database Mandiri" "Memeriksa dan membuat database terpisah (psm, pap_core, eternal_db, stock_umkm)..."

    if command -v psql &>/dev/null; then
        if PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw psm; then
            log_success "Database 'psm' sudah tersedia di PostgreSQL host."
        else
            log_info "Membuat database 'psm' di PostgreSQL host..."
            PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -d postgres -c "CREATE DATABASE psm;" 2>/dev/null || true
            log_success "Database 'psm' siap digunakan."
        fi

        if PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw pap_core; then
            log_success "Database 'pap_core' sudah tersedia di PostgreSQL host."
        else
            log_info "Membuat database 'pap_core' di PostgreSQL host..."
            PGPASSWORD="admin12345" psql -h "$HOST_IP" -p 5432 -U appuser -d postgres -c "CREATE DATABASE pap_core;" 2>/dev/null || true
            log_success "Database 'pap_core' siap digunakan."
        fi
    else
        log_info "Client psql lokal tidak ditemukan; inisialisasi database ditangani otomatis oleh engine runtime."
    fi

    # Inisialisasi otomatis semua database mandiri per project
    if command -v python3 &>/dev/null && [ -f "auto_provision_all_databases.py" ]; then
        spin_command "Auto-provisioning database mandiri (eternal_db, stock_umkm, psm, pap_core)" python3 auto_provision_all_databases.py || true
    fi
}

# ------------------------------------------------------------------------------
# 5. SETUP ENVIRONMENT FILE & MONOREPO MODULES
# ------------------------------------------------------------------------------
setup_env() {
    show_stage_progress 5 "$TOTAL_STAGES" "Verifikasi Konfigurasi & Modul Monorepo" "Memeriksa .env, router ingress, backup directory, dan modul monorepo..."

    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            log_warn "File .env belum ditemukan. Membuat dari .env.example..."
            cp .env.example .env
            log_success "File .env berhasil dibuat dari .env.example."
        else
            log_error "File .env.example tidak ditemukan!"
            exit 1
        fi
    else
        log_success "File .env konfigurasi server terverifikasi."
    fi

    # Pastikan direktori operasional siap
    mkdir -p router/conf.d/projects dns /opt/homelab/backups backups
    log_success "Direktori Router Ingress, DNS, dan Backups siap."

    # Periksa kelengkapan file modul
    local missing=0
    [ ! -d "Personal_Server_Manager/infrastructure/docker" ] && { log_error "Modul Personal_Server_Manager tidak lengkap!"; missing=1; }
    [ ! -d "Personal Api Platform/docker" ] && { log_error "Modul Personal Api Platform tidak lengkap!"; missing=1; }
    [ ! -d "dashboard_iot/web" ] && { log_error "Modul dashboard_iot tidak lengkap!"; missing=1; }

    if [ "$missing" -eq 1 ]; then
        log_error "Repository belum di-pull dengan lengkap."
        exit 1
    fi
    log_success "Seluruh modul Monorepo terpadu lengkap dan siap di-build."
}

# ------------------------------------------------------------------------------
# 6. BUILD DAN JALANKAN DOCKER MASTER STACK
# ------------------------------------------------------------------------------
deploy_containers() {
    show_stage_progress 6 "$TOTAL_STAGES" "Membangun & Menjalankan Master Compose Stack" "Parallel Docker build (pap-api, psm-web, psm-agent, iot-web) & compose up..."

    # Validasi sintaks compose
    docker compose config --quiet
    log_success "Sintaks docker-compose.yml terverifikasi valid."

    # Build container parallel dengan progress spinner
    log_info "Membangun Docker image (pap-api, psm-web, psm-agent, iot-web)..."
    docker compose build --parallel

    # Bersihkan kontainer lama / zombie
    log_info "Membersihkan kontainer lama & me-reset port routing..."
    docker rm -f psm-api psm-web psm-agent pap-api iot_telegraf iot_device_mapping_api iot_dashboard_web homelab_router homelab_dns 2>/dev/null || true
    docker network rm iot-network 2>/dev/null || true

    # Jalankan container
    spin_command "Meluncurkan seluruh container master stack di background" docker compose up -d --remove-orphans

    log_success "Seluruh container master stack aktif di jaringan Docker."
}

# ------------------------------------------------------------------------------
# 7. HEALTHCHECK & VERIFIKASI ENDPOINT LIVE
# ------------------------------------------------------------------------------
verify_deployment() {
    show_stage_progress 7 "$TOTAL_STAGES" "Live Endpoint Healthcheck & Latency Meter" "Memverifikasi seluruh endpoint layanan aktif dan mengukur latency..."

    local endpoints=(
        "http://$HOST_IP:8000/health|PAP Core Central API Gateway|8000"
        "http://$HOST_IP:8000/|Homelab Mission Control Web UI|8000"
        "http://$HOST_IP:8000/api/health|IoT Fleet Telemetry Gateway|8000"
        "http://$HOST_IP:8000/api/v1/backups|Homelab Backup Engine|8000"
        "http://$HOST_IP:8000/api/v1/dns/records|Local DNS & Virtual Hosts API|8000"
        "http://127.0.0.1:80|Homelab Ingress Router (Nginx)|80"
        "http://127.0.0.1:3005|PSM Web Dashboard Console|3005"
        "http://127.0.0.1:8088|IoT Dashboard Web Hub|8088"
        "http://127.0.0.1:9273/metrics|IoT Telegraf Exporter|9273"
    )

    sleep 3
    local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

    for item in "${endpoints[@]}"; do
        IFS="|" read -r url name port <<< "$item"
        local success=0
        local http_code=""
        local time_total=""

        for i in {1..12}; do
            local spin_char="${spin[$(( i % 10 ))]}"
            printf "\r    ${BLUE}[%s]${NC} %-30s (Percobaan %2d/12) Menunggu endpoint..." "$spin_char" "$name" "$i"

            local res
            res=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" --connect-timeout 2 "$url" 2>/dev/null || echo "000 0")
            http_code=$(echo "$res" | awk '{print $1}')
            time_total=$(echo "$res" | awk '{print $2}')

            if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 500 ]; then
                success=1
                break
            fi
            sleep 1.5
        done

        local ms="?"
        if command -v awk &>/dev/null; then
            ms=$(awk "BEGIN {printf \"%.1f\", $time_total * 1000}")"ms"
        fi

        if [ "$success" -eq 1 ]; then
            printf "\r    ${GREEN}[✓]${NC} %-30s Port :%-5s -> ONLINE (HTTP %s, %s)    \n" "$name" "$port" "$http_code" "$ms"
        else
            printf "\r    ${YELLOW}[!]${NC} %-30s Port :%-5s -> INISIALISASI (Cek: docker compose logs)\n" "$name" "$port"
        fi
    done
}

# ------------------------------------------------------------------------------
# IMPOR GRAFANA DASHBOARD KE GRAFANA EKSISTING (:3001)
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
# RINGKASAN STATUS AKHIR
# ------------------------------------------------------------------------------
print_summary() {
    local deploy_end_time
    deploy_end_time=$(date +%s)
    local duration=$(( deploy_end_time - DEPLOY_START_TIME ))

    echo ""
    echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}          DEPLOYMENT HOMELAB SERVER SELESAI DENGAN SUKSES!         ${NC}"
    echo -e "          Total Waktu Eksekusi: ${duration} detik"
    echo -e "${GREEN}${BOLD}════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "Akses via Local DNS & Virtual Host (Port 80):"
    echo -e "  • ${BOLD}Homelab Mission Control${NC} : http://homelab (atau http://api.homelab)"
    echo -e "  • ${BOLD}Personal Server Manager${NC} : http://psm.homelab"
    echo -e "  • ${BOLD}IoT Dashboard Fleet${NC}     : http://iot.homelab"
    echo -e "  • ${BOLD}Grafana Visualizations${NC}  : http://grafana.homelab"
    echo -e "  • ${BOLD}Prometheus Metrics${NC}      : http://prometheus.homelab"
    echo -e "  • ${BOLD}Uptime Kuma Hub${NC}         : http://kuma.homelab"
    echo -e "  • ${BOLD}Vaultwarden Passwords${NC}   : http://vault.homelab"
    echo -e "  • ${BOLD}Cockpit OS Console${NC}      : http://cockpit.homelab"
    echo ""
    echo -e "Aplikasi dapat diakses langsung melalui Port Server:"
    echo -e "  • ${BOLD}Homelab Mission Control Web UI${NC} : http://$HOST_IP:8000/ (atau http://$HOST_TAILSCALE:8000/)"
    echo -e "  • ${BOLD}PAP Core Central API Gateway${NC}   : http://$HOST_IP:8000/docs"
    echo -e "  • ${BOLD}Backup & Disaster Recovery${NC}     : http://$HOST_IP:8000/api/v1/backups"
    echo -e "  • ${BOLD}PSM Web Dashboard Console${NC}      : http://$HOST_IP:3005"
    echo -e "  • ${BOLD}IoT Dashboard Web Hub${NC}          : http://$HOST_IP:8088"
    echo -e "  • ${BOLD}Grafana Utama Homelab${NC}          : http://$HOST_IP:3001"
    echo -e "  • ${BOLD}Prometheus Server${NC}              : http://$HOST_IP:9001"
    echo ""
    echo -e "Perintah harian yang berguna:"
    echo -e "  Deploy master stack       : ${CYAN}python3 homelab.py deploy${NC} (atau ./deploy.sh)"
    echo -e "  Cek status kesehatan      : ${CYAN}python3 homelab.py status${NC}"
    echo -e "  Cek daftar domain DNS     : ${CYAN}python3 homelab.py dns${NC}"
    echo -e "  Buat backup sistem        : ${CYAN}curl -X POST http://127.0.0.1:8000/api/v1/backups/create${NC}"
    echo -e "  Cek log realtime          : ${CYAN}docker compose logs -f${NC}"
    echo -e "  Restart gateway           : ${CYAN}docker compose restart pap-api${NC}"
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

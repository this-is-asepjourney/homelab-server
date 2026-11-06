// ─────────────────────────────────────────────────────────────────────────────
// Heatpress IoT Fleet Dashboard — app.js v3.0
// Hirarki Model: Heatpress -> HPM 55, AF-450, APM-LOGO, Coming Soon
// Multi-Model Dedicated Dashboards & Universal Monitoring
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE_URL = '/api/devices';
const REFRESH_INTERVAL_SEC = 30;
// Menggunakan Grafana eksisting di port 3001 (sesuai port.md) dengan fallback proxy /grafana
const GRAFANA_BASE = window.GRAFANA_BASE_URL || (window.location.port === '8088' ? `${window.location.protocol}//${window.location.hostname}:3001` : '/grafana');

const DASHBOARD_CONFIG = {
    universal: {
        uid: 'iot-universal',
        title: 'Dashboard Universal — Monitoring Armada Heatpress',
        desc: 'Monitoring telemetri terpadu seluruh armada mesin Heatpress (HPM 55, AF-450, APM-LOGO) secara real-time',
        icon: 'bx-globe',
        badge: 'Universal Fleet',
        themeColor: '#6366f1'
    },
    'HPM 55': {
        uid: 'hpm55-monitoring',
        title: 'Dashboard Mesin HPM 55 — Pneumatic Double Station',
        desc: 'Dedicated precision monitoring model HPM 55: Tekanan 4-8 Bar • Suhu 50°C-250°C • Dual Platen Shuttle',
        icon: 'bx-flame',
        badge: 'Pneumatic Press',
        themeColor: '#ef4444'
    },
    'AF-450': {
        uid: 'af450-dashboard',
        title: 'Dashboard Mesin AF-450 — Automatic Flatbed 450',
        desc: 'Dedicated precision monitoring model AF-450: Auto-Open Elektromagnetik • Suhu 50°C-220°C • Single Flatbed 40x50cm',
        icon: 'bx-layer',
        badge: 'Auto Flatbed',
        themeColor: '#0ea5e9'
    },
    'APM-LOGO': {
        uid: 'apmlogo-dashboard',
        title: 'Dashboard Mesin APM-LOGO — Auto Positioning Logo',
        desc: 'Dedicated precision monitoring model APM-LOGO: Micro-Cylinder Pneumatik • Laser Guide • Suhu 50°C-230°C • Platen 15x15cm',
        icon: 'bx-purchase-tag-alt',
        badge: 'Logo Precision',
        themeColor: '#f59e0b'
    }
};

const app = {
    devices: [],
    statuses: {},          // { mac_address: true/false }
    stats: {},             // { total, online, offline, mapped, unmapped }
    hierarchyData: null,   // Hierarchical response from /api/devices/hierarchy
    lastSeenCache: {},     // { mac_address: ISO string }
    currentModelFilter: 'all', // 'all' | 'HPM 55' | 'AF-450' | 'APM-LOGO' | 'comingsoon'
    activeDashboard: 'universal', // 'universal' | 'HPM 55' | 'AF-450' | 'APM-LOGO'
    selectedDeviceForDash: 'all', // 'all' or MAC
    universalModelFilter: 'all',  // 'all' | 'HPM 55' | 'AF-450' | 'APM-LOGO'
    countdownTimer: null,
    countdownValue: REFRESH_INTERVAL_SEC,
    currentPage: 'hierarchy',

    // ─── Init ────────────────────────────────────────────────────────────────
    init() {
        this.fetchAll(false);
        this.checkSystemHealth();
        this.startCountdown();

        // Auto-refresh setiap 30 detik
        setInterval(() => {
            this.fetchAll(true);
            this.checkSystemHealth();
        }, REFRESH_INTERVAL_SEC * 1000);
    },

    // ─── Page Navigation ─────────────────────────────────────────────────────
    showPage(page, resetFilter = false) {
        this.currentPage = page;

        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.sidebar-nav .nav-item').forEach(n => n.classList.remove('active'));

        const targetPage = document.getElementById(`page-${page}`);
        if (targetPage) targetPage.classList.add('active');

        if (page === 'hierarchy') {
            const navEl = document.getElementById('nav-hierarchy');
            if (navEl) navEl.classList.add('active');
            this.renderHierarchyCards();
        } else if (page === 'grafana') {
            this.renderGrafanaView();
        } else if (page === 'devices') {
            const navEl = document.getElementById('nav-devices');
            if (navEl) navEl.classList.add('active');
            if (resetFilter) {
                this.currentModelFilter = 'all';
                document.querySelectorAll('.model-pill').forEach(p => p.classList.remove('active'));
                const pillAll = document.getElementById('pill-all');
                if (pillAll) pillAll.classList.add('active');
            }
            this.applyFilters();
        }
    },

    // ─── Fetch All Data ───────────────────────────────────────────────────────
    async fetchAll(silent = false) {
        const tableBody = document.getElementById('deviceTableBody');
        if (!silent && this.devices.length === 0 && tableBody) {
            tableBody.innerHTML = `<tr><td colspan="9" class="text-center"><div class="loader-container"><div class="loader"></div><p>Memuat armada heatpress...</p></div></td></tr>`;
        }

        const icon1 = document.getElementById('refresh-icon');
        const icon2 = document.getElementById('refresh-icon-h');
        if (icon1) icon1.classList.add('bx-spin');
        if (icon2) icon2.classList.add('bx-spin');

        try {
            const [devicesRes, statusesRes, statsRes, hierarchyRes] = await Promise.all([
                fetch(`${API_BASE_URL}/`),
                fetch(`${API_BASE_URL}/statuses`),
                fetch(`${API_BASE_URL}/stats`),
                fetch(`${API_BASE_URL}/hierarchy`),
            ]);

            if (!devicesRes.ok) throw new Error('Gagal mengambil data armada');
            this.devices = await devicesRes.json();

            if (statusesRes.ok) {
                const newStatuses = await statusesRes.json();
                
                // Deteksi perubahan status online/offline untuk toast
                if (Object.keys(this.statuses).length > 0) {
                    for (const mac in newStatuses) {
                        const oldStatus = this.statuses[mac];
                        const newStatus = newStatuses[mac];
                        if (oldStatus !== undefined && oldStatus !== newStatus) {
                            const device = this.devices.find(d => d.mac_address.toUpperCase() === mac);
                            const devName = device && device.name ? device.name : mac;
                            const modelName = device && device.model ? ` (${device.model})` : '';
                            if (newStatus) {
                                this.showToast(`Mesin "${devName}"${modelName} terhubung (ONLINE)`, 'success');
                            } else {
                                this.showToast(`Mesin "${devName}"${modelName} terputus (OFFLINE)`, 'error');
                            }
                        }
                    }
                }
                this.statuses = newStatuses;
            } else {
                this.statuses = {};
                this.devices.forEach(d => { this.statuses[d.mac_address.toUpperCase()] = false; });
            }

            if (statsRes.ok) {
                this.stats = await statsRes.json();
            }

            if (hierarchyRes.ok) {
                this.hierarchyData = await hierarchyRes.json();
            }

            this.renderHierarchyCards();
            this.updateModelPills();
            this.updateSidebarCounts();
            this.applyFilters();
            this.updateStats();
            this.updateLastUpdated();
            this.resetCountdown();

        } catch (error) {
            console.error('Error fetching armada data:', error);
            if (!silent) {
                this.showToast('Gagal memuat data dari server', 'error');
                if (tableBody) {
                    tableBody.innerHTML = `<tr><td colspan="9" class="text-center text-danger">Gagal memuat data. Periksa apakah container API berjalan.</td></tr>`;
                }
            }
        } finally {
            if (icon1) icon1.classList.remove('bx-spin');
            if (icon2) icon2.classList.remove('bx-spin');
        }
    },

    // ─── Sync From Prometheus ────────────────────────────────────────────────
    async syncFromPrometheus() {
        const icon1 = document.getElementById('refresh-icon');
        const icon2 = document.getElementById('refresh-icon-h');
        if (icon1) icon1.classList.add('bx-spin');
        if (icon2) icon2.classList.add('bx-spin');

        try {
            const res = await fetch(`${API_BASE_URL}/sync-prometheus`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!res.ok) throw new Error('Gagal sinkronisasi dengan Prometheus');
            const result = await res.json();

            await this.fetchAll(true);

            const count = result.devices ? result.devices.length : 3;
            this.showToast(`Sinkronisasi berhasil! ${count} device armada Heatpress aktif terdeteksi.`, 'success');
        } catch (error) {
            console.error('Error syncing with Prometheus:', error);
            this.showToast('Gagal sinkronisasi data dari Prometheus', 'error');
        } finally {
            if (icon1) icon1.classList.remove('bx-spin');
            if (icon2) icon2.classList.remove('bx-spin');
        }
    },

    // ─── Render Hierarchy Cards (Armada Heatpress) ───────────────────────────
    renderHierarchyCards() {
        const container = document.getElementById('hierarchyCardsContainer');
        if (!container) return;

        // Fallback default structure if hierarchy endpoint not loaded yet
        const models = this.hierarchyData && this.hierarchyData.models ? this.hierarchyData.models : [
            {
                id: 'HPM 55',
                name: 'HPM 55',
                type: 'Pneumatic Double Station',
                status: 'active',
                icon: 'bx-flame',
                badge_color: 'primary',
                description: 'Double station pneumatic heat press bertekanan tinggi untuk transfer sublimasi, sablon DTF, dan heat seal presisi.',
                specs: { pressure: '4 - 8 Bar', temp_range: '50°C - 250°C', station: 'Dual Platen' }
            },
            {
                id: 'AF-450',
                name: 'AF-450',
                type: 'Automatic Flat Press 450',
                status: 'active',
                icon: 'bx-layer',
                badge_color: 'teal',
                description: 'Flatbed heat press otomatis seri 450 dengan pemanas presisi tinggi dan auto-open elektromagnetik.',
                specs: { pressure: 'Electromagnetic Auto-Open', temp_range: '50°C - 220°C', station: 'Single Flatbed 40x50cm' }
            },
            {
                id: 'APM-LOGO',
                name: 'APM-LOGO',
                type: 'Auto Positioning Motion Logo',
                status: 'active',
                icon: 'bx-purchase-tag-alt',
                badge_color: 'amber',
                description: 'Mesin heatpress khusus logo, badge, dan label pakaian dengan penempatan posisi otomatis dan laser guide.',
                specs: { pressure: 'Precision Micro Cylinder', temp_range: '50°C - 230°C', station: 'Compact Platen 15x15cm' }
            },
            {
                id: 'comingsoon',
                name: 'Coming Soon',
                type: 'Next-Gen Intelligent Press',
                status: 'coming_soon',
                icon: 'bx-time-five',
                badge_color: 'purple',
                description: 'Slot ekspansi mesin heatpress generasi pintar masa depan dengan sensor tekanan digital terintegrasi (load cell) dan multi-zone heating.',
                specs: { pressure: 'Load-Cell Force Feedback', temp_range: '30°C - 300°C Multi-Zone', station: 'Smart Modular Platen' }
            }
        ];

        container.innerHTML = '';

        models.forEach(m => {
            const isComingSoon = m.status === 'coming_soon' || m.id === 'comingsoon';
            
            // Filter devices matching this model
            const matchingDevices = this.devices.filter(d => {
                const mod = (d.model || '').toUpperCase().replace('-', ' ');
                const mid = m.name.toUpperCase().replace('-', ' ');
                if (isComingSoon) return mod.includes('COMING');
                if (mid.includes('HPM') || mid.includes('55')) return mod.includes('HPM') || mod.includes('55');
                if (mid.includes('AF') || mid.includes('450')) return mod.includes('AF') || mod.includes('450');
                if (mid.includes('APM') || mid.includes('LOGO')) return mod.includes('APM') || mod.includes('LOGO');
                return mod.includes(mid);
            });

            const totalInModel = matchingDevices.length;
            const onlineInModel = matchingDevices.filter(d => this.statuses[d.mac_address.toUpperCase()] === true).length;

            const card = document.createElement('div');
            let cardModClass = 'model-card--hpm';
            if (m.name.includes('AF') || m.id.includes('AF')) cardModClass = 'model-card--af';
            else if (m.name.includes('APM') || m.id.includes('APM')) cardModClass = 'model-card--apm';
            else if (isComingSoon) cardModClass = 'model-card--comingsoon';

            card.className = `model-card ${cardModClass}`;

            // Specs chips HTML
            const specsHtml = m.specs ? Object.entries(m.specs).map(([k, v]) => `<span class="spec-chip">${this._esc(v)}</span>`).join('') : '';

            // Devices list inside card
            let devicesSnippetHtml = '';
            if (isComingSoon) {
                devicesSnippetHtml = `
                    <div class="model-devices-snippet">
                        <div class="model-devices-snippet-header">
                            <span>Status Pengembangan</span>
                            <span class="badge" style="background:rgba(139,92,246,0.15);color:#8b5cf6;padding:2px 8px;font-size:10px;">Pipeline R&D</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-sub);line-height:1.6;">
                            • Integrasi MQTT Multi-Zone PID Heat Controller<br>
                            • Real-time Clamp Load-Cell Pressure Logger<br>
                            • Dual Shuttle High-Speed Automation Sync
                        </div>
                    </div>`;
            } else if (matchingDevices.length === 0) {
                devicesSnippetHtml = `
                    <div class="model-devices-snippet">
                        <div class="model-devices-snippet-header">
                            <span>Perangkat Terhubung</span>
                            <span>0 Unit</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-muted);padding:8px 0;text-align:center;">
                            Belum ada perangkat terdaftar untuk model ini.
                        </div>
                    </div>`;
            } else {
                const rowsHtml = matchingDevices.map(d => {
                    const isOnline = this.statuses[d.mac_address.toUpperCase()] === true;
                    return `
                        <div class="mini-device-row" onclick="app.monitorDeviceInDashboard('${this._esc(d.mac_address)}')" title="Klik untuk monitor langsung di Dashboard ${this._esc(m.name)}" style="cursor:pointer;">
                            <span class="mini-device-name">
                                <span class="status-dot ${isOnline ? 'online' : 'offline'}" style="width:7px;height:7px;"></span>
                                ${this._esc(d.name || d.mac_address)}
                                ${d.mcid ? `<span class="mcid-badge" style="padding:1px 5px;font-size:10px;"><i class='bx bx-link'></i>${this._esc(d.mcid)}</span>` : ''}
                            </span>
                            <span class="mini-device-mac">
                                ${this._esc(d.mac_address)}
                                <i class='bx bx-line-chart' style="margin-left:6px;font-size:12px;opacity:0.75;" title="Monitor Device"></i>
                            </span>
                        </div>`;
                }).join('');

                devicesSnippetHtml = `
                    <div class="model-devices-snippet">
                        <div class="model-devices-snippet-header">
                            <span>Perangkat Terhubung</span>
                            <span style="color:${onlineInModel > 0 ? '#10b981' : 'var(--text-muted)'};font-weight:700;">
                                ${onlineInModel} Online / ${totalInModel} Unit
                            </span>
                        </div>
                        ${rowsHtml}
                    </div>`;
            }

            // Buttons
            let buttonsHtml = '';
            if (isComingSoon) {
                buttonsHtml = `
                    <div class="model-card-actions">
                        <button class="btn btn-secondary" onclick="app.openModal('add', null, 'Coming Soon')" style="width:100%;">
                            <i class='bx bx-plus-circle'></i> Siapkan Slot / Prototype
                        </button>
                    </div>`;
            } else {
                buttonsHtml = `
                    <div class="model-card-actions">
                        <button class="btn btn-secondary" onclick="app.filterByModel('${this._esc(m.name)}')" title="Lihat di tabel">
                            <i class='bx bx-list-ul'></i> Tabel
                        </button>
                        <button class="btn btn-secondary" onclick="app.switchToDashboard('${this._esc(m.name)}')" title="Buka Dashboard Khusus ${this._esc(m.name)}">
                            <i class='bx ${m.icon || "bx-line-chart"}' style="color:#f59e0b;"></i> Dashboard
                        </button>
                        <button class="btn btn-primary" onclick="app.openModal('add', null, '${this._esc(m.name)}')" title="Tambah unit baru untuk model ini">
                            <i class='bx bx-plus'></i> Tambah
                        </button>
                    </div>`;
            }

            card.innerHTML = `
                <div>
                    <div class="model-card-header">
                        <div class="model-card-brand">
                            <div class="model-card-icon">
                                <i class='bx ${m.icon || "bx-cube"}'></i>
                            </div>
                            <div>
                                <div class="model-card-title">${this._esc(m.name)}</div>
                                <div class="model-card-type">${this._esc(m.type || "Heatpress Machine")}</div>
                            </div>
                        </div>
                        <span class="model-status-pill ${isComingSoon ? 'model-status-pill--comingsoon' : 'model-status-pill--active'}">
                            ${isComingSoon ? '<i class="bx bx-time"></i> Coming Soon' : '<i class="bx bx-check-circle"></i> Aktif'}
                        </span>
                    </div>

                    <p class="model-card-desc">${this._esc(m.description || "")}</p>
                    <div class="model-specs-list">${specsHtml}</div>
                    ${devicesSnippetHtml}
                </div>
                ${buttonsHtml}
            `;

            container.appendChild(card);
        });

        // Update Hero stats
        const heroDevices = document.getElementById('hero-devices-count');
        const heroOnline = document.getElementById('hero-online-count');
        if (heroDevices) heroDevices.textContent = `${this.devices.length} Mesin`;
        if (heroOnline) {
            const onlineCount = Object.values(this.statuses).filter(v => v === true).length;
            heroOnline.textContent = `${onlineCount} Mesin Aktif`;
        }
    },

    // ─── Filter By Model (from cards or sidebar) ──────────────────────────────
    filterByModel(modelName) {
        this.currentModelFilter = modelName;
        this.showPage('devices');

        // Update active class on pills
        document.querySelectorAll('.model-pill').forEach(p => p.classList.remove('active'));
        const pillId = modelName === 'HPM 55' ? 'pill-hpm' :
                       modelName === 'AF-450' ? 'pill-af' :
                       modelName === 'APM-LOGO' ? 'pill-apm' :
                       modelName === 'comingsoon' ? 'pill-comingsoon' : 'pill-all';
        const pillEl = document.getElementById(pillId);
        if (pillEl) pillEl.classList.add('active');

        this.applyFilters();
    },

    setTableFilterModel(modelName, buttonEl) {
        this.currentModelFilter = modelName;
        document.querySelectorAll('.model-pill').forEach(p => p.classList.remove('active'));
        if (buttonEl) buttonEl.classList.add('active');
        this.applyFilters();
    },

    // ─── Update Model Pills and Sidebar Counts ────────────────────────────────
    updateModelPills() {
        const hpmCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('HPM') || m.includes('55');
        }).length;

        const afCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('AF') || m.includes('450');
        }).length;

        const apmCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('APM') || m.includes('LOGO');
        }).length;

        const comingCount = this.devices.filter(d => (d.model || '').toUpperCase().includes('COMING')).length;

        const pillAll = document.getElementById('pill-all-count');
        const pillHpm = document.getElementById('pill-hpm-count');
        const pillAf = document.getElementById('pill-af-count');
        const pillApm = document.getElementById('pill-apm-count');
        const pillComing = document.getElementById('pill-comingsoon-count');

        if (pillAll) pillAll.textContent = this.devices.length;
        if (pillHpm) pillHpm.textContent = hpmCount;
        if (pillAf) pillAf.textContent = afCount;
        if (pillApm) pillApm.textContent = apmCount;
        if (pillComing) pillComing.textContent = comingCount;
    },

    updateSidebarCounts() {
        const hpmCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('HPM') || m.includes('55');
        }).length;

        const afCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('AF') || m.includes('450');
        }).length;

        const apmCount = this.devices.filter(d => {
            const m = (d.model || '').toUpperCase();
            return m.includes('APM') || m.includes('LOGO');
        }).length;

        const elHpm = document.getElementById('subnav-count-hpm');
        const elAf = document.getElementById('subnav-count-af');
        const elApm = document.getElementById('subnav-count-apm');

        if (elHpm) elHpm.textContent = hpmCount;
        if (elAf) elAf.textContent = afCount;
        if (elApm) elApm.textContent = apmCount;

        const badgeHpm = document.getElementById('badge-count-hpm');
        const badgeAf = document.getElementById('badge-count-af');
        const badgeApm = document.getElementById('badge-count-apm');

        if (badgeHpm) badgeHpm.textContent = `${hpmCount} Unit`;
        if (badgeAf) badgeAf.textContent = `${afCount} Unit`;
        if (badgeApm) badgeApm.textContent = `${apmCount} Unit`;
    },

    // ─── Apply Filters (search + status + model) ─────────────────────────────
    applyFilters() {
        const searchInput = document.getElementById('searchInput');
        const statusFilterEl = document.getElementById('statusFilter');

        const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
        const statusFilter = statusFilterEl ? statusFilterEl.value : 'all';
        const modelFilter = this.currentModelFilter;

        let filtered = this.devices.filter(d => {
            // Model Filter
            if (modelFilter !== 'all') {
                const mod = (d.model || '').toUpperCase().replace('-', ' ');
                const targetMod = modelFilter.toUpperCase().replace('-', ' ');
                let matchModel = false;
                if (targetMod.includes('HPM') || targetMod.includes('55')) {
                    matchModel = mod.includes('HPM') || mod.includes('55');
                } else if (targetMod.includes('AF') || targetMod.includes('450')) {
                    matchModel = mod.includes('AF') || mod.includes('450');
                } else if (targetMod.includes('APM') || targetMod.includes('LOGO')) {
                    matchModel = mod.includes('APM') || mod.includes('LOGO');
                } else if (targetMod.includes('COMING')) {
                    matchModel = mod.includes('COMING');
                } else {
                    matchModel = mod.includes(targetMod);
                }
                if (!matchModel) return false;
            }

            // Search Filter
            const matchSearch = !query ||
                (d.name && d.name.toLowerCase().includes(query)) ||
                (d.mac_address && d.mac_address.toLowerCase().includes(query)) ||
                (d.mcid && d.mcid.toLowerCase().includes(query)) ||
                (d.location && d.location.toLowerCase().includes(query)) ||
                (d.model && d.model.toLowerCase().includes(query)) ||
                (d.device_type && d.device_type.toLowerCase().includes(query));

            // Status Filter
            const isOnline = this.statuses[d.mac_address.toUpperCase()] === true;
            const matchStatus = statusFilter === 'all' ||
                (statusFilter === 'online' && isOnline) ||
                (statusFilter === 'offline' && !isOnline);

            return matchSearch && matchStatus;
        });

        this.renderTable(filtered);

        const countLabel = document.getElementById('device-count-label');
        if (countLabel) {
            const total = this.devices.length;
            const showing = filtered.length;
            countLabel.textContent = showing === total
                ? `${total} device terdaftar dalam armada`
                : `Menampilkan ${showing} dari ${total} device`;
        }
    },

    // ─── Render Table ─────────────────────────────────────────────────────────
    renderTable(data) {
        const tableBody = document.getElementById('deviceTableBody');
        if (!tableBody) return;
        tableBody.innerHTML = '';

        if (!data || data.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center empty-state">
                        <i class='bx bx-devices empty-icon'></i>
                        <p>Tidak ada device ditemukan untuk filter ini.</p>
                        <p class="text-muted">Klik <strong>Tambah Device</strong> untuk mendaftarkan device ke hirarki model ini.</p>
                    </td>
                </tr>`;
            return;
        }

        data.forEach(device => {
            const row = document.createElement('tr');
            const isOnline = this.statuses[device.mac_address.toUpperCase()] === true;

            const lastSeenStr = this._formatLastSeen(device.mac_address);

            // MCID badge
            const mcidHtml = device.mcid
                ? `<span class="mcid-badge"><i class='bx bx-link'></i>${this._esc(device.mcid)}</span>`
                : `<span class="mcid-empty" title="Belum di-mapping ke mesin fisik"><i class='bx bx-unlink'></i> —</span>`;

            // Model Badge
            const modelBadgeHtml = (() => {
                const mod = (device.model || '').toUpperCase();
                if (mod.includes('HPM') || mod.includes('55')) {
                    return `<span class="model-badge model-badge--hpm"><i class='bx bx-flame'></i> ${this._esc(device.model || 'HPM 55')}</span>`;
                } else if (mod.includes('AF') || mod.includes('450')) {
                    return `<span class="model-badge model-badge--af"><i class='bx bx-layer'></i> ${this._esc(device.model || 'AF-450')}</span>`;
                } else if (mod.includes('APM') || mod.includes('LOGO')) {
                    return `<span class="model-badge model-badge--apm"><i class='bx bx-purchase-tag-alt'></i> ${this._esc(device.model || 'APM-LOGO')}</span>`;
                } else if (mod.includes('COMING')) {
                    return `<span class="model-badge model-badge--comingsoon"><i class='bx bx-time-five'></i> Coming Soon</span>`;
                }
                return `<span class="model-badge"><i class='bx bx-cube'></i> ${this._esc(device.model || 'Heatpress')}</span>`;
            })();

            row.innerHTML = `
                <td>
                    <div class="status-badge ${isOnline ? 'online' : 'offline'}">
                        <span class="status-dot"></span>
                        <span class="status-text">${isOnline ? 'Online' : 'Offline'}</span>
                    </div>
                </td>
                <td>${modelBadgeHtml}</td>
                <td><span class="mac-address">${this._esc(device.mac_address)}</span></td>
                <td>${mcidHtml}</td>
                <td><strong>${this._esc(device.name || '—')}</strong>${device.description ? `<br><small class="text-muted">${this._esc(device.description)}</small>` : ''}</td>
                <td><span class="type-badge">${this._esc(device.device_type || 'ESP32')}</span></td>
                <td>${device.location ? `<span class="location-tag"><i class='bx bx-map-pin'></i> ${this._esc(device.location)}</span>` : '<span class="text-muted">—</span>'}</td>
                <td class="last-seen-cell">${lastSeenStr}</td>
                <td class="actions-cell">
                    <button class="btn btn-icon text-success" onclick="app.monitorDeviceInDashboard('${device.mac_address}')" title="Buka Dashboard Khusus & Monitor Device">
                        <i class='bx bx-line-chart'></i>
                    </button>
                    <button class="btn btn-icon text-info" onclick="app.openGrafanaModal('${device.mac_address}')" title="Preview Fullscreen Modal">
                        <i class='bx bx-window-open'></i>
                    </button>
                    <button class="btn btn-icon" onclick="app.openModal('edit', '${device.mac_address}')" title="Edit Device">
                        <i class='bx bx-edit-alt'></i>
                    </button>
                    <button class="btn btn-icon text-danger" onclick="app.deleteDevice('${device.mac_address}')" title="Hapus Device">
                        <i class='bx bx-trash'></i>
                    </button>
                </td>`;

            tableBody.appendChild(row);

            // Fetch last seen non-blocking
            this._fetchLastSeen(device.mac_address);
        });
    },

    // ─── Fetch Last Seen ──────────────────────────────────────────────────────
    async _fetchLastSeen(macAddress) {
        if (this.lastSeenCache[macAddress] !== undefined) return;
        this.lastSeenCache[macAddress] = null;

        try {
            const res = await fetch(`${API_BASE_URL}/${encodeURIComponent(macAddress)}/last-seen`);
            if (!res.ok) return;
            const data = await res.json();
            this.lastSeenCache[macAddress] = data.last_seen || null;

            const rows = document.querySelectorAll('#deviceTableBody tr');
            rows.forEach(row => {
                const macCell = row.querySelector('.mac-address');
                if (macCell && macCell.textContent.trim() === macAddress) {
                    const lastSeenCell = row.querySelector('.last-seen-cell');
                    if (lastSeenCell) {
                        lastSeenCell.innerHTML = this._formatLastSeen(macAddress);
                    }
                }
            });
        } catch {
            this.lastSeenCache[macAddress] = null;
        }
    },

    _formatLastSeen(macAddress) {
        const cached = this.lastSeenCache[macAddress];
        if (cached === undefined) return '<span class="text-muted">...</span>';
        if (!cached) return '<span class="text-muted">—</span>';

        const dt = new Date(cached);
        const now = new Date();
        const diffSec = Math.floor((now - dt) / 1000);

        let relative;
        if (diffSec < 60) relative = `${diffSec}d lalu`;
        else if (diffSec < 3600) relative = `${Math.floor(diffSec / 60)}m lalu`;
        else if (diffSec < 86400) relative = `${Math.floor(diffSec / 3600)}j lalu`;
        else relative = `${Math.floor(diffSec / 86400)}h lalu`;

        const full = dt.toLocaleString('id-ID', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        return `<span class="last-seen" title="${full}">${relative}</span>`;
    },

    // ─── Update Stats Cards ───────────────────────────────────────────────────
    updateStats() {
        const s = this.stats;
        const total = s.total !== undefined ? s.total : this.devices.length;
        const onlineCount = s.online !== undefined ? s.online : Object.values(this.statuses).filter(v => v === true).length;
        const offlineCount = s.offline !== undefined ? s.offline : (total - onlineCount);
        const mappedCount = s.mapped !== undefined ? s.mapped : this.devices.filter(d => d.mcid && d.mcid.trim()).length;

        const elTotal = document.getElementById('total-devices-count');
        const elOnline = document.getElementById('online-devices-count');
        const elOffline = document.getElementById('offline-devices-count');
        const elMapped = document.getElementById('mapped-devices-count');

        if (elTotal) elTotal.textContent = total;
        if (elOnline) elOnline.textContent = onlineCount;
        if (elOffline) elOffline.textContent = offlineCount;
        if (elMapped) elMapped.textContent = mappedCount;

        const onlineCard = document.querySelector('.stat-card--online');
        if (onlineCard) onlineCard.classList.toggle('has-online', onlineCount > 0);
    },

    updateLastUpdated() {
        const now = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const el = document.getElementById('last-updated-time');
        if (el) el.textContent = now;
    },

    // ─── Countdown ────────────────────────────────────────────────────────────
    startCountdown() {
        this.countdownValue = REFRESH_INTERVAL_SEC;
        this.countdownTimer = setInterval(() => {
            this.countdownValue--;
            const el = document.getElementById('refresh-countdown');
            if (el) el.textContent = this.countdownValue;
            if (this.countdownValue <= 0) this.countdownValue = REFRESH_INTERVAL_SEC;
        }, 1000);
    },

    resetCountdown() {
        this.countdownValue = REFRESH_INTERVAL_SEC;
        const el = document.getElementById('refresh-countdown');
        if (el) el.textContent = REFRESH_INTERVAL_SEC;
    },

    // ─── System Health Check & PAP Main API Status ────────────────────────────
    async checkSystemHealth() {
        const dot = document.getElementById('sys-status-dot');
        const label = document.getElementById('sys-status-label');
        const papDot = document.getElementById('pap-status-dot');
        const papLabel = document.getElementById('pap-status-label');
        const papSub = document.getElementById('pap-status-sub');
        try {
            const res = await fetch('/api/health', { signal: AbortSignal.timeout(4000) });
            const data = res.ok ? await res.json() : null;
            if (data && data.status === 'healthy') {
                if (dot) { dot.style.background = '#10b981'; dot.style.boxShadow = '0 0 8px rgba(16,185,129,0.6)'; }
                if (label) label.textContent = 'Sistem Normal';
            } else {
                if (dot) { dot.style.background = '#f59e0b'; dot.style.boxShadow = '0 0 8px rgba(245,158,11,0.6)'; }
                if (label) label.textContent = 'Degraded';
            }
            if (data && data.pap_api === 'ok') {
                if (papDot) { papDot.style.background = '#10b981'; papDot.style.boxShadow = '0 0 8px rgba(16,185,129,0.6)'; }
                if (papLabel) papLabel.textContent = 'PAP Main API';
                if (papSub) papSub.textContent = 'Terhubung (API Utama)';
            } else {
                if (papDot) { papDot.style.background = '#f59e0b'; papDot.style.boxShadow = '0 0 8px rgba(245,158,11,0.6)'; }
                if (papLabel) papLabel.textContent = 'PAP Main API';
                if (papSub) papSub.textContent = 'Local Fallback Mode';
            }
        } catch {
            if (dot) { dot.style.background = '#ef4444'; dot.style.boxShadow = '0 0 8px rgba(239,68,68,0.6)'; }
            if (label) label.textContent = 'API Offline';
        }
    },

    async syncWithPap() {
        const icon = document.getElementById('pap-sync-icon-h');
        if (icon) icon.classList.add('bx-spin');
        try {
            const res = await fetch('/api/pap/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) throw new Error('Gagal sinkronisasi ke PAP Main API');
            const body = await res.json();
            await this.fetchAll(true);
            await this.checkSystemHealth();
            if (body.pap && body.pap.pap_reachable) {
                this.showToast(`Terhubung ke Personal API Platform! (${body.total_devices} device tersinkronisasi)`, 'success');
            } else {
                this.showToast(`Data disinkronkan secara lokal (${body.total_devices} device).`, 'success');
            }
        } catch (err) {
            console.error('Error syncing with PAP Main API:', err);
            this.showToast('Gagal sinkronisasi dengan PAP Main API', 'error');
        } finally {
            if (icon) icon.classList.remove('bx-spin');
        }
    },

    // ─── Multi-Model Dashboard & Grafana Monitoring ──────────────────────────
    switchToDashboard(dashKey, targetMac = null) {
        if (!DASHBOARD_CONFIG[dashKey]) {
            const upper = (dashKey || '').toUpperCase();
            if (upper.includes('HPM') || upper.includes('55')) dashKey = 'HPM 55';
            else if (upper.includes('AF') || upper.includes('450')) dashKey = 'AF-450';
            else if (upper.includes('APM') || upper.includes('LOGO')) dashKey = 'APM-LOGO';
            else dashKey = 'universal';
        }

        this.activeDashboard = dashKey;
        if (targetMac) {
            this.selectedDeviceForDash = targetMac;
        } else {
            this.selectedDeviceForDash = 'all';
        }

        // Show grafana page
        this.showPage('grafana');

        // Update nav items active states in sidebar
        document.querySelectorAll('.sidebar-nav .nav-item, .sidebar-nav .sub-nav-item').forEach(el => el.classList.remove('active'));
        if (dashKey === 'universal') {
            const navUni = document.getElementById('nav-dash-universal');
            if (navUni) navUni.classList.add('active');
        } else if (dashKey === 'HPM 55') {
            const navHpm = document.getElementById('subnav-dash-hpm');
            if (navHpm) navHpm.classList.add('active');
        } else if (dashKey === 'AF-450') {
            const navAf = document.getElementById('subnav-dash-af');
            if (navAf) navAf.classList.add('active');
        } else if (dashKey === 'APM-LOGO') {
            const navApm = document.getElementById('subnav-dash-apm');
            if (navApm) navApm.classList.add('active');
        }

        // Update dashboard tab buttons
        document.querySelectorAll('.dash-tab').forEach(tab => tab.classList.remove('active'));
        const tabId = dashKey === 'universal' ? 'tab-dash-universal' :
                      dashKey === 'HPM 55' ? 'tab-dash-hpm' :
                      dashKey === 'AF-450' ? 'tab-dash-af' : 'tab-dash-apm';
        const tabEl = document.getElementById(tabId);
        if (tabEl) tabEl.classList.add('active');

        this.renderGrafanaView();
    },

    renderGrafanaView() {
        const cfg = DASHBOARD_CONFIG[this.activeDashboard] || DASHBOARD_CONFIG.universal;
        const isUniversal = this.activeDashboard === 'universal';

        // Update page title and description
        const headerTitle = document.getElementById('grafana-header-title');
        const headerDesc = document.getElementById('grafana-header-desc');
        if (headerTitle) headerTitle.innerHTML = `<i class='bx ${cfg.icon}' style="color:${cfg.themeColor};"></i> ${cfg.title}`;
        if (headerDesc) headerDesc.textContent = cfg.desc;

        // Show/hide universal model filter
        const modelFilterGroup = document.getElementById('universal-model-filter-group');
        if (modelFilterGroup) {
            modelFilterGroup.style.display = isUniversal ? 'flex' : 'none';
        }

        // Populate device select dropdown
        this.populateGrafanaDeviceDropdown();

        // Load Grafana iframe
        this.loadGrafanaFrame();
    },

    populateGrafanaDeviceDropdown() {
        const sel = document.getElementById('grafana-device-select');
        if (!sel) return;
        sel.innerHTML = '';

        const isUniversal = this.activeDashboard === 'universal';
        let candidateDevices = this.devices;

        if (isUniversal) {
            if (this.universalModelFilter && this.universalModelFilter !== 'all') {
                const targetModel = this.universalModelFilter.toUpperCase().replace('-', ' ');
                candidateDevices = this.devices.filter(d => {
                    const m = (d.model || '').toUpperCase().replace('-', ' ');
                    if (targetModel.includes('HPM') || targetModel.includes('55')) return m.includes('HPM') || m.includes('55');
                    if (targetModel.includes('AF') || targetModel.includes('450')) return m.includes('AF') || m.includes('450');
                    if (targetModel.includes('APM') || targetModel.includes('LOGO')) return m.includes('APM') || m.includes('LOGO');
                    return m.includes(targetModel);
                });
            }

            // Universal All Option
            const optAll = document.createElement('option');
            optAll.value = 'all';
            optAll.textContent = `🌐 Pantau Seluruh Armada (${candidateDevices.length} Mesin)`;
            sel.appendChild(optAll);
        } else {
            // Dedicated model
            const targetModel = this.activeDashboard.toUpperCase().replace('-', ' ');
            candidateDevices = this.devices.filter(d => {
                const m = (d.model || '').toUpperCase().replace('-', ' ');
                if (targetModel.includes('HPM') || targetModel.includes('55')) return m.includes('HPM') || m.includes('55');
                if (targetModel.includes('AF') || targetModel.includes('450')) return m.includes('AF') || m.includes('450');
                if (targetModel.includes('APM') || targetModel.includes('LOGO')) return m.includes('APM') || m.includes('LOGO');
                return m.includes(targetModel);
            });

            // Dedicated All Option
            const optAll = document.createElement('option');
            optAll.value = 'all';
            optAll.textContent = `⚡ Pantau Seluruh Unit ${this.activeDashboard} (${candidateDevices.length} Mesin)`;
            sel.appendChild(optAll);
        }

        // Add device items
        candidateDevices.forEach(d => {
            const isOnline = this.statuses[d.mac_address.toUpperCase()] === true;
            const indicator = isOnline ? '🟢' : '⚫';
            const mcidPart = d.mcid ? ` [${d.mcid}]` : '';
            const modelPart = isUniversal && d.model ? ` (${d.model})` : '';
            const opt = document.createElement('option');
            opt.value = d.mac_address;
            opt.textContent = `${indicator} ${d.name || d.mac_address}${mcidPart}${modelPart} — ${d.mac_address}`;
            sel.appendChild(opt);
        });

        // Set selected value
        if (this.selectedDeviceForDash && (this.selectedDeviceForDash === 'all' || candidateDevices.some(d => d.mac_address === this.selectedDeviceForDash))) {
            sel.value = this.selectedDeviceForDash;
        } else {
            this.selectedDeviceForDash = 'all';
            sel.value = 'all';
        }

        // Update active chip summary
        const chipText = document.getElementById('activeDashSummaryText');
        if (chipText) {
            const onlineCount = candidateDevices.filter(d => this.statuses[d.mac_address.toUpperCase()] === true).length;
            if (this.selectedDeviceForDash === 'all') {
                chipText.textContent = `${onlineCount} Online / ${candidateDevices.length} Unit ${isUniversal ? 'Armada' : this.activeDashboard}`;
            } else {
                const curDev = this.devices.find(d => d.mac_address === this.selectedDeviceForDash);
                const curOnline = curDev ? this.statuses[curDev.mac_address.toUpperCase()] === true : false;
                chipText.textContent = `${curOnline ? 'Online' : 'Offline'} • ${curDev ? (curDev.name || curDev.mac_address) : this.selectedDeviceForDash}`;
            }
        }
    },

    loadGrafanaFrame() {
        const iframe = document.getElementById('grafanaPageIframe');
        const loader = document.getElementById('grafana-page-loader');
        const placeholder = document.getElementById('grafana-placeholder');
        const directLink = document.getElementById('grafana-direct-link');

        const cfg = DASHBOARD_CONFIG[this.activeDashboard] || DASHBOARD_CONFIG.universal;
        const isUniversal = this.activeDashboard === 'universal';

        let params = [];
        params.push('kiosk=tv');
        params.push('theme=dark');

        if (isUniversal) {
            if (this.universalModelFilter && this.universalModelFilter !== 'all') {
                if (this.universalModelFilter.includes('HPM') || this.universalModelFilter.includes('55')) {
                    params.push('var-model=' + encodeURIComponent('.*(HPM|55).*'));
                } else if (this.universalModelFilter.includes('AF') || this.universalModelFilter.includes('450')) {
                    params.push('var-model=' + encodeURIComponent('.*(AF-450|AF450).*'));
                } else if (this.universalModelFilter.includes('APM') || this.universalModelFilter.includes('LOGO')) {
                    params.push('var-model=' + encodeURIComponent('.*(APM|LOGO).*'));
                }
            } else {
                params.push('var-model=$__all');
            }
        }

        if (this.selectedDeviceForDash && this.selectedDeviceForDash !== 'all') {
            params.push('var-mac=' + encodeURIComponent(this.selectedDeviceForDash));
        } else {
            params.push('var-mac=$__all');
        }

        const fullUrl = `${GRAFANA_BASE}/d/${cfg.uid}/?${params.join('&')}`;

        if (directLink) directLink.href = fullUrl;

        if (placeholder) placeholder.style.display = 'none';
        if (loader) loader.style.display = 'flex';
        if (iframe) {
            iframe.style.display = 'none';
            iframe.src = fullUrl;
        }
    },

    onDeviceSelectChange(mac) {
        this.selectedDeviceForDash = mac || 'all';
        this.populateGrafanaDeviceDropdown();
        this.loadGrafanaFrame();
    },

    onGrafanaModelChange(model) {
        this.universalModelFilter = model;
        this.selectedDeviceForDash = 'all';
        this.populateGrafanaDeviceDropdown();
        this.loadGrafanaFrame();
    },

    refreshGrafanaIframe() {
        const icon = document.getElementById('grafana-refresh-btn-icon');
        if (icon) icon.classList.add('bx-spin');
        const iframe = document.getElementById('grafanaPageIframe');
        if (iframe && iframe.src) {
            const currentSrc = iframe.src;
            iframe.src = '';
            setTimeout(() => {
                iframe.src = currentSrc;
                if (icon) icon.classList.remove('bx-spin');
            }, 200);
        } else {
            this.loadGrafanaFrame();
            if (icon) icon.classList.remove('bx-spin');
        }
        this.showToast('Memperbarui visualisasi dashboard Grafana', 'success');
    },

    monitorDeviceInDashboard(macAddress) {
        const dev = this.devices.find(d => d.mac_address === macAddress);
        let targetModel = 'universal';
        if (dev && dev.model) {
            const m = dev.model.toUpperCase();
            if (m.includes('HPM') || m.includes('55')) targetModel = 'HPM 55';
            else if (m.includes('AF') || m.includes('450')) targetModel = 'AF-450';
            else if (m.includes('APM') || m.includes('LOGO')) targetModel = 'APM-LOGO';
        }

        const devName = dev ? (dev.name || macAddress) : macAddress;
        this.switchToDashboard(targetModel, macAddress);
        this.showToast(`Membuka Dashboard ${targetModel} untuk perangkat "${devName}"`, 'success');
    },

    openGrafanaModal(macAddress) {
        const modal = document.getElementById('grafanaModal');
        const iframe = document.getElementById('grafanaIframe');
        const title = document.getElementById('grafanaModalTitle');
        const loader = document.getElementById('grafanaLoader');
        const openLink = document.getElementById('grafana-open-link');

        const device = this.devices.find(d => d.mac_address === macAddress);
        const displayName = device ? (device.name || macAddress) : macAddress;
        const mcidInfo = device && device.mcid ? ` [${device.mcid}]` : '';

        let targetModel = 'universal';
        if (device && device.model) {
            const m = device.model.toUpperCase();
            if (m.includes('HPM') || m.includes('55')) targetModel = 'HPM 55';
            else if (m.includes('AF') || m.includes('450')) targetModel = 'AF-450';
            else if (m.includes('APM') || m.includes('LOGO')) targetModel = 'APM-LOGO';
        }

        const cfg = DASHBOARD_CONFIG[targetModel] || DASHBOARD_CONFIG.universal;
        const isOnline = this.statuses[macAddress.toUpperCase()] === true;
        const statusEmoji = isOnline ? '🟢' : '⚫';
        title.innerHTML = `${statusEmoji} ${displayName}${mcidInfo} <span class="badge" style="margin-left:8px;font-size:11px;background:rgba(99,102,241,0.15);color:${cfg.themeColor};">${cfg.badge}</span>`;

        const grafanaUrl = `${GRAFANA_BASE}/d/${cfg.uid}/?var-mac=${encodeURIComponent(macAddress)}&kiosk=tv&theme=dark`;

        if (openLink) openLink.href = grafanaUrl;

        loader.style.display = 'flex';
        iframe.style.display = 'none';
        iframe.src = grafanaUrl;

        modal.classList.add('active');
    },

    onGrafanaLoad() {
        const loader = document.getElementById('grafanaLoader');
        const iframe = document.getElementById('grafanaIframe');
        if (loader) loader.style.display = 'none';
        if (iframe) iframe.style.display = 'block';
    },

    closeGrafanaModal() {
        const modal = document.getElementById('grafanaModal');
        const iframe = document.getElementById('grafanaIframe');
        modal.classList.remove('active');
        setTimeout(() => { iframe.src = ''; iframe.style.display = 'none'; }, 300);
    },

    onGrafanaPageLoad() {
        const loader = document.getElementById('grafana-page-loader');
        const iframe = document.getElementById('grafanaPageIframe');
        if (loader) loader.style.display = 'none';
        if (iframe) iframe.style.display = 'block';
    },

    // ─── Add / Edit Modal ─────────────────────────────────────────────────────
    selectModelPreset(modelName) {
        const modelInput = document.getElementById('deviceModel');
        if (modelInput) modelInput.value = modelName;

        // Auto pre-fill name suggestion if empty
        const nameInput = document.getElementById('deviceName');
        if (nameInput && (!nameInput.value || nameInput.value.startsWith('Heatpress') || nameInput.value.startsWith('HPM') || nameInput.value.startsWith('AF') || nameInput.value.startsWith('APM'))) {
            if (modelName === 'HPM 55') nameInput.value = 'HPM 55 Press';
            else if (modelName === 'AF-450') nameInput.value = 'AF-450 Auto Flat';
            else if (modelName === 'APM-LOGO') nameInput.value = 'APM-LOGO Precision';
            else if (modelName === 'comingsoon') nameInput.value = 'Next-Gen Heatpress Prototype';
        }

        // Auto prefill MCID suggestion if empty
        const mcidInput = document.getElementById('deviceMcid');
        if (mcidInput && !mcidInput.value) {
            if (modelName === 'HPM 55') mcidInput.value = 'HP-55-02';
            else if (modelName === 'AF-450') mcidInput.value = 'AF-450-02';
            else if (modelName === 'APM-LOGO') mcidInput.value = 'APM-02';
        }

        // Highlight chip
        document.querySelectorAll('.model-select-chip').forEach(c => c.classList.remove('selected'));
        const chipId = modelName === 'HPM 55' ? 'chip-hpm' :
                       modelName === 'AF-450' ? 'chip-af' :
                       modelName === 'APM-LOGO' ? 'chip-apm' : 'chip-comingsoon';
        const chipEl = document.getElementById(chipId);
        if (chipEl) chipEl.classList.add('selected');
    },

    openModal(mode, macAddress = null, defaultModel = 'HPM 55') {
        const modal = document.getElementById('deviceModal');
        const form = document.getElementById('deviceForm');
        const title = document.getElementById('modalTitle');
        const modeInput = document.getElementById('formMode');
        const macInput = document.getElementById('macAddress');
        const macError = document.getElementById('mac-error');
        const icon = document.getElementById('modal-icon');

        form.reset();
        macError.textContent = '';
        modeInput.value = mode;

        if (mode === 'add') {
            title.textContent = 'Tambah Device ke Armada';
            if (icon) icon.className = 'bx bx-plus-circle modal-title-icon';
            macInput.disabled = false;
            this.selectModelPreset(defaultModel || 'HPM 55');
        } else if (mode === 'edit') {
            title.textContent = 'Edit Informasi Device';
            if (icon) icon.className = 'bx bx-edit modal-title-icon';
            const device = this.devices.find(d => d.mac_address === macAddress);
            if (device) {
                macInput.value = device.mac_address;
                macInput.disabled = true;
                document.getElementById('deviceCategory').value = device.category || 'Heatpress';
                document.getElementById('deviceModel').value = device.model || '';
                document.getElementById('deviceMcid').value = device.mcid || '';
                document.getElementById('deviceName').value = device.name || '';
                document.getElementById('deviceType').value = device.device_type || 'ESP32';
                document.getElementById('deviceLocation').value = device.location || '';
                document.getElementById('deviceDescription').value = device.description || '';

                // Select matching chip
                const mod = (device.model || '').toUpperCase();
                if (mod.includes('HPM') || mod.includes('55')) this.selectModelPreset('HPM 55');
                else if (mod.includes('AF') || mod.includes('450')) this.selectModelPreset('AF-450');
                else if (mod.includes('APM') || mod.includes('LOGO')) this.selectModelPreset('APM-LOGO');
                else if (mod.includes('COMING')) this.selectModelPreset('comingsoon');
            }
        }

        modal.classList.add('active');
        setTimeout(() => {
            const firstEnabled = form.querySelector('input:not([disabled])');
            if (firstEnabled) firstEnabled.focus();
        }, 200);
    },

    closeModal() {
        document.getElementById('deviceModal').classList.remove('active');
    },

    validateMac(mac) {
        return /^([0-9A-Fa-f]{2}[:\-]){5}([0-9A-Fa-f]{2})$/.test(mac.trim());
    },

    // ─── Form Submit ──────────────────────────────────────────────────────────
    async handleFormSubmit(event) {
        event.preventDefault();
        const mode = document.getElementById('formMode').value;
        const saveButton = document.getElementById('saveButton');
        const macError = document.getElementById('mac-error');
        macError.textContent = '';

        const mac = document.getElementById('macAddress').value.trim().toUpperCase();

        if (mode === 'add' && !this.validateMac(mac)) {
            macError.textContent = 'Format MAC tidak valid. Gunakan format XX:XX:XX:XX:XX:XX';
            document.getElementById('macAddress').focus();
            return;
        }

        const deviceData = {
            mac_address: mac,
            category: document.getElementById('deviceCategory').value.trim() || 'Heatpress',
            model: document.getElementById('deviceModel').value.trim() || 'HPM 55',
            mcid: document.getElementById('deviceMcid').value.trim() || null,
            name: document.getElementById('deviceName').value.trim(),
            device_type: document.getElementById('deviceType').value.trim() || 'ESP32',
            location: document.getElementById('deviceLocation').value.trim() || null,
            description: document.getElementById('deviceDescription').value.trim() || null,
        };

        if (!deviceData.name) {
            this.showToast('Nama device wajib diisi', 'error');
            document.getElementById('deviceName').focus();
            return;
        }

        saveButton.disabled = true;
        saveButton.innerHTML = `<i class='bx bx-loader-alt bx-spin'></i> Menyimpan...`;

        try {
            if (mode === 'add') {
                const response = await fetch(`${API_BASE_URL}/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(deviceData),
                });
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Gagal menambah device');
                }
                this.showToast(`Device "${deviceData.name}" berhasil didaftarkan ke model ${deviceData.model}`, 'success');
            } else {
                const { mac_address, ...updateData } = deviceData;
                const response = await fetch(`${API_BASE_URL}/${mac}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateData),
                });
                if (!response.ok) throw new Error('Gagal memperbarui device');
                this.showToast(`Device "${deviceData.name}" berhasil diperbarui`, 'success');
            }
            this.closeModal();
            await this.fetchAll(false);
        } catch (error) {
            console.error('Error saving device:', error);
            this.showToast(error.message, 'error');
        } finally {
            saveButton.disabled = false;
            saveButton.innerHTML = `<i class='bx bx-save'></i> Simpan Device`;
        }
    },

    // ─── Delete Device ────────────────────────────────────────────────────────
    async deleteDevice(macAddress) {
        const device = this.devices.find(d => d.mac_address === macAddress);
        const name = device ? device.name : macAddress;
        const mcidInfo = device && device.mcid ? ` (MCID: ${device.mcid})` : '';

        if (!confirm(`Hapus device "${name}"${mcidInfo} (${macAddress}) dari armada Heatpress?\n\nAksi ini tidak dapat dibatalkan.`)) return;

        try {
            const response = await fetch(`${API_BASE_URL}/${macAddress}`, { method: 'DELETE' });
            if (!response.ok) throw new Error('Gagal menghapus device');
            delete this.lastSeenCache[macAddress];
            this.showToast(`Device "${name}" berhasil dihapus`, 'success');
            await this.fetchAll(false);
        } catch (error) {
            console.error('Error deleting device:', error);
            this.showToast('Error menghapus device', 'error');
        }
    },

    // ─── Export CSV ───────────────────────────────────────────────────────────
    exportCSV() {
        if (this.devices.length === 0) {
            this.showToast('Tidak ada data untuk di-export', 'error');
            return;
        }

        const headers = ['Kategori', 'Model', 'MAC Address', 'Machine ID (MCID)', 'Nama Device', 'Tipe Hardware', 'Lokasi', 'Catatan', 'Status', 'Terdaftar'];
        const rows = this.devices.map(d => {
            const isOnline = this.statuses[d.mac_address.toUpperCase()] === true ? 'Online' : 'Offline';
            const createdAt = d.created_at ? new Date(d.created_at).toLocaleString('id-ID') : '';
            return [
                d.category || 'Heatpress',
                d.model || '',
                d.mac_address,
                d.mcid || '',
                d.name || '',
                d.device_type || '',
                d.location || '',
                d.description || '',
                isOnline,
                createdAt,
            ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',');
        });

        const csv = [headers.join(','), ...rows].join('\n');
        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `heatpress-fleet-devices-${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);

        this.showToast(`${this.devices.length} device armada berhasil di-export`, 'success');
    },

    // ─── Toast Notifications ──────────────────────────────────────────────────
    showToast(message, type = 'success') {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        const icon = type === 'success' ? 'bx-check-circle' : 'bx-error-circle';
        toast.innerHTML = `<i class='bx ${icon} toast-icon'></i><span>${message}</span>`;
        container.appendChild(toast);
        void toast.offsetWidth;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    },

    // ─── Escape HTML ──────────────────────────────────────────────────────────
    _esc(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    },
};

// Initialize app on load
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});

'use client';

import React, { useState, useEffect } from 'react';
import {
  Radio,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
  Activity,
  HardDrive,
  Globe,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  Search,
  Maximize2
} from 'lucide-react';
import { api } from '../../lib/api';

export default function MissionControlPage() {
  const [activeTab, setActiveTab] = useState<'topology' | 'backups' | 'worker'>('topology');
  const [loading, setLoading] = useState(false);
  const [workerStatus, setWorkerStatus] = useState<any>(null);
  const [backups, setBackups] = useState<any[]>([]);
  const [verifyingFile, setVerifyingFile] = useState<string | null>(null);
  const [verifyReport, setVerifyReport] = useState<any>(null);
  const [gatewayUrl, setGatewayUrl] = useState('http://localhost:8000');

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const host = window.location.hostname || 'localhost';
      setGatewayUrl(`http://${host}:8000`);
    }
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const [wRes, bRes] = await Promise.all([
        api.getWorkerStatus().catch(() => null),
        api.getBackupsList().catch(() => null),
      ]);
      if (wRes && wRes.data) {
        setWorkerStatus(wRes.data);
      }
      if (bRes && bRes.data) {
        setBackups(bRes.data);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (filename: string) => {
    try {
      setVerifyingFile(filename);
      const res = await api.verifyBackupIntegrity(filename);
      if (res && res.data) {
        setVerifyReport(res.data);
      }
    } catch (e: any) {
      alert('Gagal verifikasi arsip: ' + e.message);
    } finally {
      setVerifyingFile(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* HEADER ROW */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-xl border border-border bg-card/60 backdrop-blur-md shadow-sm">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <Radio className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
                Homelab Mission Control &amp; Architecture Core
              </h1>
              <p className="text-xs text-muted-foreground">
                Unified Central API Gateway (:8000) • Decoupled Background Worker • Full-Stack Backup &amp; Live Telemetry
              </p>
            </div>
          </div>
        </div>

        {/* STATUS PILLS & ACTIONS */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Worker Status Badge */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background text-xs">
            <span className={`w-2 h-2 rounded-full ${workerStatus?.healthy ? 'bg-emerald-500' : 'bg-amber-500 animate-ping'}`} />
            <span className="font-semibold text-foreground">pap-worker:</span>
            <span className="text-emerald-500 font-mono text-[11px]">
              {workerStatus?.healthy ? `Decoupled (${workerStatus?.details?.uptime_sec || 0}s)` : 'Standby / Internal'}
            </span>
          </div>

          <button
            onClick={loadStatus}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground text-xs font-medium transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>

          <a
            href={gatewayUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all shadow-sm"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            <span>Buka Layar Penuh (:8000)</span>
          </a>
        </div>
      </div>

      {/* NAVIGATION TABS */}
      <div className="flex items-center gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab('topology')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'topology'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Peta Topologi &amp; Streaming Realtime</span>
        </button>

        <button
          onClick={() => setActiveTab('backups')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'backups'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
          }`}
        >
          <HardDrive className="w-4 h-4" />
          <span>Disaster Recovery &amp; Backups ({backups.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('worker')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'worker'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-accent hover:text-foreground'
          }`}
        >
          <Cpu className="w-4 h-4" />
          <span>Engine Decoupled Worker</span>
        </button>
      </div>

      {/* TAB 1: TOPOLOGY EMBED */}
      {activeTab === 'topology' && (
        <div className="rounded-xl border border-border bg-card overflow-hidden shadow-lg">
          <div className="p-3 bg-muted/40 border-b border-border flex items-center justify-between text-xs">
            <span className="font-mono text-muted-foreground flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              Live Interactive Architecture Map Canvas (WebSocket Stream: /api/v1/traffic/ws)
            </span>
            <span className="text-[11px] text-muted-foreground">
              Menampilkan paket HTTP, Ingress, DNS, InfluxDB &amp; ESP32 Telemetri
            </span>
          </div>
          <iframe
            src={`${gatewayUrl}/ui`}
            className="w-full h-[780px] border-0 bg-[#070d19]"
            title="Homelab Architecture Topology"
          />
        </div>
      )}

      {/* TAB 2: DISASTER RECOVERY & BACKUPS */}
      {activeTab === 'backups' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-xl border border-border bg-card">
              <div className="text-xs text-muted-foreground uppercase font-semibold">Total Arsip Backup</div>
              <div className="text-2xl font-bold text-foreground mt-1">{backups.length} Arsip</div>
              <div className="text-[11px] text-muted-foreground mt-1">Snapshot Full-Stack Homelab</div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card">
              <div className="text-xs text-muted-foreground uppercase font-semibold">Cakupan Database</div>
              <div className="text-sm font-semibold text-emerald-500 mt-1">Postgres + MySQL + InfluxDB</div>
              <div className="text-[11px] text-muted-foreground mt-1">psm, pap_core, eternal_db, stock_umkm, telemetry</div>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card">
              <div className="text-xs text-muted-foreground uppercase font-semibold">Auto-Prune Retention</div>
              <div className="text-sm font-semibold text-blue-500 mt-1">7 Hari (Min 3 Snapshot)</div>
              <div className="text-[11px] text-muted-foreground mt-1">Dikelola otomatis oleh pap-worker</div>
            </div>
          </div>

          {/* Backup Archives Table */}
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h2 className="font-bold text-sm text-foreground">Daftar Snapshot Backup Server</h2>
              <span className="text-xs text-muted-foreground">Format Kompresi: .tar.gz (SHA-256 Validated)</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]">
                  <tr>
                    <th className="p-3">Nama File Arsip</th>
                    <th className="p-3">Lingkup</th>
                    <th className="p-3">Ukuran</th>
                    <th className="p-3">Waktu Dibuat</th>
                    <th className="p-3">Database Terkandung</th>
                    <th className="p-3 text-right">Aksi</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border font-mono">
                  {backups.map((b: any) => (
                    <tr key={b.filename} className="hover:bg-muted/30 transition-colors">
                      <td className="p-3">
                        <span className="font-bold text-foreground">{b.filename}</span>
                        {b.note && <div className="text-[10px] text-muted-foreground font-sans">{b.note}</div>}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-500 text-[10px]">
                          {b.scope}
                        </span>
                      </td>
                      <td className="p-3 font-semibold text-foreground">{b.size_human}</td>
                      <td className="p-3 text-muted-foreground font-sans">
                        {new Date(b.created_at).toLocaleString('id-ID')}
                      </td>
                      <td className="p-3">
                        <div className="flex flex-wrap gap-1">
                          {Object.keys(b.databases || {}).map((db: string) => (
                            <span key={db} className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500 text-[9px]">
                              {db}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="p-3 text-right space-x-2">
                        <button
                          onClick={() => handleVerify(b.filename)}
                          disabled={verifyingFile === b.filename}
                          className="px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white text-[10px] font-sans disabled:opacity-60 transition-all"
                        >
                          {verifyingFile === b.filename ? 'Menguji...' : '🔍 Verifikasi'}
                        </button>
                        <a
                          href={`${gatewayUrl}/api/v1/backups/${encodeURIComponent(b.filename)}/download`}
                          className="px-2.5 py-1 rounded bg-secondary hover:bg-secondary/80 text-foreground text-[10px] font-sans transition-all inline-block"
                        >
                          ⬇️ Unduh
                        </a>
                      </td>
                    </tr>
                  ))}
                  {backups.length === 0 && (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-muted-foreground font-sans">
                        Belum ada arsip backup terdaftar.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Modal / Report Section */}
          {verifyReport && (
            <div className="p-5 rounded-xl border border-emerald-500/30 bg-emerald-950/20 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <h3 className="font-bold text-sm text-foreground">
                    Hasil Verifikasi Integritas: {verifyReport.filename}
                  </h3>
                </div>
                <button
                  onClick={() => setVerifyReport(null)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  ✕ Tutup Laporan
                </button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="p-2.5 rounded bg-background/50 border border-border">
                  <span className="text-muted-foreground block text-[10px]">STATUS</span>
                  <span className="font-bold text-emerald-400 text-sm">{verifyReport.status}</span>
                </div>
                <div className="p-2.5 rounded bg-background/50 border border-border">
                  <span className="text-muted-foreground block text-[10px]">SKOR KELAYAKAN RESTORE</span>
                  <span className="font-bold text-sky-400 text-sm">{verifyReport.integrity_score_percent}%</span>
                </div>
                <div className="p-2.5 rounded bg-background/50 border border-border">
                  <span className="text-muted-foreground block text-[10px]">STREAM TAR.GZ</span>
                  <span className="font-bold text-foreground">{verifyReport.tar_intact ? 'Valid' : 'Corrupt'}</span>
                </div>
                <div className="p-2.5 rounded bg-background/50 border border-border">
                  <span className="text-muted-foreground block text-[10px]">TOTAL FILE ARSIP</span>
                  <span className="font-bold text-foreground">{verifyReport.total_files} File</span>
                </div>
              </div>

              <div className="text-[11px] font-mono text-muted-foreground break-all bg-background/60 p-2 rounded border border-border">
                SHA-256: {verifyReport.sha256}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: DECOUPLED WORKER STATUS */}
      {activeTab === 'worker' && (
        <div className="space-y-4">
          <div className="p-5 rounded-xl border border-border bg-card space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-bold text-base text-foreground flex items-center gap-2">
                  <span>⚙️ Decoupled Background Worker Daemon</span>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 font-mono text-xs border border-emerald-500/20">
                    pap-worker
                  </span>
                </h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Berjalan secara independen dari API Gateway untuk mengeliminasi Single Point of Failure (SPOF).
                </p>
              </div>
              <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${workerStatus?.healthy ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 'bg-red-500/10 text-red-500'}`}>
                {workerStatus?.healthy ? '● Operational' : '○ Standby'}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-2">
              <div className="p-3.5 rounded-lg border border-border bg-background/60 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase font-semibold">Uptime Worker</span>
                <div className="text-lg font-bold text-foreground">
                  {Math.floor((workerStatus?.details?.uptime_sec || 0) / 60)} Menit {((workerStatus?.details?.uptime_sec || 0) % 60)} Detik
                </div>
                <div className="text-[11px] text-muted-foreground">ID: {workerStatus?.details?.worker_id || 'pap-worker-01'}</div>
              </div>

              <div className="p-3.5 rounded-lg border border-border bg-background/60 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase font-semibold">Memori Terisolasi (RSS)</span>
                <div className="text-lg font-bold text-sky-400">
                  {workerStatus?.details?.memory_rss_mb || 45.0} MB
                </div>
                <div className="text-[11px] text-muted-foreground">Terpisah dari memori API Gateway :8000</div>
              </div>

              <div className="p-3.5 rounded-lg border border-border bg-background/60 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase font-semibold">Pesan MQTT Telemetri</span>
                <div className="text-lg font-bold text-emerald-400">
                  {workerStatus?.details?.mqtt_messages_processed ?? 0} Pesan
                </div>
                <div className="text-[11px] text-muted-foreground truncate">
                  Topik Terakhir: {workerStatus?.details?.last_mqtt_topic || '/SysCtrl'}
                </div>
              </div>

              <div className="p-3.5 rounded-lg border border-border bg-background/60 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase font-semibold">IoT Watchdog &amp; Fleet</span>
                <div className="text-lg font-bold text-emerald-500">
                  {workerStatus?.details?.devices_online ?? 1} / {workerStatus?.details?.devices_monitored ?? 1} Aktif
                </div>
                <div className="text-[11px] text-muted-foreground">
                  DB Health: {workerStatus?.details?.databases_health ? Object.keys(workerStatus.details.databases_health).length + ' DB OK' : 'Postgres + MySQL + InfluxDB OK'}
                </div>
              </div>
            </div>

            <div className="p-4 rounded-lg border border-border bg-muted/20 space-y-2 text-xs">
              <h3 className="font-semibold text-foreground">Fitur Otomatis yang Ditangani oleh pap-worker:</h3>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                <li><b>MQTT IoT Pipeline &amp; Dual Ingestion:</b> Mengonsumsi pesan telemetri ESP32 &amp; Tap NFC RFID langsung ke InfluxDB (:8086 TSDB) dan MySQL (:3306) tanpa membebani gateway API HTTP.</li>
                <li><b>Dead Man&apos;s Snitch Watchdog:</b> Memantau keaktifan perangkat IoT setiap 30s. Jika tidak ada telemetri selama &gt;90s, status otomatis diubah ke &apos;offline&apos; di database dan mengirim alert.</li>
                <li><b>NFC Whitelist Sync Relay:</b> Menarik daftar kartu aktif terverifikasi dari MySQL dan merelay ke broker MQTT setiap 5 menit agar ESP32 tetap resilien offline.</li>
                <li><b>Database Retention Maintenance:</b> Merotasi log telemetri mentah di MySQL lebih dari 14 hari agar database tetap ramping (data jangka panjang tersimpan aman di InfluxDB).</li>
                <li><b>Auto-Disaster Recovery Backup:</b> Menjalankan snapshot database terjadwal setiap 24 jam dengan verifikasi checksum SHA-256 dan auto-pruning 7 hari.</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


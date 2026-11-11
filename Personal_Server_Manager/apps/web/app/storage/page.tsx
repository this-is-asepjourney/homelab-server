'use client';

import React, { useState, useEffect } from 'react';
import {
  Database,
  Download,
  RefreshCw,
  FolderArchive,
  ShieldCheck,
  RotateCcw,
  Trash2,
  HardDrive,
  ArrowDownToLine,
  ArrowUpFromLine,
  Layers,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Copy,
  Check,
  Cloud,
  Server,
} from 'lucide-react';
import { api, formatBytes } from '../../lib/api';

export default function StoragePage() {
  const [backups, setBackups] = useState<any[]>([]);
  const [storageStats, setStorageStats] = useState<any>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);
  const [configTab, setConfigTab] = useState<'laravel' | 'node' | 'python'>('laravel');

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSnippet(id);
    setTimeout(() => setCopiedSnippet(null), 2000);
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [list, stats] = await Promise.all([
        api.getBackups().catch(() => []),
        api.getStorageTelemetry().catch(() => null),
      ]);
      setBackups(list);
      if (stats) {
        setStorageStats(stats);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      api.getStorageTelemetry().then((st) => {
        if (st) setStorageStats(st);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCreateBackup = async (backupType: string) => {
    try {
      setCreating(true);
      const dateStr = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      await api.createBackup({
        name: `${backupType}-snapshot-${dateStr}`,
        backup_type: backupType,
      });
      await loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to create backup snapshot');
    } finally {
      setCreating(false);
    }
  };

  const handleRestore = async (id: string, name: string) => {
    if (!confirm(`Restore system state from snapshot "${name}"?`)) return;
    try {
      const res = await api.restoreBackup(id);
      alert(res.message || 'Snapshot restored successfully.');
    } catch (err: any) {
      alert(err.message || 'Restore failed');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this backup snapshot?')) return;
    try {
      await api.deleteBackup(id);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Delete failed');
    }
  };

  const summary = storageStats?.summary || {
    total_bytes: 0,
    used_bytes: 0,
    free_bytes: 0,
    usage_percent: 0,
    free_percent: 100,
    read_bytes_per_sec: 0,
    write_bytes_per_sec: 0,
    total_read_bytes: 0,
    total_write_bytes: 0,
    total_read_count: 0,
    total_write_count: 0,
  };

  const partitions = storageStats?.partitions || [];
  const volumeInfo = storageStats?.volumes || { total: 0, in_use: 0, unused: 0, items: [] };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Storage & Disk I/O Center</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Real-time disk capacity (Used vs Unused), Read/Write I/O speed, partition mounts, Docker volumes & snapshots.
          </p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-border hover:bg-card text-xs font-medium text-foreground transition-all self-start"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Storage</span>
        </button>
      </div>

      {/* Real-Time Storage Capacity & Disk Read/Write Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Used vs Unused Space */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Disk Used vs Unused</span>
            <HardDrive className="w-4 h-4 text-blue-500" />
          </div>
          <div className="flex items-baseline justify-between">
            <div>
              <div className="text-2xl font-bold font-mono text-foreground">{summary.usage_percent}%</div>
              <div className="text-[11px] text-gray-400">Used: {formatBytes(summary.used_bytes)}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold font-mono text-emerald-500">{summary.free_percent}% Free</div>
              <div className="text-[11px] text-gray-400">Unused: {formatBytes(summary.free_bytes)}</div>
            </div>
          </div>
          <div className="h-2.5 w-full bg-emerald-500/20 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${Math.min(summary.usage_percent, 100)}%` }}
              title={`Used: ${formatBytes(summary.used_bytes)}`}
            ></div>
          </div>
          <div className="flex items-center justify-between text-[11px] text-gray-500 font-mono">
            <span>Total Capacity:</span>
            <span className="text-foreground font-semibold">{formatBytes(summary.total_bytes)}</span>
          </div>
        </div>

        {/* 2. Disk Read Speed & Total Read */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Disk Read (I/O)</span>
            <ArrowDownToLine className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-mono text-emerald-500">
              {formatBytes(summary.read_bytes_per_sec)}/s
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">Live Disk Read Throughput</p>
          </div>
          <div className="pt-2 border-t border-border space-y-1 text-[11px] font-mono">
            <div className="flex justify-between">
              <span className="text-gray-500">Total Read:</span>
              <span className="text-foreground">{formatBytes(summary.total_read_bytes)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Read Operations:</span>
              <span className="text-foreground">{Number(summary.total_read_count || 0).toLocaleString()} IOPS</span>
            </div>
          </div>
        </div>

        {/* 3. Disk Write Speed & Total Write */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Disk Write (I/O)</span>
            <ArrowUpFromLine className="w-4 h-4 text-amber-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-mono text-amber-500">
              {formatBytes(summary.write_bytes_per_sec)}/s
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">Live Disk Write Throughput</p>
          </div>
          <div className="pt-2 border-t border-border space-y-1 text-[11px] font-mono">
            <div className="flex justify-between">
              <span className="text-gray-500">Total Written:</span>
              <span className="text-foreground">{formatBytes(summary.total_write_bytes)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Write Operations:</span>
              <span className="text-foreground">{Number(summary.total_write_count || 0).toLocaleString()} IOPS</span>
            </div>
          </div>
        </div>

        {/* 4. Docker Volumes (In-Use vs Unused) */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Docker Volumes State</span>
            <Layers className="w-4 h-4 text-purple-500" />
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-2xl font-bold font-mono text-foreground">{volumeInfo.total}</div>
            <span className="text-xs text-gray-400">Total Volumes</span>
          </div>
          <div className="pt-2 border-t border-border space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-emerald-500 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" /> Active (In-Use)
              </span>
              <span className="font-mono font-bold text-foreground">{volumeInfo.in_use}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-amber-500 font-medium">
                <AlertCircle className="w-3.5 h-3.5" /> Unused / Dangling
              </span>
              <span className="font-mono font-bold text-foreground">{volumeInfo.unused}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Mounted Partitions & Filesystems Table (Used vs Unused + RW Mode) */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-foreground">Disk Partitions & Mountpoints</h3>
            <p className="text-xs text-gray-500">
              Detailed breakdown of Used vs Unused storage and Read/Write mount flags across host filesystems
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Device</th>
                <th className="p-3.5">Mountpoint</th>
                <th className="p-3.5">Filesystem</th>
                <th className="p-3.5">Mode (R/W)</th>
                <th className="p-3.5">Used Space</th>
                <th className="p-3.5">Unused (Free)</th>
                <th className="p-3.5">Total Size</th>
                <th className="p-3.5 w-44">Utilization</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono">
              {partitions.map((part: any, i: number) => {
                const isRw = !part.opts || part.opts.includes('rw');
                return (
                  <tr key={i} className="hover:bg-gray-500/5 transition-colors">
                    <td className="p-3.5 font-semibold text-foreground">{part.device}</td>
                    <td className="p-3.5 text-blue-500 font-bold">{part.mountpoint}</td>
                    <td className="p-3.5 text-gray-400 uppercase">{part.fstype}</td>
                    <td className="p-3.5">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          isRw
                            ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                            : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                        }`}
                      >
                        {isRw ? 'READ / WRITE' : 'READ-ONLY'}
                      </span>
                    </td>
                    <td className="p-3.5 text-foreground font-semibold">{formatBytes(part.used_bytes)}</td>
                    <td className="p-3.5 text-emerald-500 font-semibold">{formatBytes(part.free_bytes)}</td>
                    <td className="p-3.5 text-gray-400">{formatBytes(part.total_bytes)}</td>
                    <td className="p-3.5">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              part.percent > 85
                                ? 'bg-rose-500'
                                : part.percent > 70
                                ? 'bg-amber-500'
                                : 'bg-blue-500'
                            }`}
                            style={{ width: `${Math.min(part.percent, 100)}%` }}
                          ></div>
                        </div>
                        <span className="text-[11px] font-bold text-foreground w-10 text-right">
                          {part.percent}%
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Docker Volumes Breakdown (Used vs Unused) */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-foreground">Docker Volumes Inventory ({volumeInfo.total})</h3>
            <p className="text-xs text-gray-500">Shows which persistent volumes are actively mounted (In-Use) or Unused</p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Volume Name</th>
                <th className="p-3.5">Driver</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5">Host Mountpoint</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono">
              {volumeInfo.items.map((v: any) => (
                <tr key={v.id || v.name} className="hover:bg-gray-500/5 transition-colors">
                  <td className="p-3.5 font-bold text-foreground">{v.name}</td>
                  <td className="p-3.5 text-gray-400 uppercase">{v.driver}</td>
                  <td className="p-3.5">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                        v.in_use
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                      }`}
                    >
                      {v.in_use ? 'IN-USE (ACTIVE)' : 'UNUSED'}
                    </span>
                  </td>
                  <td className="p-3.5 text-gray-400 truncate max-w-md">{v.mountpoint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── MinIO S3-Compatible Object Storage ────────────────────────── */}
      <div className="rounded-xl border border-border bg-card p-6 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20">
              <Cloud className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-foreground">MinIO S3-Compatible Object Storage</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  READY (:9000 / :9002)
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Penyimpanan objek S3 berkecepatan tinggi untuk file upload project (Laravel, Node, Next.js, Python), aset statis, dan backup otomatis.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="http://192.168.25.101:9002"
              target="_blank"
              rel="noreferrer"
              className="px-3.5 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold flex items-center gap-2 shadow-sm transition-all"
            >
              <span>Buka MinIO Console</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>

        {/* 4 Info Boxes */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl bg-background border border-border space-y-1.5">
            <span className="text-[11px] font-semibold uppercase text-gray-400 tracking-wider">S3 API Endpoint</span>
            <div className="font-mono text-sm font-bold text-foreground">http://192.168.25.101:9000</div>
            <p className="text-[11px] text-gray-500">Internal Docker: <code className="text-emerald-400">http://minio:9000</code></p>
          </div>

          <div className="p-4 rounded-xl bg-background border border-border space-y-1.5">
            <span className="text-[11px] font-semibold uppercase text-gray-400 tracking-wider">Web Console</span>
            <div className="font-mono text-sm font-bold text-amber-500">http://192.168.25.101:9002</div>
            <p className="text-[11px] text-gray-500">Domain: <code className="text-amber-400">http://minio.homelab</code></p>
          </div>

          <div className="p-4 rounded-xl bg-background border border-border space-y-1.5">
            <span className="text-[11px] font-semibold uppercase text-gray-400 tracking-wider">Root Credentials</span>
            <div className="font-mono text-xs text-foreground flex items-center justify-between">
              <span>User: <strong className="text-emerald-500">admin</strong></span>
              <span>Pass: <strong className="text-emerald-500">admin12345</strong></span>
            </div>
            <p className="text-[11px] text-gray-500">Gunakan untuk membuat Access Key &amp; Buckets</p>
          </div>

          <div className="p-4 rounded-xl bg-background border border-border space-y-1.5">
            <span className="text-[11px] font-semibold uppercase text-gray-400 tracking-wider">Default Buckets</span>
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="px-1.5 py-0.5 rounded bg-card border border-border text-[10px] font-mono text-emerald-400">homelab-storage</span>
              <span className="px-1.5 py-0.5 rounded bg-card border border-border text-[10px] font-mono text-blue-400">stock-umkm</span>
              <span className="px-1.5 py-0.5 rounded bg-card border border-border text-[10px] font-mono text-purple-400">backups</span>
            </div>
            <p className="text-[11px] text-gray-500">Otomatis di-inisiarisasi saat startup</p>
          </div>
        </div>

        {/* Quick Config Snippets for Projects */}
        <div className="rounded-xl border border-border bg-background/50 p-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-2.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground">Contoh Konfigurasi .env Project:</span>
              <div className="flex items-center gap-1 bg-card p-0.5 rounded-lg border border-border text-[11px]">
                <button
                  type="button"
                  onClick={() => setConfigTab('laravel')}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    configTab === 'laravel' ? 'bg-amber-600 text-white' : 'text-gray-400 hover:text-foreground'
                  }`}
                >
                  Laravel (stock_umkm)
                </button>
                <button
                  type="button"
                  onClick={() => setConfigTab('node')}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    configTab === 'node' ? 'bg-amber-600 text-white' : 'text-gray-400 hover:text-foreground'
                  }`}
                >
                  Node.js / Next.js
                </button>
                <button
                  type="button"
                  onClick={() => setConfigTab('python')}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                    configTab === 'python' ? 'bg-amber-600 text-white' : 'text-gray-400 hover:text-foreground'
                  }`}
                >
                  Python (Boto3)
                </button>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                const snippets = {
                  laravel: `FILESYSTEM_DISK=s3\nAWS_ACCESS_KEY_ID=admin\nAWS_SECRET_ACCESS_KEY=admin12345\nAWS_DEFAULT_REGION=us-east-1\nAWS_BUCKET=stock-umkm\nAWS_USE_PATH_STYLE_ENDPOINT=true\nAWS_ENDPOINT=http://minio:9000\nAWS_URL=http://192.168.25.101:9000/stock-umkm`,
                  node: `S3_ENDPOINT=http://minio:9000\nS3_REGION=us-east-1\nS3_ACCESS_KEY_ID=admin\nS3_SECRET_ACCESS_KEY=admin12345\nS3_BUCKET=homelab-storage\nS3_FORCE_PATH_STYLE=true`,
                  python: `AWS_ACCESS_KEY_ID=admin\nAWS_SECRET_ACCESS_KEY=admin12345\nAWS_DEFAULT_REGION=us-east-1\nS3_ENDPOINT_URL=http://minio:9000\nS3_BUCKET_NAME=homelab-storage`,
                };
                handleCopy(snippets[configTab], configTab);
              }}
              className="px-2.5 py-1 rounded bg-card hover:bg-card/80 border border-border text-[11px] font-medium text-foreground flex items-center gap-1.5 self-end sm:self-auto transition-colors"
            >
              {copiedSnippet === configTab ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-emerald-500 font-semibold">Tersalin!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-gray-400" />
                  <span>Salin ke Clipboard</span>
                </>
              )}
            </button>
          </div>

          <pre className="font-mono text-xs text-emerald-400 bg-background/90 p-3 rounded-lg border border-border overflow-x-auto whitespace-pre">
            {configTab === 'laravel' && (
              `# Tambahkan ke .env project Laravel (stock_umkm)
FILESYSTEM_DISK=s3
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=admin12345
AWS_DEFAULT_REGION=us-east-1
AWS_BUCKET=stock-umkm
AWS_USE_PATH_STYLE_ENDPOINT=true
AWS_ENDPOINT=http://minio:9000
AWS_URL=http://192.168.25.101:9000/stock-umkm`
            )}
            {configTab === 'node' && (
              `# Konfigurasi S3 untuk Node.js / Next.js
S3_ENDPOINT=http://minio:9000
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=admin
S3_SECRET_ACCESS_KEY=admin12345
S3_BUCKET=homelab-storage
S3_FORCE_PATH_STYLE=true`
            )}
            {configTab === 'python' && (
              `# Konfigurasi S3 untuk Python / Boto3 / FastAPI
AWS_ACCESS_KEY_ID=admin
AWS_SECRET_ACCESS_KEY=admin12345
AWS_DEFAULT_REGION=us-east-1
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET_NAME=homelab-storage`
            )}
          </pre>
        </div>
      </div>

      {/* Snapshot Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-blue-500/10 text-blue-500">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-base text-foreground">PostgreSQL Database Snapshot</h3>
              <p className="text-xs text-gray-400">Control plane state, audit logs, and configurations</p>
            </div>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">
            Exports all servers, users, projects, encrypted credentials, and historical logs into a portable archive on the Control Plane volume.
          </p>
          <div className="flex items-center gap-2.5">
            <button
              onClick={() => handleCreateBackup('database')}
              disabled={creating}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all disabled:opacity-50"
            >
              <Download className="w-4 h-4" />
              <span>{creating ? 'Generating Snapshot...' : 'Create DB Snapshot'}</span>
            </button>
            <button
              onClick={() => handleCreateBackup('project_workspace')}
              disabled={creating}
              className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-border hover:bg-background text-foreground text-xs font-medium transition-all disabled:opacity-50"
            >
              <FolderArchive className="w-4 h-4 text-purple-500" />
              <span>Snapshot Workspaces</span>
            </button>
          </div>
        </div>

        <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-purple-500/10 text-purple-500">
              <FolderArchive className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-bold text-base text-foreground">Docker Volumes Retention</h3>
              <p className="text-xs text-gray-400">Mounted volumes on managed homelab nodes</p>
            </div>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">
            Persistent storage locations on target nodes:
            <br />• <code>/var/lib/docker/volumes/psm-postgres</code> (Database)
            <br />• <code>/opt/psm/workspaces</code> (Deployments & Releases)
          </p>
          <div className="flex items-center gap-2 text-xs text-emerald-500 font-medium">
            <ShieldCheck className="w-4 h-4" />
            <span>Encrypted at rest with host permissions</span>
          </div>
        </div>
      </div>

      {/* Backup History Table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h3 className="font-bold text-sm text-foreground">Backup Snapshots ({backups.length})</h3>
          <button
            onClick={loadData}
            className="text-xs text-blue-500 hover:underline flex items-center gap-1"
          >
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Archive Name</th>
                <th className="p-3.5">Type</th>
                <th className="p-3.5">Size</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5">Created At</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {backups.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-gray-500">
                    {loading ? 'Loading snapshots...' : 'No backup snapshots created yet.'}
                  </td>
                </tr>
              ) : (
                backups.map((b) => (
                  <tr key={b.id} className="hover:bg-gray-500/5 transition-colors">
                    <td className="p-3.5 font-mono font-semibold text-foreground">{b.name}</td>
                    <td className="p-3.5 capitalize text-gray-400">{(b.backup_type || 'database').replace('_', ' ')}</td>
                    <td className="p-3.5 font-mono text-gray-400">{formatBytes(b.size_bytes)}</td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                        {b.status}
                      </span>
                    </td>
                    <td className="p-3.5 text-gray-400">{new Date(b.created_at).toLocaleString()}</td>
                    <td className="p-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => api.downloadBackup(b.id, `${b.name}.json`)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded border border-border hover:bg-card text-foreground font-medium"
                          title="Download Snapshot File"
                        >
                          <Download className="w-3 h-3 text-emerald-500" />
                          <span>Download</span>
                        </button>
                        <button
                          onClick={() => handleRestore(b.id, b.name)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded border border-border hover:bg-blue-500/10 text-blue-500 font-medium"
                        >
                          <RotateCcw className="w-3 h-3" />
                          <span>Restore</span>
                        </button>
                        <button
                          onClick={() => handleDelete(b.id)}
                          className="p-1.5 rounded hover:bg-rose-500/10 text-rose-500"
                          title="Delete Snapshot"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

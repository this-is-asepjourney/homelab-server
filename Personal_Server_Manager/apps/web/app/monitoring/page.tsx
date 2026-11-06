'use client';

import React, { useState, useEffect } from 'react';
import {
  Activity,
  Cpu,
  HardDrive,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Settings2,
  Copy,
  Check,
  ExternalLink,
  Terminal,
} from 'lucide-react';
import { api, formatBytes } from '../../lib/api';

export default function MonitoringPage() {
  const [overview, setOverview] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [promStatus, setPromStatus] = useState<any>(null);
  const [promUrlInput, setPromUrlInput] = useState('http://host.docker.internal:9001');
  const [showPromConfig, setShowPromConfig] = useState(false);
  const [savingProm, setSavingProm] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      setLoading(true);
      const [ov, hist, pStat] = await Promise.all([
        api.getMonitoringOverview().catch(() => null),
        api.getMonitoringHistory().catch(() => []),
        api.getPrometheusStatus().catch(() => null),
      ]);
      setOverview(ov);
      setHistory(hist);
      if (pStat) {
        setPromStatus(pStat);
        if (pStat.configured_url) {
          setPromUrlInput(pStat.configured_url);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSavePrometheusUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingProm(true);
      const res = await api.updatePrometheusConfig(promUrlInput);
      if (res?.status) {
        setPromStatus(res.status);
      } else {
        await loadData();
      }
    } catch (err: any) {
      alert(err.message || 'Failed to update Prometheus configuration');
    } finally {
      setSavingProm(false);
    }
  };

  const snapCommands = `# 1. Pastikan Prometheus Snap berjalan di port 9001 (Ubuntu Host)
sudo snap install prometheus
sudo snap set prometheus web.listen-address=":9001"
sudo snap restart prometheus

# 2. Tambahkan target PSM ke konfigurasi Prometheus Snap
sudo bash -c 'cat >> /var/snap/prometheus/current/prometheus.yml <<EOF

  - job_name: "personal-server-manager"
    metrics_path: "/metrics"
    scrape_interval: 10s
    static_configs:
      - targets: ["localhost:8000"]
EOF'

# 3. Restart Prometheus Snap untuk menerapkan scrape job
sudo snap restart prometheus`;

  const handleCopyCommands = () => {
    navigator.clipboard.writeText(snapCommands);
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 2000);
  };

  const isPromConnected = Boolean(promStatus?.connected);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Monitoring Center</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Real-time telemetry, Prometheus OpenMetrics exporter & cluster health.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setShowPromConfig(!showPromConfig)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
              isPromConnected
                ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20'
                : 'bg-amber-500/10 text-amber-500 border-amber-500/20 hover:bg-amber-500/20'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isPromConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`}
            ></span>
            <span>
              {isPromConnected
                ? `Prometheus Snap Connected (${promStatus?.version || 'v2.x'})`
                : 'Prometheus Snap: Disconnected (Click to Configure)'}
            </span>
            <Settings2 className="w-3.5 h-3.5 ml-1" />
          </button>

          <button
            onClick={loadData}
            className="p-2 rounded-lg border border-border text-gray-500 hover:text-foreground hover:bg-card transition-all"
            title="Refresh Telemetry"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Prometheus Snap Connection & Integration Panel */}
      {(showPromConfig || !isPromConnected) && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
            <div className="flex items-center gap-2.5">
              {isPromConnected ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-500" />
              ) : (
                <XCircle className="w-5 h-5 text-amber-500" />
              )}
              <div>
                <h3 className="font-bold text-sm text-foreground">
                  Prometheus Snap Integration (Port 9001)
                </h3>
                <p className="text-xs text-gray-500">
                  {isPromConnected
                    ? `Connected to Prometheus at ${promStatus.url}`
                    : `Status: Not reachable (${promStatus?.error || 'Connection refused on port 9001'})`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <a
                href="/api/v1/monitoring/prometheus/metrics"
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border hover:bg-background text-blue-500 font-mono"
              >
                <span>View PSM /metrics</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 text-xs">
            {/* Left: Endpoint configuration */}
            <div className="space-y-3">
              <form onSubmit={handleSavePrometheusUrl} className="space-y-2.5">
                <label className="block font-semibold text-foreground">
                  Prometheus Server URL (Accessible from PSM API)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={promUrlInput}
                    onChange={(e) => setPromUrlInput(e.target.value)}
                    placeholder="http://host.docker.internal:9001 or http://192.168.25.101:9001"
                    className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                  />
                  <button
                    type="submit"
                    disabled={savingProm}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold disabled:opacity-50 whitespace-nowrap"
                  >
                    {savingProm ? 'Testing...' : 'Save & Test'}
                  </button>
                </div>
                <p className="text-[11px] text-gray-400">
                  Tip: Gunakan <code>http://host.docker.internal:9001</code>, IP LAN <code>http://192.168.25.101:9001</code>, atau IP Tailscale <code>http://100.106.63.90:9001</code>.
                </p>
              </form>

              {/* Active Scrape Targets */}
              {isPromConnected && Array.isArray(promStatus?.active_targets) && (
                <div className="pt-2 space-y-1.5">
                  <span className="font-semibold text-gray-400 block">
                    Active Prometheus Scrape Targets ({promStatus.active_targets.length}):
                  </span>
                  {promStatus.active_targets.length === 0 ? (
                    <div className="p-2.5 rounded bg-background border border-border text-gray-500">
                      No scrape targets configured yet.
                    </div>
                  ) : (
                    <div className="space-y-1 max-h-36 overflow-y-auto">
                      {promStatus.active_targets.map((t: any, i: number) => (
                        <div
                          key={i}
                          className="flex items-center justify-between p-2 rounded bg-background border border-border font-mono"
                        >
                          <span>
                            <strong>{t.job}</strong> ({t.instance})
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded uppercase text-[10px] font-bold ${
                              t.health === 'up'
                                ? 'bg-emerald-500/10 text-emerald-500'
                                : 'bg-rose-500/10 text-rose-500'
                            }`}
                          >
                            {t.health}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Right: Setup instructions */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-blue-500" />
                  <span>Cara Menghubungkan Prometheus Snap di Ubuntu Server:</span>
                </span>
                <button
                  onClick={handleCopyCommands}
                  className="flex items-center gap-1 px-2 py-1 rounded bg-background border border-border hover:text-blue-500 text-[11px]"
                >
                  {copiedCmd ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedCmd ? 'Copied!' : 'Copy Commands'}</span>
                </button>
              </div>
              <pre className="p-3 rounded-lg bg-slate-950 text-slate-200 font-mono text-[11px] overflow-x-auto leading-relaxed border border-slate-800">
                {snapCommands}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Cluster Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between mb-3 text-xs text-gray-400 uppercase tracking-wider font-semibold">
            <span>Cluster CPU Usage</span>
            <Cpu className="w-4 h-4 text-blue-500" />
          </div>
          <div className="text-3xl font-bold font-mono text-foreground">
            {overview?.resources?.avg_cpu_percent ?? 0}%
          </div>
          <p className="text-xs text-gray-500 mt-1">Aggregated across {overview?.servers?.online ?? 1} online node(s)</p>
          <div className="mt-4 h-2 w-full bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(overview?.resources?.avg_cpu_percent ?? 0, 100)}%` }}
            ></div>
          </div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between mb-3 text-xs text-gray-400 uppercase tracking-wider font-semibold">
            <span>Cluster RAM Usage</span>
            <Activity className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-3xl font-bold font-mono text-foreground">
            {overview?.resources?.avg_memory_percent ?? 0}%
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {overview?.resources?.memory_total_bytes
              ? `${formatBytes(overview.resources.memory_used_bytes)} / ${formatBytes(overview.resources.memory_total_bytes)} used`
              : 'Real-time host memory utilization'}
          </p>
          <div className="mt-4 h-2 w-full bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(overview?.resources?.avg_memory_percent ?? 0, 100)}%` }}
            ></div>
          </div>
        </div>

        <div className="p-5 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between mb-3 text-xs text-gray-400 uppercase tracking-wider font-semibold">
            <span>Cluster Disk Usage</span>
            <HardDrive className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-3xl font-bold font-mono text-foreground">
            {overview?.resources?.avg_disk_percent ?? 0}%
          </div>
          <p className="text-xs text-gray-500 mt-1">
            {overview?.resources?.disk_total_bytes
              ? `${formatBytes(overview.resources.disk_used_bytes)} / ${formatBytes(overview.resources.disk_total_bytes)} used`
              : 'Primary root filesystem'}
          </p>
          <div className="mt-4 h-2 w-full bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(overview?.resources?.avg_disk_percent ?? 0, 100)}%` }}
            ></div>
          </div>
        </div>
      </div>

      {/* Historical Metrics Timeline Visualizer */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-foreground">Historical Telemetry</h3>
            <p className="text-xs text-gray-500">Metric samples (past 24 hours)</p>
          </div>
          <div className="flex items-center gap-4 text-xs font-medium">
            <span className="flex items-center gap-1.5 text-blue-500">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span> CPU %
            </span>
            <span className="flex items-center gap-1.5 text-purple-500">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span> RAM %
            </span>
          </div>
        </div>

        {/* Timeline Bar visualization */}
        <div className="h-44 flex items-end gap-1.5 pt-6 pb-2 border-b border-border">
          {history.length === 0 ? (
            <div className="w-full text-center text-xs text-gray-500 self-center">
              Collecting metric data points from active agents...
            </div>
          ) : (
            history.slice(-40).map((pt, idx) => (
              <div key={idx} className="flex-1 flex flex-col justify-end items-center gap-1 group relative h-full">
                {/* Tooltip */}
                <div className="absolute -top-8 hidden group-hover:flex flex-col items-center bg-slate-900 text-white text-[10px] p-1.5 rounded shadow z-10 whitespace-nowrap">
                  <span>
                    {pt.time}: CPU {pt.cpu}% | RAM {pt.memory}%
                  </span>
                </div>
                <div
                  className="w-full bg-blue-500/80 rounded-t hover:bg-blue-400 transition-all"
                  style={{ height: `${Math.max(pt.cpu, 4)}%` }}
                ></div>
                <div
                  className="w-full bg-purple-500/80 rounded-t hover:bg-purple-400 transition-all"
                  style={{ height: `${Math.max(pt.memory, 4)}%` }}
                ></div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Active Alerts Table */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="font-bold text-sm text-foreground mb-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span>Configured Alert Rules & Status</span>
        </h3>
        <div className="space-y-2 text-xs">
          <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-background">
            <div className="flex items-center gap-2.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span className="font-medium text-foreground">High CPU Threshold (&gt; 90%)</span>
            </div>
            <span className="text-emerald-500 font-semibold uppercase text-[10px]">Active</span>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-background">
            <div className="flex items-center gap-2.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span className="font-medium text-foreground">High RAM Threshold (&gt; 90%)</span>
            </div>
            <span className="text-emerald-500 font-semibold uppercase text-[10px]">Active</span>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-background">
            <div className="flex items-center gap-2.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span className="font-medium text-foreground">Agent Heartbeat Monitor (&gt; 45s)</span>
            </div>
            <span className="text-emerald-500 font-semibold uppercase text-[10px]">Active</span>
          </div>
        </div>
      </div>
    </div>
  );
}

'use client';

import React, { useState, useEffect } from 'react';
import {
  Network,
  ArrowDownLeft,
  ArrowUpRight,
  Activity,
  ShieldCheck,
  RefreshCw,
  Wifi,
  Server,
  Globe,
  Radio,
  Search,
  CheckCircle2,
  XCircle,
  Zap,
  Layers,
} from 'lucide-react';
import { api, formatBytes } from '../../lib/api';

export default function NetworkMonitoringPage() {
  const [netData, setNetData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [portSearch, setPortSearch] = useState('');

  // Network Probe state
  const [probeTarget, setProbeTarget] = useState('1.1.1.1');
  const [probePort, setProbePort] = useState('53');
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<any>(null);

  const loadNetwork = async () => {
    try {
      setLoading(true);
      const data = await api.getNetworkTelemetry();
      if (data) {
        setNetData(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadNetwork();
    const interval = setInterval(() => {
      api.getNetworkTelemetry()
        .then((d) => {
          if (d) setNetData(d);
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleRunProbe = async (e?: React.FormEvent, customTarget?: string, customPort?: number) => {
    if (e) e.preventDefault();
    const t = customTarget ?? probeTarget;
    const p = customPort ?? (probePort ? parseInt(probePort, 10) : 80);
    if (!t) return;
    try {
      setProbing(true);
      const res = await api.probeNetworkTarget(t, p);
      setProbeResult(res);
    } catch (err: any) {
      setProbeResult({
        target: t,
        port: p,
        reachable: false,
        error: err.message || 'Probe failed',
      });
    } finally {
      setProbing(false);
    }
  };

  const bw = netData?.bandwidth || {
    rx_bytes_per_sec: 0,
    tx_bytes_per_sec: 0,
    total_rx_bytes: 0,
    total_tx_bytes: 0,
    packets_recv: 0,
    packets_sent: 0,
    err_in: 0,
    err_out: 0,
    drop_in: 0,
    drop_out: 0,
  };

  const connStats = netData?.connection_stats || {
    established: 0,
    listen: 0,
    time_wait: 0,
    close_wait: 0,
    total: 0,
  };

  const interfaces = netData?.interfaces || [];
  const listeningPorts = netData?.listening_ports || [];
  const dockerNetworks = netData?.docker_networks || [];
  const history = netData?.history || [];

  const filteredPorts = listeningPorts.filter(
    (p: any) =>
      !portSearch ||
      String(p.port).includes(portSearch) ||
      (p.service || '').toLowerCase().includes(portSearch.toLowerCase()) ||
      (p.bind_address || '').includes(portSearch)
  );

  const totalErrors = (bw.err_in || 0) + (bw.err_out || 0) + (bw.drop_in || 0) + (bw.drop_out || 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Network Monitoring Center</h1>
            <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-xs font-semibold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Live Telemetry
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Real-time RX/TX bandwidth, network interfaces (LAN, Tailscale, Docker), active listening ports & latency diagnostics.
          </p>
        </div>
        <button
          onClick={loadNetwork}
          className="flex items-center gap-2 px-3.5 py-2 rounded-lg border border-border hover:bg-card text-xs font-medium text-foreground transition-all self-start"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Network</span>
        </button>
      </div>

      {/* Top 4 Network KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Inbound Bandwidth (RX) */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Inbound Traffic (RX)</span>
            <ArrowDownLeft className="w-4 h-4 text-emerald-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-mono text-emerald-500">
              {formatBytes(bw.rx_bytes_per_sec)}/s
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">Real-Time Download Rate</p>
          </div>
          <div className="pt-2 border-t border-border space-y-1 text-[11px] font-mono">
            <div className="flex justify-between">
              <span className="text-gray-500">Total Received:</span>
              <span className="text-foreground font-semibold">{formatBytes(bw.total_rx_bytes)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">RX Packets:</span>
              <span className="text-foreground">{Number(bw.packets_recv || 0).toLocaleString()} pkts</span>
            </div>
          </div>
        </div>

        {/* 2. Outbound Bandwidth (TX) */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Outbound Traffic (TX)</span>
            <ArrowUpRight className="w-4 h-4 text-blue-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-mono text-blue-500">
              {formatBytes(bw.tx_bytes_per_sec)}/s
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">Real-Time Upload Rate</p>
          </div>
          <div className="pt-2 border-t border-border space-y-1 text-[11px] font-mono">
            <div className="flex justify-between">
              <span className="text-gray-500">Total Sent:</span>
              <span className="text-foreground font-semibold">{formatBytes(bw.total_tx_bytes)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">TX Packets:</span>
              <span className="text-foreground">{Number(bw.packets_sent || 0).toLocaleString()} pkts</span>
            </div>
          </div>
        </div>

        {/* 3. Active Socket Connections */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Socket Connections</span>
            <Activity className="w-4 h-4 text-purple-500" />
          </div>
          <div className="flex items-baseline gap-2.5">
            <div className="text-2xl font-bold font-mono text-foreground">{connStats.established}</div>
            <span className="text-xs text-emerald-500 font-medium">Established</span>
          </div>
          <div className="pt-2 border-t border-border grid grid-cols-3 gap-2 text-[11px] font-mono">
            <div>
              <span className="text-gray-500 block text-[10px]">LISTEN</span>
              <span className="text-foreground font-bold">{connStats.listen}</span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">TIME_WAIT</span>
              <span className="text-amber-500 font-bold">{connStats.time_wait}</span>
            </div>
            <div>
              <span className="text-gray-500 block text-[10px]">TOTAL</span>
              <span className="text-foreground font-bold">{connStats.total}</span>
            </div>
          </div>
        </div>

        {/* 4. Packet Integrity & Error Rate */}
        <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs text-gray-400 font-semibold uppercase">
            <span>Packet Integrity</span>
            <ShieldCheck className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="flex items-center gap-2">
            <div className="text-2xl font-bold font-mono text-foreground">
              {totalErrors === 0 ? '100%' : `${totalErrors} err`}
            </div>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500">
              Clean Link
            </span>
          </div>
          <div className="pt-2 border-t border-border space-y-1 text-[11px] font-mono">
            <div className="flex justify-between">
              <span className="text-gray-500">Errors (In / Out):</span>
              <span className="text-foreground">
                {bw.err_in} / {bw.err_out}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Dropped (In / Out):</span>
              <span className="text-foreground">
                {bw.drop_in} / {bw.drop_out}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bandwidth History Visualizer & Network Latency Probe */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Bandwidth Chart (2 cols) */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-foreground">Real-Time Bandwidth Throughput</h3>
              <p className="text-xs text-gray-500">Inbound (RX) vs Outbound (TX) traffic samples</p>
            </div>
            <div className="flex items-center gap-4 text-xs font-medium">
              <span className="flex items-center gap-1.5 text-emerald-500">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> RX (Download)
              </span>
              <span className="flex items-center gap-1.5 text-blue-500">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span> TX (Upload)
              </span>
            </div>
          </div>

          <div className="h-44 flex items-end gap-1.5 pt-6 pb-2 border-b border-border">
            {history.length === 0 ? (
              <div className="w-full text-center text-xs text-gray-500 self-center">
                Collecting live network throughput samples...
              </div>
            ) : (
              (() => {
                const maxVal = Math.max(
                  ...history.map((h: any) => Math.max(h.rx_bytes_per_sec || 0, h.tx_bytes_per_sec || 0)),
                  1024
                );
                return history.map((pt: any, idx: number) => {
                  const rxPct = Math.min(100, Math.max(6, Math.round(((pt.rx_bytes_per_sec || 0) / maxVal) * 100)));
                  const txPct = Math.min(100, Math.max(6, Math.round(((pt.tx_bytes_per_sec || 0) / maxVal) * 100)));
                  return (
                    <div key={idx} className="flex-1 flex flex-col justify-end items-center gap-1 group relative h-full">
                      <div className="absolute -top-9 hidden group-hover:flex flex-col items-center bg-slate-900 text-white text-[10px] p-1.5 rounded shadow z-10 whitespace-nowrap font-mono">
                        <span>
                          {pt.time} | RX: {formatBytes(pt.rx_bytes_per_sec)}/s | TX: {formatBytes(pt.tx_bytes_per_sec)}/s
                        </span>
                      </div>
                      <div
                        className="w-full bg-emerald-500/80 rounded-t hover:bg-emerald-400 transition-all"
                        style={{ height: `${rxPct}%` }}
                      ></div>
                      <div
                        className="w-full bg-blue-500/80 rounded-t hover:bg-blue-400 transition-all"
                        style={{ height: `${txPct}%` }}
                      ></div>
                    </div>
                  );
                });
              })()
            )}
          </div>
        </div>

        {/* Network Connectivity & Latency Probe (1 col) */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-500" />
            <div>
              <h3 className="font-bold text-sm text-foreground">Latency & Port Probe</h3>
              <p className="text-xs text-gray-500">Test outbound connectivity & TCP latency from server</p>
            </div>
          </div>

          <form onSubmit={(e) => handleRunProbe(e)} className="space-y-3 text-xs">
            <div className="flex gap-2">
              <input
                type="text"
                value={probeTarget}
                onChange={(e) => setProbeTarget(e.target.value)}
                placeholder="Host / IP (e.g. 1.1.1.1)"
                className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono"
              />
              <input
                type="number"
                value={probePort}
                onChange={(e) => setProbePort(e.target.value)}
                placeholder="Port"
                className="w-20 px-2.5 py-2 rounded-lg bg-background border border-border text-foreground font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={probing}
              className="w-full py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-all disabled:opacity-50"
            >
              {probing ? 'Probing Target...' : 'Run Connectivity Probe'}
            </button>
          </form>

          {/* Quick Presets */}
          <div className="space-y-1.5">
            <span className="text-[10px] text-gray-400 uppercase font-semibold">Quick Targets:</span>
            <div className="flex flex-wrap gap-1.5 text-[11px] font-mono">
              {[
                { label: 'Cloudflare DNS', host: '1.1.1.1', port: 53 },
                { label: 'Google DNS', host: '8.8.8.8', port: 53 },
                { label: 'GitHub HTTPS', host: 'github.com', port: 443 },
                { label: 'Prometheus :9001', host: 'host.docker.internal', port: 9001 },
              ].map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => {
                    setProbeTarget(preset.host);
                    setProbePort(String(preset.port));
                    handleRunProbe(undefined, preset.host, preset.port);
                  }}
                  className="px-2 py-1 rounded border border-border bg-background hover:border-blue-500 text-gray-300 transition-colors"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {probeResult && (
            <div
              className={`p-3 rounded-lg border text-xs font-mono space-y-1 ${
                probeResult.reachable
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                  : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
              }`}
            >
              <div className="flex items-center justify-between font-bold">
                <span className="flex items-center gap-1.5">
                  {probeResult.reachable ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  {probeResult.target}:{probeResult.port}
                </span>
                <span>{probeResult.latency_ms} ms</span>
              </div>
              {probeResult.resolved_ip && (
                <div className="text-[11px] text-gray-400">Resolved IP: {probeResult.resolved_ip}</div>
              )}
              {probeResult.error && (
                <div className="text-[11px] text-rose-400 break-all">{probeResult.error}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Network Interfaces Table (LAN, Tailscale, Docker, Loopback) */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wifi className="w-4 h-4 text-blue-500" />
            <div>
              <h3 className="font-bold text-sm text-foreground">
                Host Network Interfaces ({interfaces.length})
              </h3>
              <p className="text-xs text-gray-500">
                Physical NICs, Tailscale VPN tunnel, Docker bridges, IPv4/IPv6 addresses, and per-interface traffic
              </p>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Interface</th>
                <th className="p-3.5">Type</th>
                <th className="p-3.5">State</th>
                <th className="p-3.5">IPv4 Address</th>
                <th className="p-3.5">MAC / IPv6</th>
                <th className="p-3.5">MTU / Speed</th>
                <th className="p-3.5">Total RX</th>
                <th className="p-3.5">Total TX</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-mono">
              {interfaces.length === 0 ? (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-gray-500">
                    Loading network interfaces...
                  </td>
                </tr>
              ) : (
                interfaces.map((iface: any) => (
                  <tr key={iface.name} className="hover:bg-gray-500/5 transition-colors">
                    <td className="p-3.5 font-bold text-foreground">{iface.name}</td>
                    <td className="p-3.5">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                          iface.type === 'vpn'
                            ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                            : iface.type === 'docker'
                            ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                            : iface.type === 'loopback'
                            ? 'bg-gray-500/10 text-gray-400'
                            : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        }`}
                      >
                        {iface.type}
                      </span>
                    </td>
                    <td className="p-3.5">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                          iface.is_up
                            ? 'bg-emerald-500/10 text-emerald-500'
                            : 'bg-rose-500/10 text-rose-500'
                        }`}
                      >
                        {iface.is_up ? 'UP' : 'DOWN'}
                      </span>
                    </td>
                    <td className="p-3.5 text-blue-500 font-bold">
                      {iface.ipv4 || '-'}
                      {iface.netmask && (
                        <span className="text-gray-500 font-normal text-[10px] block">
                          Mask: {iface.netmask}
                        </span>
                      )}
                    </td>
                    <td className="p-3.5 text-gray-400 text-[11px]">
                      <div>{iface.mac || '-'}</div>
                      {iface.ipv6 && <div className="text-[10px] text-gray-500 truncate max-w-[160px]">{iface.ipv6}</div>}
                    </td>
                    <td className="p-3.5 text-gray-400">
                      MTU {iface.mtu}
                      {iface.speed_mbps > 0 && (
                        <span className="block text-[10px] text-emerald-500">{iface.speed_mbps} Mbps</span>
                      )}
                    </td>
                    <td className="p-3.5 text-emerald-500 font-semibold">{formatBytes(iface.rx_bytes)}</td>
                    <td className="p-3.5 text-blue-400 font-semibold">{formatBytes(iface.tx_bytes)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Active Listening Ports & Socket Services */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 rounded-xl border border-border bg-card overflow-hidden shadow-sm">
          <div className="p-4 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-emerald-500" />
              <div>
                <h3 className="font-bold text-sm text-foreground">
                  Active Listening Ports ({filteredPorts.length})
                </h3>
                <p className="text-xs text-gray-500">
                  Open TCP/UDP ports currently bound and accepting connections
                </p>
              </div>
            </div>

            <div className="relative w-full sm:w-56">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Filter port or service..."
                value={portSearch}
                onChange={(e) => setPortSearch(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-background border border-border text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-left text-xs">
              <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border sticky top-0">
                <tr>
                  <th className="p-3.5">Port</th>
                  <th className="p-3.5">Protocol</th>
                  <th className="p-3.5">Bind Address</th>
                  <th className="p-3.5">Service / Process</th>
                  <th className="p-3.5">State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono">
                {filteredPorts.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-6 text-center text-gray-500">
                      No matching listening ports found.
                    </td>
                  </tr>
                ) : (
                  filteredPorts.map((p: any, i: number) => (
                    <tr key={i} className="hover:bg-gray-500/5 transition-colors">
                      <td className="p-3.5 font-bold text-blue-500">:{p.port}</td>
                      <td className="p-3.5 text-gray-400">{p.protocol}</td>
                      <td className="p-3.5 text-foreground">{p.bind_address}</td>
                      <td className="p-3.5 font-sans font-medium text-foreground">{p.service}</td>
                      <td className="p-3.5">
                        <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500 text-[10px] font-bold">
                          {p.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Docker Networks Card */}
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-500" />
            <div>
              <h3 className="font-bold text-sm text-foreground">Docker Networks</h3>
              <p className="text-xs text-gray-500">Container virtual bridge & host networks</p>
            </div>
          </div>

          <div className="space-y-2.5 text-xs font-mono">
            {dockerNetworks.map((dn: any) => (
              <div
                key={dn.id || dn.name}
                className="flex items-center justify-between p-3 rounded-lg border border-border bg-background"
              >
                <div>
                  <span className="font-bold text-foreground block">{dn.name}</span>
                  <span className="text-[10px] text-gray-500 uppercase">Scope: {dn.scope || 'local'}</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px] font-bold uppercase border border-blue-500/20">
                  {dn.driver}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


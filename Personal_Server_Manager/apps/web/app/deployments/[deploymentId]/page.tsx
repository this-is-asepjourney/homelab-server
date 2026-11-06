'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  RotateCcw,
  Square,
  Terminal,
  Copy,
  Check,
  FolderGit2,
  Globe,
} from 'lucide-react';
import { api, formatDuration, getWsBase } from '../../../lib/api';

export default function DeploymentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const deploymentId = params.deploymentId as string;

  const [deployment, setDeployment] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const loadData = async () => {
    try {
      const [d, l] = await Promise.all([
        api.getDeployment(deploymentId),
        api.getDeploymentLogs(deploymentId),
      ]);
      setDeployment(d);
      setLogs(l);
    } catch (_) {}
  };

  useEffect(() => {
    loadData();

    // WebSocket connection for live log streaming (LAN-aware)
    const wsBase = getWsBase();
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(`${wsBase}/ws/deployments/${deploymentId}/logs`);
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLogs((prev) => [...prev, data]);
        } catch (_) {}
      };
    } catch (_) {}

    // Polling interval if websocket is inactive or pending
    const interval = setInterval(loadData, 3000);

    return () => {
      if (ws) ws.close();
      clearInterval(interval);
    };
  }, [deploymentId]);

  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const copyLogs = () => {
    const text = logs.map((l) => `[${l.level?.toUpperCase()}] ${l.message}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRollback = async () => {
    if (!confirm('Rollback to this release?')) return;
    try {
      const dep = await api.rollbackDeployment(deploymentId);
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'Rollback failed');
    }
  };

  const handleCancel = async () => {
    if (!confirm('Cancel this deployment?')) return;
    try {
      await api.cancelDeployment(deploymentId);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to cancel deployment');
    }
  };

  const isRunning = ['queued', 'preparing', 'building', 'deploying'].includes(deployment?.status);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push('/deployments')}
            className="p-2 rounded-lg border border-border hover:bg-card text-gray-400 hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl font-bold text-foreground">
                Release v{deployment?.version || '...'} • {deployment?.project_name}
              </h1>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                  deployment?.status === 'success'
                    ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                    : deployment?.status === 'failed' || deployment?.status === 'cancelled'
                    ? 'bg-rose-500/10 text-rose-500'
                    : 'bg-amber-500/10 text-amber-500 animate-pulse'
                }`}
              >
                {deployment?.status}
              </span>
            </div>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              Image Tag: {deployment?.image_tag || 'Generating...'} • Duration: {formatDuration(deployment?.duration_seconds || 0)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {deployment?.project_id && (
            <Link
              href={`/projects/${deployment.project_id}`}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-card text-foreground text-xs font-medium transition-colors"
            >
              <FolderGit2 className="w-3.5 h-3.5 text-blue-500" />
              <span>Project</span>
            </Link>
          )}
          {isRunning && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rose-500/30 text-xs font-medium text-rose-500 hover:bg-rose-500/10 transition-colors"
            >
              <Square className="w-3.5 h-3.5" />
              <span>Cancel Deployment</span>
            </button>
          )}
          {deployment?.status === 'success' && (
            <button
              onClick={handleRollback}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-amber-500 hover:bg-amber-500/10 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Rollback to this Release</span>
            </button>
          )}
        </div>
      </div>

      {/* Real-time Console */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 shadow-2xl overflow-hidden font-mono text-xs">
        {/* Console Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800 text-slate-400">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-slate-200">Live Build & Deployment Stream</span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-blue-500"
              />
              <span className="text-slate-400">Auto-scroll</span>
            </label>

            <button
              onClick={copyLogs}
              className="flex items-center gap-1 text-slate-400 hover:text-slate-200 transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        </div>

        {/* Console Body */}
        <div className="p-4 h-[480px] overflow-y-auto space-y-1 text-slate-300">
          {logs.length === 0 ? (
            <div className="text-slate-500 italic py-4">Connecting to build worker stream...</div>
          ) : (
            logs.map((log, index) => {
              const isErr = log.level === 'error';
              const isWarn = log.level === 'warning';
              return (
                <div key={index} className="flex items-start gap-3 hover:bg-slate-900/40 py-0.5 rounded px-1">
                  <span className="text-slate-600 select-none w-8 text-right shrink-0">
                    {index + 1}
                  </span>
                  <span
                    className={`font-semibold shrink-0 uppercase text-[10px] px-1 rounded ${
                      isErr
                        ? 'bg-rose-500/20 text-rose-400'
                        : isWarn
                        ? 'bg-amber-500/20 text-amber-400'
                        : 'text-slate-500'
                    }`}
                  >
                    {log.level || 'info'}
                  </span>
                  <span className={`break-all ${isErr ? 'text-rose-300' : isWarn ? 'text-amber-200' : 'text-slate-200'}`}>
                    {log.message}
                  </span>
                </div>
              );
            })
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}

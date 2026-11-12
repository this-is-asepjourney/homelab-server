'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
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
  Database,
  FileCode2,
  Cpu,
  Server,
  CheckCircle2,
  XCircle,
  Loader2,
  ExternalLink,
  Search,
  Filter,
  Clock,
  Sparkles,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { api, formatDuration, getWsBase } from '../../../lib/api';
import { DeployProjectModal } from '../../../components/deploy-project-modal';

interface PipelineStage {
  id: number;
  key: string;
  label: string;
  subtitle: string;
  icon: any;
}

const STAGES: PipelineStage[] = [
  { id: 1, key: 'source', label: 'Source Prep', subtitle: 'Git / ZIP source code', icon: FolderGit2 },
  { id: 2, key: 'env_db', label: 'Env & Database', subtitle: 'Auto-wiring & secrets', icon: Database },
  { id: 3, key: 'dockerfile', label: 'Dockerfile Guard', subtitle: 'Docker context & ignore', icon: FileCode2 },
  { id: 4, key: 'build', label: 'Docker Build', subtitle: 'Layers & dependencies', icon: Cpu },
  { id: 5, key: 'runtime', label: 'Container Active', subtitle: 'Network & healthcheck', icon: Server },
];

export default function DeploymentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const deploymentId = params.deploymentId as string;

  const [deployment, setDeployment] = useState<any>(null);
  const [project, setProject] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'warning' | 'error'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Edit & Redeploy state
  const [servers, setServers] = useState<any[]>([]);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [redeploying, setRedeploying] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);

  const loadData = async () => {
    try {
      const [d, l, s] = await Promise.all([
        api.getDeployment(deploymentId),
        api.getDeploymentLogs(deploymentId),
        api.getServers().catch(() => []),
      ]);
      setDeployment(d);
      setLogs(l || []);
      setServers(s || []);

      if (d?.project_id && !project) {
        try {
          const p = await api.getProject(d.project_id);
          setProject(p);
        } catch (_) {}
      }
    } catch (_) {}
  };

  const handleRedeploy = async () => {
    if (!deployment?.project_id) return;
    try {
      setRedeploying(true);
      const dep = await api.redeployProject(deployment.project_id);
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'Gagal memicu deploy ulang project ke server');
    } finally {
      setRedeploying(false);
    }
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
    const interval = setInterval(loadData, 2500);

    return () => {
      if (ws) ws.close();
      clearInterval(interval);
    };
  }, [deploymentId]);

  const isRunning = useMemo(() => {
    return ['queued', 'preparing', 'building', 'deploying'].includes(deployment?.status);
  }, [deployment?.status]);

  // Live timer for elapsed time
  useEffect(() => {
    if (!isRunning) {
      if (deployment?.duration_seconds) {
        setElapsedSeconds(deployment.duration_seconds);
      }
      return;
    }

    const startTime = deployment?.created_at ? new Date(deployment.created_at).getTime() : Date.now();
    const updateElapsed = () => {
      const now = Date.now();
      const sec = Math.max(0, Math.floor((now - startTime) / 1000));
      setElapsedSeconds(sec);
    };

    updateElapsed();
    const timer = setInterval(updateElapsed, 1000);
    return () => clearInterval(timer);
  }, [isRunning, deployment?.created_at, deployment?.duration_seconds]);

  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Derive pipeline stage progress from deployment state and logs
  const pipelineInfo = useMemo<{
    activeStage: number;
    stageStatuses: Record<number, 'completed' | 'active' | 'pending' | 'failed'>;
    progressPercent: number;
    latestActivity: string;
  }>(() => {
    if (!deployment) {
      return {
        activeStage: 1,
        stageStatuses: { 1: 'pending', 2: 'pending', 3: 'pending', 4: 'pending', 5: 'pending' },
        progressPercent: 5,
        latestActivity: 'Inisialisasi pipeline deployment...',
      };
    }

    const isSuccess = deployment.status === 'success';
    const isFailed = deployment.status === 'failed' || deployment.status === 'cancelled';

    let activeStage = 1;
    let dockerStepBonus = 0;
    let latestActivity = 'Menyiapkan proses deployment...';

    if (logs && logs.length > 0) {
      for (let i = logs.length - 1; i >= 0; i--) {
        const msg = logs[i]?.message?.trim();
        if (msg) {
          latestActivity = msg;
          break;
        }
      }

      for (const log of logs) {
        const msg = log?.message || '';
        if (msg.includes('[STAGE:1/5]')) activeStage = Math.max(activeStage, 1);
        else if (msg.includes('[STAGE:2/5]')) activeStage = Math.max(activeStage, 2);
        else if (msg.includes('[STAGE:3/5]')) activeStage = Math.max(activeStage, 3);
        else if (msg.includes('[STAGE:4/5]')) activeStage = Math.max(activeStage, 4);
        else if (msg.includes('[STAGE:5/5]')) activeStage = Math.max(activeStage, 5);
        else if (msg.includes('[STAGE:DONE]')) activeStage = 6;

        // Extract Step X/Y for Docker building interpolation
        const stepMatch = msg.match(/(?:Step|#\d+)\s+([0-9]+)\/([0-9]+)/i);
        if (stepMatch) {
          const cur = parseInt(stepMatch[1], 10);
          const total = parseInt(stepMatch[2], 10);
          if (total > 0) {
            dockerStepBonus = Math.min(Math.round((cur / total) * 35), 35);
          }
        }
      }

      // Fallbacks if logs don't have explicit stage tags
      if (activeStage === 1) {
        for (const log of logs) {
          const msg = (log?.message || '').toLowerCase();
          if (msg.includes('running container') || msg.includes('launched and operational') || msg.includes('container is now running')) {
            activeStage = 5;
          } else if (msg.includes('step ') || msg.includes('building image') || msg.includes('docker build')) {
            activeStage = Math.max(activeStage, 4);
          } else if (msg.includes('dockerfile') || msg.includes('.dockerignore')) {
            activeStage = Math.max(activeStage, 3);
          } else if (msg.includes('postgres') || msg.includes('mysql') || msg.includes('environment')) {
            activeStage = Math.max(activeStage, 2);
          }
        }
      }
    }

    if (isSuccess) activeStage = 6;

    const stageStatuses: Record<number, 'completed' | 'active' | 'pending' | 'failed'> = {};
    for (let i = 1; i <= 5; i++) {
      if (isSuccess) {
        stageStatuses[i] = 'completed';
      } else if (isFailed) {
        if (i < activeStage) stageStatuses[i] = 'completed';
        else if (i === activeStage) stageStatuses[i] = 'failed';
        else stageStatuses[i] = 'pending';
      } else {
        if (i < activeStage) stageStatuses[i] = 'completed';
        else if (i === activeStage) stageStatuses[i] = 'active';
        else stageStatuses[i] = 'pending';
      }
    }

    let progressPercent = 0;
    if (isSuccess) {
      progressPercent = 100;
    } else if (isFailed) {
      progressPercent = activeStage === 1 ? 15 : activeStage === 2 ? 30 : activeStage === 3 ? 45 : activeStage === 4 ? 65 : 90;
    } else {
      switch (activeStage) {
        case 1:
          progressPercent = 15;
          break;
        case 2:
          progressPercent = 30;
          break;
        case 3:
          progressPercent = 45;
          break;
        case 4:
          progressPercent = 50 + dockerStepBonus;
          break;
        case 5:
          progressPercent = 90;
          break;
        default:
          progressPercent = 8;
          break;
      }
    }

    return { activeStage, stageStatuses, progressPercent, latestActivity };
  }, [deployment, logs]);

  const copyLogs = () => {
    const text = logs.map((l) => `[${(l.level || 'info').toUpperCase()}] ${l.message}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRollback = async () => {
    if (!confirm('Rollback ke release ini? Container sebelumnya akan digantikan dengan image rilis ini.')) return;
    try {
      const dep = await api.rollbackDeployment(deploymentId);
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'Rollback gagal');
    }
  };

  const handleCancel = async () => {
    if (!confirm('Batalkan proses deployment ini?')) return;
    try {
      await api.cancelDeployment(deploymentId);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Gagal membatalkan deployment');
    }
  };

  // Filter logs
  const filteredLogs = useMemo(() => {
    return logs.filter((l) => {
      if (logFilter !== 'all' && l.level !== logFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (l.message || '').toLowerCase().includes(q) || (l.level || '').toLowerCase().includes(q);
      }
      return true;
    });
  }, [logs, logFilter, searchQuery]);

  // Extract application endpoint URL
  const appEndpoint = useMemo(() => {
    const hostIp = typeof window !== 'undefined' ? window.location.hostname : '192.168.25.101';
    if (project?.domain && !project.domain.includes('homelab')) {
      return `http://${project.domain}`;
    }
    const mapping = deployment?.port_mappings || project?.port_mappings;
    if (mapping) {
      const firstPair = mapping.split(',')[0].trim();
      const hostPort = firstPair.split(':')[0].trim();
      if (hostPort && !isNaN(Number(hostPort))) {
        return `http://${hostIp}:${hostPort}`;
      }
    }
    if (project?.domain) {
      return `http://${project.domain}`;
    }
    return null;
  }, [project, deployment]);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push(deployment?.project_id ? `/projects/${deployment.project_id}` : '/deployments')}
            className="p-2 rounded-xl border border-border hover:bg-card text-gray-400 hover:text-foreground transition-all shadow-sm"
            title="Kembali"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-bold text-foreground">
                Release v{deployment?.version || '1'} • {deployment?.project_name || 'Project'}
              </h1>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                  deployment?.status === 'success'
                    ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                    : deployment?.status === 'failed' || deployment?.status === 'cancelled'
                    ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                    : 'bg-amber-500/15 text-amber-500 border border-amber-500/30 animate-pulse'
                }`}
              >
                {isRunning && <Loader2 className="w-3 h-3 animate-spin" />}
                {deployment?.status === 'success' && <CheckCircle2 className="w-3 h-3" />}
                {deployment?.status === 'failed' && <XCircle className="w-3 h-3" />}
                {deployment?.status || 'Loading...'}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-400 font-mono mt-1 flex-wrap">
              <span>Image: <strong className="text-foreground">{deployment?.image_tag || 'Generating...'}</strong></span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5 text-blue-400" />
                Durasi: <strong className="text-foreground">{formatDuration(elapsedSeconds)}</strong>
              </span>
              {deployment?.created_at && (
                <>
                  <span>•</span>
                  <span>Dimulai: {new Date(deployment.created_at).toLocaleTimeString()}</span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {appEndpoint && deployment?.status === 'success' && (
            <a
              href={appEndpoint}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md shadow-emerald-600/20"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Buka Aplikasi</span>
            </a>
          )}

          {deployment?.project_id && (
            <Link
              href={`/projects/${deployment.project_id}`}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border hover:bg-card text-foreground text-xs font-medium transition-colors"
            >
              <FolderGit2 className="w-3.5 h-3.5 text-blue-500" />
              <span>Project Hub</span>
            </Link>
          )}

          {isRunning && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-rose-500/30 text-xs font-medium text-rose-500 hover:bg-rose-500/10 transition-colors"
            >
              <Square className="w-3.5 h-3.5" />
              <span>Hentikan</span>
            </button>
          )}

          {/* Edit & Deploy Ulang */}
          {project && (
            <button
              onClick={() => setEditModalOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 text-blue-500 text-xs font-semibold transition-all shadow-sm"
              title="Sesuaikan konfigurasi branch, port, database, atau .env lalu deploy ulang"
            >
              <FileCode2 className="w-3.5 h-3.5" />
              <span>Edit &amp; Deploy Ulang</span>
            </button>
          )}

          {/* Quick Redeploy Button */}
          {project && !isRunning && (
            <button
              onClick={handleRedeploy}
              disabled={redeploying}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-md shadow-blue-600/20 disabled:opacity-50"
              title="Deploy ulang project langsung dengan konfigurasi aktif"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${redeploying ? 'animate-spin' : ''}`} />
              <span>{redeploying ? 'Deploying...' : 'Deploy Ulang'}</span>
            </button>
          )}

          {deployment?.status === 'success' && (
            <button
              onClick={handleRollback}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border text-xs font-medium text-amber-500 hover:bg-amber-500/10 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Rollback Rilis</span>
            </button>
          )}
        </div>
      </div>

      {/* Visual Multi-Stage Pipeline Stepper & Progress Card */}
      <div className="rounded-2xl border border-border bg-card p-5 shadow-lg space-y-4">
        {/* Progress Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className={`p-2 rounded-xl ${
              deployment?.status === 'success'
                ? 'bg-emerald-500/10 text-emerald-500'
                : deployment?.status === 'failed'
                ? 'bg-rose-500/10 text-rose-500'
                : 'bg-blue-500/10 text-blue-500'
            }`}>
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">
                Pipeline Deployment Tracker
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {deployment?.status === 'success'
                  ? 'Seluruh tahapan pipeline deployment berhasil diselesaikan.'
                  : deployment?.status === 'failed'
                  ? 'Deployment terhenti karena kesalahan pada salah satu tahapan.'
                  : 'Memantau tahapan build & eksekusi container secara real-time.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono font-bold text-foreground">
              {pipelineInfo.progressPercent}% Selesai
            </span>
          </div>
        </div>

        {/* Dynamic Progress Bar */}
        <div className="w-full bg-slate-800/50 rounded-full h-2.5 overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ease-out rounded-full ${
              deployment?.status === 'success'
                ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50'
                : deployment?.status === 'failed'
                ? 'bg-rose-500 shadow-sm shadow-rose-500/50'
                : 'bg-gradient-to-r from-blue-500 via-indigo-500 to-cyan-400 animate-pulse'
            }`}
            style={{ width: `${Math.max(5, pipelineInfo.progressPercent)}%` }}
          />
        </div>

        {/* Pipeline Stepper Items */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 pt-2">
          {STAGES.map((stage) => {
            const Icon = stage.icon;
            const status = pipelineInfo.stageStatuses[stage.id] || 'pending';
            const isCompleted = status === 'completed';
            const isActive = status === 'active';
            const isFailed = status === 'failed';

            return (
              <div
                key={stage.id}
                className={`p-3 rounded-xl border transition-all flex flex-col gap-1.5 ${
                  isActive
                    ? 'border-blue-500/60 bg-blue-500/10 shadow-md shadow-blue-500/10 ring-1 ring-blue-500/30'
                    : isCompleted
                    ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-500'
                    : isFailed
                    ? 'border-rose-500/50 bg-rose-500/10 text-rose-500'
                    : 'border-border/60 bg-background/40 opacity-70'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className={`p-1.5 rounded-lg ${
                    isActive
                      ? 'bg-blue-500 text-white shadow-sm'
                      : isCompleted
                      ? 'bg-emerald-500/20 text-emerald-500'
                      : isFailed
                      ? 'bg-rose-500/20 text-rose-500'
                      : 'bg-muted text-gray-400'
                  }`}>
                    <Icon className="w-3.5 h-3.5" />
                  </div>

                  {isActive && <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />}
                  {isCompleted && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                  {isFailed && <AlertTriangle className="w-4 h-4 text-rose-500" />}
                  {status === 'pending' && <span className="text-[10px] font-mono text-gray-500">Antre</span>}
                </div>

                <div>
                  <div className={`text-xs font-bold leading-tight ${
                    isActive ? 'text-blue-500 dark:text-blue-400' : isCompleted ? 'text-foreground' : isFailed ? 'text-rose-400' : 'text-gray-400'
                  }`}>
                    {stage.label}
                  </div>
                  <div className="text-[10px] text-gray-500 truncate leading-snug mt-0.5">
                    {stage.subtitle}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Live Activity Ticker */}
        {isRunning && (
          <div className="px-3 py-2 rounded-xl bg-blue-500/5 border border-blue-500/20 flex items-center gap-2.5 text-xs text-blue-400 font-mono">
            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-blue-500" />
            <span className="font-semibold shrink-0 text-blue-500">Aktivitas Terkini:</span>
            <span className="truncate text-slate-300">{pipelineInfo.latestActivity}</span>
          </div>
        )}
      </div>

      {/* Failure Callout Banner */}
      {deployment?.status === 'failed' && project && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-xl bg-rose-500/20 text-rose-400 mt-0.5">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-rose-300">
                Deployment Gagal pada Tahapan Terakhir
              </h4>
              <p className="text-xs text-rose-200/80 mt-1">
                Periksa log error di bawah. Anda dapat memperbaiki konfigurasi (port, database, env var, atau branch) lalu deploy ulang langsung ke server.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 shrink-0">
            <button
              onClick={() => setEditModalOpen(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition-all shadow-md shadow-blue-600/20"
            >
              <FileCode2 className="w-3.5 h-3.5" />
              <span>Edit &amp; Deploy Ulang</span>
            </button>
            <button
              onClick={handleRedeploy}
              disabled={redeploying}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-rose-500/40 hover:bg-rose-500/20 text-rose-200 text-xs font-semibold transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${redeploying ? 'animate-spin' : ''}`} />
              <span>Coba Deploy Ulang</span>
            </button>
          </div>
        </div>
      )}

      {/* Real-time Console */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl overflow-hidden font-mono text-xs flex flex-col">
        {/* Console Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-3 bg-slate-900 border-b border-slate-800 text-slate-400">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-blue-400" />
            <span className="font-semibold text-slate-200">Terminal Build & Deployment Log</span>
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              {logs.length} baris
            </span>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Filter buttons */}
            <div className="flex items-center rounded-lg bg-slate-800/80 p-0.5 border border-slate-700 text-[11px]">
              {(['all', 'info', 'warning', 'error'] as const).map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setLogFilter(lvl)}
                  className={`px-2 py-0.5 rounded capitalize transition-colors ${
                    logFilter === lvl ? 'bg-blue-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {lvl}
                </button>
              ))}
            </div>

            {/* Search Box */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Cari log..."
                className="pl-8 pr-3 py-1 rounded-lg bg-slate-800 border border-slate-700 text-slate-200 text-[11px] placeholder-slate-500 focus:outline-none focus:border-blue-500 w-32 sm:w-40"
              />
            </div>

            {/* Auto-scroll Checkbox */}
            <label className="flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-slate-200 select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-0"
              />
              <span className="text-[11px]">Auto-scroll</span>
            </label>

            {/* Copy Button */}
            <button
              onClick={copyLogs}
              className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors text-[11px]"
              title="Salin seluruh log"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Tersalin' : 'Salin'}</span>
            </button>
          </div>
        </div>

        {/* Console Body */}
        <div className="p-4 h-[500px] overflow-y-auto space-y-1 text-slate-300 leading-relaxed">
          {filteredLogs.length === 0 ? (
            <div className="text-slate-500 italic py-8 text-center flex flex-col items-center gap-2">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500/50" />
              <span>
                {logs.length === 0
                  ? 'Menghubungkan ke worker stream daemon...'
                  : 'Tidak ada baris log yang cocok dengan filter pencarian.'}
              </span>
            </div>
          ) : (
            filteredLogs.map((log, index) => {
              const isErr = log.level === 'error';
              const isWarn = log.level === 'warning';
              const isStage = (log.message || '').includes('[STAGE:');
              const isDockerStep = /(?:Step|#\d+)\s+[0-9]+\/[0-9]+/i.test(log.message || '');

              return (
                <div
                  key={index}
                  className={`flex items-start gap-3 hover:bg-slate-900/60 py-0.5 rounded px-2 transition-colors ${
                    isStage ? 'bg-blue-950/30 border-l-2 border-blue-500' : ''
                  }`}
                >
                  <span className="text-slate-600 select-none w-8 text-right shrink-0 font-mono text-[11px]">
                    {index + 1}
                  </span>

                  <span
                    className={`font-semibold shrink-0 uppercase text-[9px] px-1.5 py-0.5 rounded leading-none mt-0.5 ${
                      isErr
                        ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                        : isWarn
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        : isStage
                        ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30 font-bold'
                        : 'text-slate-500 bg-slate-900'
                    }`}
                  >
                    {isStage ? 'STAGE' : log.level || 'info'}
                  </span>

                  <span
                    className={`break-all ${
                      isErr
                        ? 'text-rose-300 font-medium'
                        : isWarn
                        ? 'text-amber-200'
                        : isStage
                        ? 'text-blue-300 font-semibold'
                        : isDockerStep
                        ? 'text-cyan-300 font-mono'
                        : 'text-slate-200'
                    }`}
                  >
                    {log.message}
                  </span>
                </div>
              );
            })
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Edit & Redeploy Modal */}
      {project && editModalOpen && (
        <DeployProjectModal
          isOpen={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          onSuccess={(newDepId) => {
            setEditModalOpen(false);
            if (newDepId) {
              router.push(`/deployments/${newDepId}`);
            } else {
              loadData();
            }
          }}
          servers={servers}
          existingProject={project}
        />
      )}
    </div>
  );
}

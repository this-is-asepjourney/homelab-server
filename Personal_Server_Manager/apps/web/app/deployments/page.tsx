'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Rocket,
  RefreshCw,
  Clock,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Plus,
} from 'lucide-react';
import { api, formatDuration } from '../../lib/api';
import { DeployProjectModal } from '../../components/deploy-project-modal';

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<any[]>([]);
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const loadDeployments = async () => {
    try {
      setLoading(true);
      const [list, s] = await Promise.all([
        api.getDeployments().catch(() => []),
        api.getServers().catch(() => []),
      ]);
      setDeployments(list);
      setServers(s);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDeployments();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Deployment Center</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Audit releases, view live build logs, and manage rollbacks across projects.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadDeployments}
            className="p-2 rounded-lg border border-border text-gray-500 hover:text-foreground hover:bg-card transition-all w-fit"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all"
          >
            <Rocket className="w-4 h-4" />
            <span>Deploy Project Baru</span>
          </button>
        </div>
      </div>

      {/* Deployments Table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Project</th>
                <th className="p-3.5">Release</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5">Image / Commit</th>
                <th className="p-3.5">Duration</th>
                <th className="p-3.5">Started At</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {deployments.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-gray-500">
                    No deployments recorded yet.
                  </td>
                </tr>
              ) : (
                deployments.map((d) => (
                  <tr key={d.id} className="hover:bg-gray-500/5 transition-colors">
                    <td className="p-3.5 font-semibold text-foreground">
                      <Link href={`/projects/${d.project_id}`} className="hover:text-blue-500">
                        {d.project_name}
                      </Link>
                    </td>
                    <td className="p-3.5 font-mono font-bold text-foreground">v{d.version}</td>
                    <td className="p-3.5">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                          d.status === 'success'
                            ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                            : d.status === 'failed'
                            ? 'bg-rose-500/10 text-rose-500'
                            : 'bg-amber-500/10 text-amber-500 animate-pulse'
                        }`}
                      >
                        {d.status === 'success' && <CheckCircle2 className="w-3 h-3" />}
                        {d.status === 'failed' && <XCircle className="w-3 h-3" />}
                        {d.status}
                      </span>
                    </td>
                    <td className="p-3.5 font-mono text-gray-400 truncate max-w-[150px]">
                      {d.image_tag || d.commit_hash || 'HEAD'}
                    </td>
                    <td className="p-3.5 text-gray-400 font-mono">
                      {formatDuration(d.duration_seconds || 0)}
                    </td>
                    <td className="p-3.5 text-gray-400">
                      {new Date(d.created_at).toLocaleString()}
                    </td>
                    <td className="p-3.5 text-right">
                      <Link
                        href={`/deployments/${d.id}`}
                        className="px-3 py-1.5 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 text-blue-600 dark:text-blue-400 font-medium transition-colors"
                      >
                        View Logs
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <DeployProjectModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        servers={servers}
        onSuccess={() => loadDeployments()}
      />
    </div>
  );
}


'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  FolderGit2,
  Plus,
  Rocket,
  Server,
  GitBranch,
  RefreshCw,
  Trash2,
  Upload,
  Database,
  Globe,
} from 'lucide-react';
import { api } from '../../lib/api';
import { DeployProjectModal } from '../../components/deploy-project-modal';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Deploy Modal states
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedProjectForDeploy, setSelectedProjectForDeploy] = useState<any | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [p, s] = await Promise.all([
        api.getProjects().catch(() => []),
        api.getServers().catch(() => []),
      ]);
      setProjects(p);
      setServers(s);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleOpenCreateModal = () => {
    setSelectedProjectForDeploy(null);
    setModalOpen(true);
  };

  const handleOpenDeployReleaseModal = (proj: any) => {
    setSelectedProjectForDeploy(proj);
    setModalOpen(true);
  };

  const handleDelete = async (id: string, projName: string) => {
    if (!confirm(`Hapus project "${projName}"? Semua release terkait akan dihapus.`)) return;
    try {
      await api.deleteProject(id);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Gagal menghapus project');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Project Management</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Deploy aplikasi ke Docker dengan mudah via Git atau Upload ZIP, lengkapi port mapping dan environment variables.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            className="p-2 rounded-lg border border-border text-gray-500 hover:text-foreground hover:bg-card transition-all"
            title="Refresh Data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleOpenCreateModal}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-md shadow-blue-600/20 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Deploy Project Baru</span>
          </button>
        </div>
      </div>

      {/* Projects Grid */}
      {projects.length === 0 && !loading ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center bg-card/50 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center mx-auto border border-blue-500/20">
            <Rocket className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-bold text-foreground">Belum ada project yang di-deploy</h3>
            <p className="text-xs text-gray-500 max-w-md mx-auto">
              Mulai deploy aplikasi Anda ke Docker sekarang via repository GitHub atau upload file ZIP source code.
            </p>
          </div>
          <button
            onClick={handleOpenCreateModal}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Deploy Project Pertama</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {projects.map((p) => {
            const dbSlug = (p.name || 'app')
              .toLowerCase()
              .replace(/[^a-z0-9_]/g, '_')
              .replace(/_+/g, '_')
              .replace(/^_|_$/g, '');

            return (
              <div
                key={p.id}
                className="rounded-xl border border-border bg-card p-5 shadow-sm hover:border-blue-500/40 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-xl border border-blue-500/30 bg-blue-500/10 text-blue-500">
                        <FolderGit2 className="w-5 h-5" />
                      </div>
                      <div>
                        <Link
                          href={`/projects/${p.id}`}
                          className="font-bold text-sm text-foreground hover:text-blue-500 transition-colors block"
                        >
                          {p.name}
                        </Link>
                        <span className="text-xs text-gray-400 font-mono mt-0.5 inline-block">
                          {p.framework}
                        </span>
                      </div>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                      {p.status}
                    </span>
                  </div>

                  <div className="space-y-2 text-xs text-gray-400 py-3 border-t border-border">
                    <div className="flex items-center gap-1.5">
                      <Server className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                      <span>
                        Target: <span className="text-foreground font-medium">{p.server_name}</span>
                      </span>
                    </div>

                    {/* Port Mappings Display */}
                    <div className="flex items-center gap-1.5 font-mono text-blue-500">
                      <Globe className="w-3.5 h-3.5 shrink-0" />
                      <span>Port Docker: {p.port_mappings || '3000:3000'}</span>
                    </div>

                    {/* Source */}
                    {p.repository_url ? (
                      <div className="flex items-center gap-1.5 font-mono truncate">
                        <GitBranch className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                        <span className="truncate">{p.branch || 'main'}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5">
                        <Upload className="w-3.5 h-3.5 text-gray-500 shrink-0" />
                        <span>Sumber: Upload Arsip ZIP</span>
                      </div>
                    )}

                    {/* Database */}
                    <div className="flex items-center gap-1.5 text-emerald-500 font-mono text-[11px]">
                      <Database className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">PostgreSQL: {dbSlug}</span>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleOpenDeployReleaseModal(p)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium shadow-sm transition-colors"
                      title="Deploy release baru"
                    >
                      <Rocket className="w-3 h-3" />
                      <span>Deploy</span>
                    </button>
                    <Link
                      href={`/projects/${p.id}`}
                      className="px-2.5 py-1.5 rounded-lg border border-border hover:bg-background text-gray-400 hover:text-foreground text-xs font-medium transition-colors"
                    >
                      Manage
                    </Link>
                  </div>

                  <button
                    onClick={() => handleDelete(p.id, p.name)}
                    className="p-1.5 text-gray-400 hover:text-rose-500 hover:bg-rose-500/10 rounded transition-colors"
                    title="Hapus project"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modern 4-Step Deploy Modal */}
      <DeployProjectModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        servers={servers}
        existingProject={selectedProjectForDeploy}
        onSuccess={() => loadData()}
      />
    </div>
  );
}

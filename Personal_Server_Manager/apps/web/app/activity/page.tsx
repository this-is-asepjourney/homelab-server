'use client';

import React, { useState, useEffect } from 'react';
import {
  History,
  ShieldCheck,
  Search,
  Filter,
  RefreshCw,
  Clock,
  User,
  Download,
} from 'lucide-react';
import { api } from '../../lib/api';

export default function ActivityPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const loadLogs = async () => {
    try {
      setLoading(true);
      const data = await api.getAuditLogs();
      setLogs(data);
    } catch (_) {}
    finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const filtered = logs.filter(
    (l) =>
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.resource_type.toLowerCase().includes(search.toLowerCase()) ||
      (l.user_name && l.user_name.toLowerCase().includes(search.toLowerCase()))
  );

  const handleExport = async (fmt: 'csv' | 'json') => {
    try {
      await api.exportAuditLogs(fmt);
    } catch (err: any) {
      alert(err.message || 'Export failed');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Audit & Activity Log</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Immutable audit trail of security operations, deployments, and server changes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-card text-foreground text-xs font-medium transition-colors"
            title="Export as CSV"
          >
            <Download className="w-3.5 h-3.5 text-blue-500" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => handleExport('json')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-card text-foreground text-xs font-medium transition-colors"
            title="Export as JSON"
          >
            <Download className="w-3.5 h-3.5 text-purple-500" />
            <span>Export JSON</span>
          </button>
          <button
            onClick={loadLogs}
            className="p-2 rounded-lg border border-border text-gray-500 hover:text-foreground hover:bg-card transition-all"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <div className="relative max-w-sm">
        <Search className="w-4 h-4 text-gray-400 absolute left-3 top-3" />
        <input
          type="text"
          placeholder="Filter by action, user, resource..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 rounded-lg bg-card border border-border text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Audit Log Table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
              <tr>
                <th className="p-3.5">Action</th>
                <th className="p-3.5">Resource</th>
                <th className="p-3.5">Actor</th>
                <th className="p-3.5">IP Address</th>
                <th className="p-3.5 text-right">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-8 text-center text-gray-500">
                    No activity records found matching query.
                  </td>
                </tr>
              ) : (
                filtered.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-500/5 transition-colors font-mono">
                    <td className="p-3.5 font-semibold text-foreground">
                      <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-500 text-[11px]">
                        {log.action}
                      </span>
                    </td>
                    <td className="p-3.5 capitalize text-gray-400">{log.resource_type}</td>
                    <td className="p-3.5 text-foreground flex items-center gap-1.5 font-sans">
                      <User className="w-3.5 h-3.5 text-gray-400" />
                      <span>{log.user_name || 'System'}</span>
                    </td>
                    <td className="p-3.5 text-gray-400">{log.ip_address || '127.0.0.1'}</td>
                    <td className="p-3.5 text-right text-gray-500">
                      {new Date(log.created_at).toLocaleString()}
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


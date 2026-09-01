import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Eye,
  CheckSquare,
  Languages,
  ArrowRightLeft,
  Download,
  Trash2,
  MoreVertical,
  Layers,
  FileText,
} from 'lucide-react';
import { SopRecord } from '@/types';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileTypeIcon } from '@/components/ui/FileTypeIcon';
import { getDisplayTitle, getDisplaySubline } from '@/lib/sopDisplay';
import { formatDate, formatTimeAgo } from '@/lib/format';
import { Button } from '@/components/ui/Button';

interface SopTableProps {
  sops: SopRecord[];
  onDelete: (sop: SopRecord) => void;
  onStatusChange?: (sop: SopRecord, newStatus: string) => void;
}

export const SopTable: React.FC<SopTableProps> = ({ sops, onDelete, onStatusChange }) => {
  const navigate = useNavigate();
  const [activeMenuId, setActiveMenuId] = useState<number | null>(null);

  const handleAction = (e: React.MouseEvent, action: () => void) => {
    e.stopPropagation();
    setActiveMenuId(null);
    action();
  };

  const downloadJson = (documentUid: string) => {
    window.open(`/documents/v2/${encodeURIComponent(documentUid)}/json`, '_blank');
  };

  return (
    <div className="dashboard-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr>
              <th className="table-header-cell min-w-[280px]">SOP DOCUMENT</th>
              <th className="table-header-cell w-28">TYPE</th>
              <th className="table-header-cell w-20 text-center">PAGES</th>
              <th className="table-header-cell w-32">REVIEW STATUS</th>
              <th className="table-header-cell w-28">EXTRACTION</th>
              <th className="table-header-cell w-28">VERSION</th>
              <th className="table-header-cell w-32">UPDATED</th>
              <th className="table-header-cell w-16 text-right pr-5">ACTIONS</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sops.map((sop) => {
              const title = getDisplayTitle(sop);
              const subline = getDisplaySubline(sop);
              const isMenuOpen = activeMenuId === sop.id;

              return (
                <tr
                  key={sop.id}
                  onClick={() => navigate(`/sops/${sop.id}`)}
                  className="table-row cursor-pointer group"
                >
                  {/* SOP Title & Info */}
                  <td className="table-cell">
                    <div className="flex items-start gap-3">
                      <FileTypeIcon fileType={sop.file_type} size="md" className="shrink-0 mt-0.5" />
                      <div className="min-w-0">
                        <div className="font-semibold text-text-main group-hover:text-primary transition truncate max-w-sm sm:max-w-md">
                          {title}
                        </div>
                        <div className="text-xs text-text-muted mt-0.5 truncate max-w-sm">
                          {subline}
                        </div>
                      </div>
                    </div>
                  </td>

                  {/* Document Type */}
                  <td className="table-cell">
                    <span className="text-xs text-text-muted capitalize">
                      {sop.document_type || 'Guidance'}
                    </span>
                  </td>

                  {/* Page Count */}
                  <td className="table-cell text-center font-mono text-xs">
                    {sop.page_count || 1}
                  </td>

                  {/* Review Status */}
                  <td className="table-cell">
                    <StatusBadge status={sop.status} size="sm" />
                  </td>

                  {/* Extraction State */}
                  <td className="table-cell">
                    <span className="inline-flex items-center gap-1 rounded bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                      <Layers className="size-3" /> v2 JSON
                    </span>
                  </td>

                  {/* Database Version */}
                  <td className="table-cell font-mono text-xs text-text-muted">
                    v{sop.gpdat_version || 1}
                  </td>

                  {/* Updated Timestamp */}
                  <td className="table-cell text-xs text-text-muted" title={formatDate(sop.updated_at)}>
                    {formatTimeAgo(sop.updated_at)}
                  </td>

                  {/* Actions Dropdown */}
                  <td className="table-cell text-right pr-4">
                    <div className="relative inline-block text-left">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setActiveMenuId(isMenuOpen ? null : sop.id);
                        }}
                        className="btn-icon size-8 hover:bg-white/10"
                        aria-label="Document options"
                      >
                        <MoreVertical className="size-4" />
                      </button>

                      {isMenuOpen && (
                        <>
                          <div
                            className="fixed inset-0 z-20"
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveMenuId(null);
                            }}
                          />
                          <div className="absolute right-0 top-9 z-30 w-48 rounded-lg border border-border bg-card p-1 shadow-panel">
                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => navigate(`/sops/${sop.id}`))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
                            >
                              <Eye className="size-3.5 text-primary" />
                              <span>View Content</span>
                            </button>

                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => navigate(`/review/${sop.id}?mode=review`))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
                            >
                              <CheckSquare className="size-3.5 text-amber-400" />
                              <span>Open Review</span>
                            </button>

                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => navigate(`/review/${sop.id}?mode=translation`))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
                            >
                              <Languages className="size-3.5 text-sky-400" />
                              <span>Start Translation</span>
                            </button>

                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => navigate(`/review/${sop.id}?mode=migration`))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
                            >
                              <ArrowRightLeft className="size-3.5 text-emerald-400" />
                              <span>Start Migration</span>
                            </button>

                            <div className="my-1 h-px bg-border" />

                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => downloadJson(sop.document_Uid))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
                            >
                              <Download className="size-3.5 text-text-muted" />
                              <span>Download JSON</span>
                            </button>

                            <button
                              type="button"
                              onClick={(e) => handleAction(e, () => onDelete(sop))}
                              className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-xs text-red-400 hover:bg-red-500/10 transition"
                            >
                              <Trash2 className="size-3.5 text-red-400" />
                              <span>Delete</span>
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

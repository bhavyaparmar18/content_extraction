import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { RotateCcw, Check, X, Clock, ShieldCheck, AlertCircle, FileText } from 'lucide-react';
import { api } from '@/lib/api';
import { ReprocessingRequest } from '@/types';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/format';
import { useToast } from '@/components/ui/ToastStack';

export const ReprocessingAdminPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError } = useToast();

  const [statusFilter, setStatusFilter] = useState<'all' | 'pending_approval' | 'approved' | 'rejected'>('all');
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectComment, setRejectComment] = useState('');

  // Sample data fallback if backend returns empty
  const [localRequests, setLocalRequests] = useState<ReprocessingRequest[]>([
    {
      id: 'rep_01',
      document_uid: 'BI-VQD-24416_BI-VQD-24416-G_v3.0',
      sop_record_id: 1,
      workflow_id: 'ext_01',
      status: 'pending_approval',
      requested_at: new Date(Date.now() - 3600000).toISOString(),
      requested_by: 'Reviewer (Sarah K.)',
      reason: 'Table on page 4 had merged sub-cells that split across page boundary. Requires table stitcher re-run with 15pt tolerance.',
      pages: 'all',
    },
  ]);

  const { data: serverRequests = [] } = useQuery({
    queryKey: ['reprocessingRequests'],
    queryFn: () => api.getReprocessingRequests(),
  });

  const requests = serverRequests.length > 0 ? serverRequests : localRequests;

  const handleApprove = (reqId: string) => {
    setLocalRequests((prev) =>
      prev.map((r) =>
        r.id === reqId
          ? { ...r, status: 'approved', decided_at: new Date().toISOString(), decided_by: 'Admin' }
          : r
      )
    );
    toastSuccess('Reprocessing request approved. Extraction job enqueued.', 'Approved');
  };

  const handleReject = (reqId: string) => {
    if (!rejectComment.trim()) {
      toastError('Please enter a decision comment for rejection.');
      return;
    }
    setLocalRequests((prev) =>
      prev.map((r) =>
        r.id === reqId
          ? {
              ...r,
              status: 'rejected',
              decided_at: new Date().toISOString(),
              decided_by: 'Admin',
              decision_comment: rejectComment,
            }
          : r
      )
    );
    setRejectingId(null);
    setRejectComment('');
    toastSuccess('Reprocessing request rejected.', 'Rejected');
  };

  const filtered = requests.filter((r) => {
    if (statusFilter !== 'all' && r.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="content-pane space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-primary">
            Administration
          </span>
        </div>
        <h1 className="page-title mt-1">Reprocessing Approval Queue</h1>
        <p className="page-description">
          Review, approve, or reject manual document reprocessing and re-extraction requests
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-border pb-3 text-xs">
        <button
          type="button"
          onClick={() => setStatusFilter('all')}
          className={`px-3 py-1.5 rounded-lg font-medium transition ${
            statusFilter === 'all' ? 'bg-primary/20 text-primary font-semibold' : 'text-text-muted hover:text-text-main'
          }`}
        >
          All Requests ({requests.length})
        </button>
        <button
          type="button"
          onClick={() => setStatusFilter('pending_approval')}
          className={`px-3 py-1.5 rounded-lg font-medium transition ${
            statusFilter === 'pending_approval' ? 'bg-amber-500/20 text-amber-400 font-semibold' : 'text-text-muted hover:text-text-main'
          }`}
        >
          Pending Approval ({requests.filter((r) => r.status === 'pending_approval').length})
        </button>
        <button
          type="button"
          onClick={() => setStatusFilter('approved')}
          className={`px-3 py-1.5 rounded-lg font-medium transition ${
            statusFilter === 'approved' ? 'bg-emerald-500/20 text-emerald-400 font-semibold' : 'text-text-muted hover:text-text-main'
          }`}
        >
          Approved ({requests.filter((r) => r.status === 'approved').length})
        </button>
        <button
          type="button"
          onClick={() => setStatusFilter('rejected')}
          className={`px-3 py-1.5 rounded-lg font-medium transition ${
            statusFilter === 'rejected' ? 'bg-red-500/20 text-red-400 font-semibold' : 'text-text-muted hover:text-text-main'
          }`}
        >
          Rejected ({requests.filter((r) => r.status === 'rejected').length})
        </button>
      </div>

      {/* Requests Table */}
      <div className="dashboard-card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-text-muted">
            <RotateCcw className="size-8 mx-auto mb-2 opacity-40 text-primary" />
            <div className="text-sm font-semibold text-text-main">No Requests Found</div>
            <div className="text-xs mt-1">There are no reprocessing requests matching this filter.</div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr>
                  <th className="table-header-cell min-w-[240px]">DOCUMENT UID</th>
                  <th className="table-header-cell w-36">REQUESTED BY</th>
                  <th className="table-header-cell w-32">DATE</th>
                  <th className="table-header-cell min-w-[280px]">REASON & DEFECT</th>
                  <th className="table-header-cell w-28">STATUS</th>
                  <th className="table-header-cell w-44 text-right pr-6">ADMIN DECISION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((req) => (
                  <tr key={req.id} className="table-row">
                    <td className="table-cell">
                      <div className="flex items-center gap-2 font-mono font-medium text-text-main">
                        <FileText className="size-4 text-primary shrink-0" />
                        <span className="truncate">{req.document_uid}</span>
                      </div>
                    </td>

                    <td className="table-cell text-text-main">{req.requested_by}</td>

                    <td className="table-cell text-text-muted">{formatDate(req.requested_at)}</td>

                    <td className="table-cell leading-relaxed text-text-main">
                      {req.reason}
                      {req.decision_comment && (
                        <div className="mt-1 text-[11px] text-red-400 italic">
                          Decision note: {req.decision_comment}
                        </div>
                      )}
                    </td>

                    <td className="table-cell">
                      {req.status === 'pending_approval' && (
                        <span className="rounded-full bg-amber-500/15 border border-amber-500/30 px-2.5 py-0.5 text-[10px] font-semibold text-amber-400 uppercase">
                          Pending
                        </span>
                      )}
                      {req.status === 'approved' && (
                        <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-400 uppercase">
                          Approved
                        </span>
                      )}
                      {req.status === 'rejected' && (
                        <span className="rounded-full bg-red-500/15 border border-red-500/30 px-2.5 py-0.5 text-[10px] font-semibold text-red-400 uppercase">
                          Rejected
                        </span>
                      )}
                    </td>

                    <td className="table-cell text-right pr-6">
                      {req.status === 'pending_approval' ? (
                        rejectingId === req.id ? (
                          <div className="flex flex-col items-end gap-1.5">
                            <input
                              type="text"
                              value={rejectComment}
                              onChange={(e) => setRejectComment(e.target.value)}
                              placeholder="Rejection comment..."
                              className="field h-7 text-xs px-2"
                              autoFocus
                            />
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setRejectingId(null)}
                                className="h-6 text-[10px] px-1.5"
                              >
                                Cancel
                              </Button>
                              <Button
                                variant="danger"
                                size="sm"
                                onClick={() => handleReject(req.id)}
                                className="h-6 text-[10px] px-2"
                              >
                                Confirm Reject
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            <Button
                              variant="primary"
                              size="sm"
                              onClick={() => handleApprove(req.id)}
                              leftIcon={<Check className="size-3" />}
                              className="h-7 text-xs px-2.5"
                            >
                              Approve
                            </Button>
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => setRejectingId(req.id)}
                              leftIcon={<X className="size-3" />}
                              className="h-7 text-xs px-2"
                            >
                              Reject
                            </Button>
                          </div>
                        )
                      ) : (
                        <span className="text-[11px] text-text-muted">
                          Decided {req.decided_at ? formatDate(req.decided_at) : '—'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

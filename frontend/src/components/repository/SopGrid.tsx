import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Eye,
  CheckSquare,
  Languages,
  ArrowRightLeft,
  Download,
  Trash2,
  Calendar,
  Layers,
} from 'lucide-react';
import { SopRecord } from '@/types';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileTypeIcon } from '@/components/ui/FileTypeIcon';
import { getDisplayTitle, getDisplaySubline } from '@/lib/sopDisplay';
import { formatDate, formatTimeAgo } from '@/lib/format';
import { Button } from '@/components/ui/Button';

interface SopGridProps {
  sops: SopRecord[];
  onDelete: (sop: SopRecord) => void;
}

export const SopGrid: React.FC<SopGridProps> = ({ sops, onDelete }) => {
  const navigate = useNavigate();

  const downloadJson = (documentUid: string) => {
    window.open(`/documents/v2/${encodeURIComponent(documentUid)}/json`, '_blank');
  };

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {sops.map((sop) => {
        const title = getDisplayTitle(sop);
        const subline = getDisplaySubline(sop);

        return (
          <div
            key={sop.id}
            onClick={() => navigate(`/sops/${sop.id}`)}
            className="dashboard-card flex flex-col justify-between p-5 hover:border-primary/40 hover:shadow-glow transition-all cursor-pointer group"
          >
            {/* Top Row: File icon + Status */}
            <div>
              <div className="flex items-start justify-between gap-3 mb-3">
                <FileTypeIcon fileType={sop.file_type} size="md" />
                <StatusBadge status={sop.status} size="sm" />
              </div>

              {/* Title & metadata */}
              <h3 className="font-semibold text-text-main group-hover:text-primary transition line-clamp-2 text-sm leading-snug">
                {title}
              </h3>
              <p className="text-xs text-text-muted mt-1 line-clamp-1">{subline}</p>

              {/* Badges / pills */}
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded bg-white/5 border border-border px-2 py-0.5 text-[11px] text-text-muted">
                  {sop.document_type || 'Guidance'}
                </span>
                <span className="rounded bg-white/5 border border-border px-2 py-0.5 text-[11px] text-text-muted">
                  {sop.page_count || 1} pages
                </span>
                <span className="rounded bg-primary/10 border border-primary/20 px-2 py-0.5 text-[11px] text-primary">
                  v{sop.gpdat_version || 1}
                </span>
              </div>
            </div>

            {/* Bottom Footer: Date & Actions */}
            <div className="mt-5 pt-3 border-t border-border flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
                <Calendar className="size-3" />
                <span>{formatTimeAgo(sop.updated_at)}</span>
              </div>

              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <Button
                  variant="icon"
                  size="sm"
                  onClick={() => navigate(`/review/${sop.id}?mode=migration`)}
                  title="Start Migration"
                  aria-label="Migrate"
                >
                  <ArrowRightLeft className="size-3.5 text-emerald-400" />
                </Button>

                <Button
                  variant="icon"
                  size="sm"
                  onClick={() => navigate(`/review/${sop.id}?mode=review`)}
                  title="Open Review"
                  aria-label="Review"
                >
                  <CheckSquare className="size-3.5 text-amber-400" />
                </Button>

                <Button
                  variant="icon"
                  size="sm"
                  onClick={() => downloadJson(sop.document_Uid)}
                  title="Download JSON"
                  aria-label="Download"
                >
                  <Download className="size-3.5 text-text-muted" />
                </Button>

                <Button
                  variant="icon"
                  size="sm"
                  onClick={() => onDelete(sop)}
                  title="Delete"
                  aria-label="Delete"
                >
                  <Trash2 className="size-3.5 text-red-400" />
                </Button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

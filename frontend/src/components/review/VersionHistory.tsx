import React from 'react';
import { History, GitCommit, CheckCircle2, RotateCcw } from 'lucide-react';
import { WorkflowVersion } from '@/types';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/format';

interface VersionHistoryProps {
  versions: WorkflowVersion[];
  currentVersionId?: string;
  onSelectVersion?: (version: WorkflowVersion) => void;
  onRestoreVersion?: (version: WorkflowVersion) => void;
}

export const VersionHistory: React.FC<VersionHistoryProps> = ({
  versions,
  currentVersionId,
  onSelectVersion,
  onRestoreVersion,
}) => {
  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <History className="size-3.5 text-primary" />
          <span>Version History ({versions.length})</span>
        </div>
      </div>

      <div className="flex-1 p-3 overflow-y-auto space-y-2">
        {versions.map((ver) => {
          const isCurrent = ver.id === currentVersionId || ver.is_current;

          return (
            <div
              key={ver.id}
              onClick={() => onSelectVersion?.(ver)}
              className={`flex items-start justify-between rounded-lg border p-3 text-xs transition cursor-pointer ${
                isCurrent
                  ? 'border-primary/40 bg-primary/10'
                  : 'border-border bg-card hover:bg-white/5'
              }`}
            >
              <div className="flex items-start gap-2.5 min-w-0">
                <GitCommit className={`size-4 mt-0.5 ${isCurrent ? 'text-primary' : 'text-text-muted'}`} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-text-main">
                      Version {ver.version_number}
                    </span>
                    {ver.status === 'approved' && (
                      <span className="rounded bg-emerald-500/15 px-1.5 py-0.2 text-[10px] text-emerald-400 font-medium">
                        Approved
                      </span>
                    )}
                    {isCurrent && (
                      <span className="rounded bg-primary/20 px-1.5 py-0.2 text-[10px] text-primary font-medium">
                        Current
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-text-muted mt-1">
                    {formatDate(ver.created_at)} {ver.created_by ? `by ${ver.created_by}` : ''}
                  </div>
                  {ver.description && (
                    <div className="text-xs text-text-muted mt-1 italic">{ver.description}</div>
                  )}
                </div>
              </div>

              {!isCurrent && onRestoreVersion && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRestoreVersion(ver);
                  }}
                  title="Restore as new draft"
                >
                  <RotateCcw className="size-3 text-text-muted hover:text-primary" />
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

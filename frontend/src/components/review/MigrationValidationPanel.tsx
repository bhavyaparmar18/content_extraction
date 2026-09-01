import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, AlertCircle, Sparkles, Layers, Download, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/Button';

interface MigrationValidationPanelProps {
  documentId?: string;
}

export const MigrationValidationPanel: React.FC<MigrationValidationPanelProps> = ({ documentId }) => {
  const { data: statusReport, isLoading, isError, refetch } = useQuery({
    queryKey: ['migrationStatus', documentId],
    queryFn: () => (documentId ? api.getMigrationStatus(documentId) : null),
    enabled: !!documentId,
    retry: 1,
  });

  const downloadUrl = documentId ? api.getDownloadDocxUrl(documentId) : '';

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
        <div className="flex items-center gap-1.5 text-text-main">
          <Layers className="size-3.5 text-primary" />
          <span>Template Section Mapping</span>
        </div>
        {statusReport?.content_coverage_pct !== undefined ? (
          <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-400 font-semibold">
            {statusReport.content_coverage_pct}% Coverage
          </span>
        ) : (
          <span className="rounded bg-primary/10 px-2 py-0.5 text-[10px] text-primary font-semibold">
            Template v2.1
          </span>
        )}
      </div>

      <div className="flex-1 p-3 overflow-y-auto space-y-3 text-xs">
        {/* Real QA Report if available */}
        {statusReport ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 space-y-1.5">
              <div className="flex items-center justify-between font-semibold text-emerald-400">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="size-4" /> Migration Executed
                </span>
                <span className="text-[10px] font-mono uppercase">{statusReport.status}</span>
              </div>
              <div className="text-xs text-text-muted">
                Placed <strong className="text-text-main">{statusReport.total_placed_elements}</strong> / {statusReport.total_source_elements} elements across <strong className="text-text-main">{statusReport.sections_mapped}</strong> mapped sections.
              </div>
            </div>

            {/* Warnings if any */}
            {statusReport.low_confidence_warnings?.length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-1">
                <div className="font-semibold text-amber-400 flex items-center gap-1">
                  <AlertCircle className="size-3.5" /> Pipeline Notes
                </div>
                {statusReport.low_confidence_warnings.map((w: string, idx: number) => (
                  <div key={idx} className="text-[11px] text-text-muted leading-tight">
                    • {w}
                  </div>
                ))}
              </div>
            )}

            {/* Download Button */}
            <div className="pt-2">
              <Button
                variant="primary"
                size="sm"
                className="w-full"
                onClick={() => window.open(downloadUrl, '_blank')}
                leftIcon={<Download className="size-3.5" />}
              >
                Download Migrated DOCX
              </Button>
            </div>
          </div>
        ) : (
          /* Default Template Mapping Blueprint */
          <div className="space-y-2">
            {[
              { sectionKey: 'SEC_01_PURPOSE', mappedTitle: '1. Purpose & Scope', status: 'mapped', confidence: 98 },
              { sectionKey: 'SEC_02_RESPONSIBILITY', mappedTitle: '2. Roles & Responsibilities', status: 'mapped', confidence: 95 },
              { sectionKey: 'SEC_03_PROCEDURES', mappedTitle: '3. Operating Steps', status: 'mapped', confidence: 92 },
              { sectionKey: 'SEC_04_REFERENCES', mappedTitle: '4. Related GxP References', status: 'mapped', confidence: 89 },
              { sectionKey: 'SEC_05_RECORDS', mappedTitle: '5. Retention & Archival', status: 'optional', confidence: 0 },
            ].map((it, idx) => (
              <div key={idx} className="rounded-lg border border-border bg-card p-2.5 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-text-main">{it.mappedTitle}</span>
                  {it.status === 'mapped' ? (
                    <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400">
                      <CheckCircle2 className="size-3" /> {it.confidence}% Match
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[10px] font-mono text-amber-400">
                      <AlertCircle className="size-3" /> Optional
                    </span>
                  )}
                </div>
                <div className="text-[10px] font-mono text-text-muted">{it.sectionKey}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

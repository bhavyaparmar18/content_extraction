import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, FileSpreadsheet, FileText, Info, Lock } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { migrationsApi } from '../api';
import { useRenderReport } from '../hooks';
import { humanize, isExportable, statusInfo } from '../status';
import type { MigrationJob, QualityReport, TemplateModel } from '../types';
import { DocxViewer } from './DocxViewer';
import { blockingIssues } from '../report';
import { useDownloads } from '../useDownloads';
import { ResolutionNote } from './issues';
import { PaneTabs } from './paneParts';
import { MigrationTranslations } from '@/features/translations/components/MigrationTranslations';

type Tab = 'final' | 'review';

/** ④ The migrated SOP as Word will show it: the final document (once the job completed) or the review draft. */
export const FinalDocument: React.FC<{
  job: MigrationJob;
  report?: QualityReport;
  template?: TemplateModel;
  onGoToIssues: () => void;
}> = ({ job, report, template, onGoToIssues }) => {
  const exportable = isExportable(job.status) && !job.running;
  const [tab, setTab] = useState<Tab>(exportable ? 'final' : 'review');
  const render = useRenderReport(job.job_id, job);
  const download = useDownloads(job);
  const reviewDoc = job.artifacts.filter((a) => a.kind === 'docx' && !a.scope).sort((a, b) => b.version - a.version)[0];
  const drafts = job.artifacts.filter((a) => a.kind === 'section_draft').map((a) => `${a.scope}:${a.version}`).sort().join(',');
  const quality = job.artifacts.filter((a) => a.kind === 'quality_report' && !a.scope).length;
  const accepted = (report?.issues ?? []).filter((i) => i.gate === 'missing_slot' && i.resolved);
  const slotNames = new Map(template?.sections.flatMap((s) => s.slots.map((x) => [x.slot_id, `${s.heading} › ${x.key ? humanize(x.key) : x.slot_id}`] as const)) ?? []);
  const blockers = blockingIssues(report);

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <PaneTabs
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          tabs={[
            { id: 'final', label: 'Final document' },
            { id: 'review', label: 'Review draft' },
          ]}
          extra={
            <span className="text-[11px] text-text-muted" title={tab === 'final' ? 'What the export will contain: gaps accepted as N/A removed, no review markers' : 'Gap markers and slot boundaries kept for review'}>
              {tab === 'final' ? 'As exported' : 'With review markers'}
            </span>
          }
        />
        <div className="min-h-0 flex-1">
          {tab === 'final' ? (
            exportable ? (
              <DocxViewer fileKey={['final', job.job_id, drafts, quality]} load={() => migrationsApi.finalPreview(job.job_id)} />
            ) : (
              <NotYet job={job} blockers={blockers.map((i) => i.message)} onGoToIssues={onGoToIssues} />
            )
          ) : reviewDoc ? (
            <DocxViewer fileKey={['review', job.job_id, reviewDoc.version]} load={() => migrationsApi.reviewDocument(job.job_id)} />
          ) : (
            <p className="p-6 text-sm text-text-muted">The review draft has not been rendered yet.</p>
          )}
        </div>
      </div>

      <aside className="w-72 shrink-0 space-y-4 overflow-y-auto border-l border-border p-4 text-xs">
        <div className="space-y-2">
          <Button
            variant="primary"
            size="sm"
            className="w-full"
            leftIcon={exportable ? <FileText className="size-3.5" /> : <Lock className="size-3.5" />}
            disabled={!exportable || !!download.busy}
            isLoading={download.busy === 'Final document'}
            onClick={download.final}
          >
            Download final document
          </Button>
          <Button variant="secondary" size="sm" className="w-full" leftIcon={<FileText className="size-3.5" />} disabled={!reviewDoc || !!download.busy} onClick={download.review}>
            Download review draft
          </Button>
          <Button variant="ghost" size="sm" className="w-full" leftIcon={<FileSpreadsheet className="size-3.5" />} disabled={!!download.busy} onClick={download.trace}>
            Traceability (.csv)
          </Button>
          <p className="text-[11px] text-text-muted">Downloading the final document records the export in the job history and on the SOP.</p>
        </div>

        <MigrationTranslations migration={job} />

        {accepted.length > 0 && (
          <Section title="Removed from the final document">
            {accepted.map((i) => (
              <li key={i.issue_id}>
                <div className="text-text-main">{(i.slot_id && slotNames.get(i.slot_id)) ?? i.slot_id}</div>
                {i.resolution_note && <ResolutionNote note={i.resolution_note} />}
              </li>
            ))}
          </Section>
        )}

        {render.data && (
          <>
            {render.data.problems.length > 0 && (
              <Section title="Render check failed" tone="danger">
                {render.data.problems.map((p) => <li key={p}>{p}</li>)}
              </Section>
            )}
            {render.data.warnings.length > 0 && (
              <Section title="Renderer notes" tone="warning">
                {render.data.warnings.map((w) => <li key={w}>{w}</li>)}
              </Section>
            )}
            {render.data.sections_removed.length > 0 && (
              <Section title="Optional sections left out">
                {render.data.sections_removed.map((s) => <li key={s}>{template?.sections.find((t) => t.section_id === s)?.heading ?? s}</li>)}
              </Section>
            )}
            <Section title="Rendered slots">
              {Object.entries(countBy(render.data.slots.map((s) => s.outcome))).map(([outcome, n]) => (
                <li key={outcome} className="flex justify-between"><span>{humanize(outcome)}</span><span className="text-text-main">{n}</span></li>
              ))}
              {render.data.toc_entries ? (
                <li className="flex justify-between"><span>Table of contents entries</span><span className="text-text-main">{render.data.toc_entries}</span></li>
              ) : null}
            </Section>
          </>
        )}
        <p className="flex gap-1.5 text-[11px] text-text-muted">
          <Info className="mt-0.5 size-3 shrink-0" />
          The in-app view approximates Word's layout (page breaks, field values). Open the download in Word for the exact pages.
        </p>
      </aside>
    </div>
  );
};

const NotYet: React.FC<{ job: MigrationJob; blockers: string[]; onGoToIssues: () => void }> = ({ job, blockers, onGoToIssues }) => (
  <div className="mx-auto max-w-lg px-6 py-12 text-center">
    <Lock className="mx-auto size-8 text-text-muted" />
    <h3 className="mt-3 text-sm font-semibold text-text-main">The final document is available once the job has completed</h3>
    <p className="mt-1 text-xs text-text-muted">
      The job is <span className="text-text-main">{statusInfo(job.status).label.toLowerCase()}</span>.
      {blockers.length ? ' Resolve these first:' : job.status === 'MANUALLY_EDITED' ? ' Re-check your edits first.' : ''}
    </p>
    {blockers.length > 0 && (
      <ul className="mt-4 space-y-1.5 text-left text-xs">
        {blockers.slice(0, 8).map((b) => (
          <li key={b} className="flex gap-2 rounded-md border border-danger/25 bg-danger/[0.04] px-2.5 py-1.5">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-danger" /> {b}
          </li>
        ))}
        {blockers.length > 8 && <li className="text-text-muted">…and {blockers.length - 8} more</li>}
      </ul>
    )}
    <Button size="sm" variant="primary" className="mt-5" leftIcon={<CheckCircle2 className="size-3.5" />} onClick={onGoToIssues}>
      Go to draft and issues
    </Button>
    <p className="mt-3 text-[11px] text-text-muted">Meanwhile the "Review draft" tab shows the rendered document with its gap markers.</p>
  </div>
);

const Section: React.FC<{ title: string; tone?: 'danger' | 'warning'; children: React.ReactNode }> = ({ title, tone, children }) => (
  <div>
    <div className={clsx('mb-1.5 font-semibold', tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : 'text-text-main')}>{title}</div>
    <ul className="space-y-1 text-[11px] text-text-muted">{children}</ul>
  </div>
);

function countBy(values: string[]): Record<string, number> {
  return values.reduce<Record<string, number>>((acc, v) => ({ ...acc, [v]: (acc[v] ?? 0) + 1 }), {});
}

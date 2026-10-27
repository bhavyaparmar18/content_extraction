import React, { useState } from 'react';
import { CheckCircle2, Download, Info, Lock } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { DocxViewer } from '@/features/migrations/components/DocxViewer';
import { PaneTabs } from '@/features/migrations/components/paneParts';
import { actorName } from '@/features/migrations/report';
import { translationsApi } from '../api';
import { useLanguageNames, useTranslationRenderReport } from '../hooks';
import { keptInEnglish } from '../segments';
import { translationPermissions } from '../status';
import { useTranslationDownload } from '../useTranslationDownload';
import type { TranslationJob } from '../types';

type Tab = 'translated' | 'english';

/** ④ The translated document as Word will show it, its render report, and the download once approved. */
export const TranslationFinal: React.FC<{ job: TranslationJob; onOpenSegment: (segmentId: string) => void }> = ({ job, onOpenSegment }) => {
  const [tab, setTab] = useState<Tab>('translated');
  const names = useLanguageNames();
  const render = useTranslationRenderReport(job);
  const download = useTranslationDownload(job);
  const can = translationPermissions(job);
  const docx = job.artifacts.filter((a) => a.kind === 'docx' && a.scope === 'translated').sort((a, b) => b.version - a.version)[0];
  const english = keptInEnglish(render.data);
  const otherWarnings = (render.data?.warnings ?? []).filter((w) => !/shown in English$/.test(w));
  const stale = job.review && !job.review.render_current;

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <PaneTabs
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          tabs={[
            { id: 'translated', label: `${names(job.language)}` },
            { id: 'english', label: 'English' },
          ]}
          extra={<span className="text-[11px] text-text-muted">{tab === 'translated' ? `Render v${docx?.version ?? '?'}` : 'The English final the translation started from'}</span>}
        />
        {tab === 'translated' && stale && (
          <div className="shrink-0 border-b border-warning/20 bg-warning/[0.06] px-4 py-1.5 text-[11px] text-warning">
            Edits since this render are not in it yet: use "Update document" above.
          </div>
        )}
        <div className="min-h-0 flex-1">
          {tab === 'translated' ? (
            docx ? (
              <DocxViewer fileKey={['translation', job.job_id, docx.version]} load={() => translationsApi.preview(job.job_id)} />
            ) : (
              <p className="p-6 text-sm text-text-muted">The translated document has not been rendered yet.</p>
            )
          ) : (
            <DocxViewer fileKey={['translation-english', job.job_id]} load={() => translationsApi.english(job.job_id)}
              emptyMessage={<span>The English document of this job could not be shown (its render had problems when the job was prepared).</span>} />
          )}
        </div>
      </div>

      <aside className="w-72 shrink-0 space-y-4 overflow-y-auto border-l border-border p-4 text-xs">
        <div className="space-y-2">
          {job.status === 'APPROVED' ? (
            <p className="flex gap-1.5 rounded-md border border-primary/25 bg-primary/[0.05] px-3 py-2 text-[11px] text-text-muted">
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-primary" />
              Approved by {actorName(job.approved_by)}{job.approved_at ? ` on ${new Date(job.approved_at).toLocaleString()}` : ''}.
            </p>
          ) : (
            <p className="flex gap-1.5 text-[11px] text-text-muted"><Lock className="mt-0.5 size-3 shrink-0" /> The download opens once the translation is approved.</p>
          )}
          <Button variant="primary" size="sm" className="w-full" leftIcon={<Download className="size-3.5" />} disabled={!can.download} isLoading={download.busy} onClick={download.run}>
            Download translated document
          </Button>
          <p className="text-[11px] text-text-muted">The download is the approved document itself, never a new render; each one is recorded.</p>
        </div>

        {render.data && (
          <>
            {render.data.problems.length > 0 && (
              <Section title="Render check failed" tone="danger">
                {render.data.problems.map((p) => <li key={p}>{p}</li>)}
              </Section>
            )}
            {english.size > 0 && (
              <Section title={`Shown in English (${english.size})`} tone="warning">
                <li className="text-text-muted">These segments could not be written in the document; their English stays until fixed.</li>
                <li className="flex flex-wrap gap-1">
                  {[...english].map((id) => (
                    <button key={id} type="button" onClick={() => onOpenSegment(id)} className="unit-id hover:text-primary">{id}</button>
                  ))}
                </li>
              </Section>
            )}
            {otherWarnings.length > 0 && (
              <Section title="Renderer notes" tone="warning">
                {otherWarnings.map((w) => <li key={w}>{w}</li>)}
              </Section>
            )}
            <Section title="Document">
              <Row label="First page, headers, footers">{job.language_template_id ? `${job.language_template_id} v${job.language_template_version}` : 'English kept'}</Row>
              {render.data.toc_entries ? <Row label="Table of contents entries">{render.data.toc_entries}</Row> : null}
              <Row label="Render check">{render.data.problems.length ? 'failed' : 'passed'}</Row>
            </Section>
          </>
        )}
        <p className="flex gap-1.5 text-[11px] text-text-muted">
          <Info className="mt-0.5 size-3 shrink-0" />
          The in-app view approximates Word's layout (page breaks, field values, East Asian fonts). Open the download in Word for the exact pages.
        </p>
      </aside>
    </div>
  );
};

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <li className="flex justify-between gap-2"><span>{label}</span><span className="text-right text-text-main">{children}</span></li>
);

const Section: React.FC<{ title: string; tone?: 'danger' | 'warning'; children: React.ReactNode }> = ({ title, tone, children }) => (
  <div>
    <div className={clsx('mb-1.5 font-semibold', tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : 'text-text-main')}>{title}</div>
    <ul className="space-y-1 text-[11px] text-text-muted">{children}</ul>
  </div>
);

import React, { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, AlertTriangle, ArrowLeft, CheckCircle2, Image, Info, Loader2, Upload } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { formatTimeAgo } from '@/lib/format';
import { actorName } from '@/features/migrations/report';
import { DocxViewer } from '@/features/migrations/components/DocxViewer';
import { translationsApi } from '@/features/translations/api';
import { useLanguageNames, useLanguageTemplate, useLanguageTemplateReport, useLanguageTemplates, useResourceMutations } from '@/features/translations/hooks';
import { TEMPLATE_STATUS } from '@/features/translations/status';
import { ErrorPanel, LanguageLabel, ToneChip } from '@/features/translations/components/parts';
import { LanguageTemplateUploadDialog } from '@/features/translations/components/ResourceUploadDialogs';
import type { FrontMatterPart, FrontMatterReport, LanguageTemplateRecord } from '@/features/translations/types';

/** One language template version: the extracted first page, headers and footers to check before marking it ready. */
export const LanguageTemplatePage: React.FC = () => {
  const { templateId = '' } = useParams<{ templateId: string }>();
  const [params] = useSearchParams();
  const asked = params.get('version') ? Number(params.get('version')) : undefined;
  const record = useLanguageTemplate(templateId, asked);

  if (record.isLoading) return <div className="grid h-full place-items-center text-sm text-text-muted"><Loader2 className="size-4 animate-spin" /></div>;
  if (record.error || !record.data) {
    return (
      <div className="content-pane">
        <div className="error-panel flex items-start gap-2 text-sm">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <div className="font-medium text-text-main">This language template could not be loaded</div>
            <div className="text-xs text-text-muted">{record.error?.message}</div>
          </div>
        </div>
      </div>
    );
  }
  return <TemplateView record={record.data} />;
};

const TemplateView: React.FC<{ record: LanguageTemplateRecord }> = ({ record }) => {
  const navigate = useNavigate();
  const { success } = useToast();
  const names = useLanguageNames();
  const versions = useLanguageTemplates({ template_id: record.template_id });
  const report = useLanguageTemplateReport(record.template_id, record.version);
  const { markReady } = useResourceMutations();
  const [newVersion, setNewVersion] = useState(false);
  const status = TEMPLATE_STATUS[record.status];
  const problems = report.data?.problems ?? [];
  const path = (version: number) => `/translations/resources/templates/${encodeURIComponent(record.template_id)}?version=${version}`;

  const ready = () =>
    markReady.mutate(
      { id: record.template_id, version: record.version },
      { onSuccess: () => success(`Translations into ${names(record.language)} can now use it.`, `${record.template_id} v${record.version} is ready`) },
    );

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-card/60 px-4 py-2.5">
        <button type="button" onClick={() => navigate('/translations/resources?tab=templates')} title="Language resources"
          className="grid size-8 place-items-center rounded-md text-text-muted hover:bg-white/5 hover:text-text-main">
          <ArrowLeft className="size-4" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-[15px] font-semibold text-text-main">{record.name}</h1>
            <ToneChip tone={status.tone}>{status.label}</ToneChip>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-text-muted">
            <span className="font-mono">{record.template_id}</span>
            <select value={record.version} aria-label="Version" className="rounded border border-border bg-transparent px-1 py-0 text-[11px]" onChange={(e) => navigate(path(Number(e.target.value)))}>
              {(versions.data ?? [record]).map((v) => <option key={v.id} value={v.version}>v{v.version} · {TEMPLATE_STATUS[v.status].label}</option>)}
            </select>
            <LanguageLabel code={record.language} name={names(record.language)} />
            {record.source_filename && <span>{record.source_filename}</span>}
            <span>{actorName(record.created_by)} · {formatTimeAgo(record.created_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" leftIcon={<Upload className="size-3.5" />} onClick={() => setNewVersion(true)}>New version</Button>
          {record.status !== 'ready' && (
            <Button size="sm" variant="primary" leftIcon={<CheckCircle2 className="size-3.5" />} disabled={record.status === 'failed' || problems.length > 0 || !report.data}
              title={problems.length ? 'Fix the problems first: upload a corrected file as a new version' : undefined} isLoading={markReady.isPending} onClick={ready}>
              Mark ready
            </Button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          {record.status === 'failed' ? (
            <div className="mx-auto max-w-lg px-6 py-12 text-center">
              <AlertCircle className="mx-auto size-8 text-danger" />
              <h3 className="mt-3 text-sm font-semibold text-text-main">The first page could not be extracted</h3>
              {record.error && <p className="mt-2 text-xs text-text-muted">{record.error}</p>}
              <p className="mt-3 text-xs text-text-muted">Upload a corrected file as a new version.</p>
            </div>
          ) : (
            <DocxViewer
              fileKey={['language-template-preview', record.template_id, record.version]}
              load={() => translationsApi.languageTemplatePreview(record.template_id, record.version)}
              toolbarExtra={<span className="truncate text-[11px] text-text-muted">The extracted first page, then two placeholder body pages with the body headers and footers</span>}
            />
          )}
        </div>

        <aside className="w-80 shrink-0 space-y-4 overflow-y-auto border-l border-border p-4 text-xs">
          {record.status === 'extracted' && (
            <p className="rounded-md border border-warning/30 bg-warning/[0.06] px-3 py-2 text-[11px] text-text-muted">
              Check the preview pages: the first page and every header and footer must look right. Once ready, translations into {names(record.language)} can use it.
            </p>
          )}
          {record.status === 'ready' && (
            <p className="flex gap-1.5 rounded-md border border-primary/25 bg-primary/[0.05] px-3 py-2 text-[11px] text-text-muted">
              <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-primary" />
              Ready: the start dialog offers it for {names(record.language)}.
            </p>
          )}
          <ErrorPanel error={markReady.error} details={apiErrorDetails(markReady.error)} />
          {report.isLoading && <Loader2 className="size-4 animate-spin text-text-muted" />}
          {report.data && <ReportView report={report.data} />}
          <p className="flex gap-1.5 text-[11px] text-text-muted">
            <Info className="mt-0.5 size-3 shrink-0" />
            The in-app view approximates Word's layout. Field values (page numbers, document variables) show what the file saved.
          </p>
        </aside>
      </div>

      {newVersion && (
        <LanguageTemplateUploadDialog open base={record} onClose={() => setNewVersion(false)} onCreated={(r) => { setNewVersion(false); navigate(path(r.version)); }} />
      )}
    </div>
  );
};

const ReportView: React.FC<{ report: FrontMatterReport }> = ({ report }) => (
  <>
    {report.problems.length > 0 && (
      <Section title={`Problems (${report.problems.length}): it cannot be marked ready`} tone="danger">
        {report.problems.map((p) => <li key={p} className="flex gap-1.5"><AlertCircle className="mt-0.5 size-3 shrink-0 text-danger" />{p}</li>)}
      </Section>
    )}
    {report.warnings.length > 0 && (
      <Section title={`Warnings (${report.warnings.length})`} tone="warning">
        {report.warnings.map((w) => <li key={w} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3 shrink-0 text-warning" />{w}</li>)}
      </Section>
    )}
    <Section title="First page">
      <Row label="Ends at">{report.cover_end === 'section_break' ? 'a section break' : report.cover_end === 'page_break' ? 'a page break' : 'not found'}</Row>
      <Row label="Blocks">{report.cover_blocks}</Row>
      <Row label="Images">{report.images}</Row>
      <Row label="Sections in the file">{report.sections}</Row>
      {report.cover_text && <li className="mt-1 line-clamp-4 rounded border border-border bg-black/10 px-2 py-1.5 italic">{report.cover_text}</li>}
    </Section>
    <Section title="First page's headers and footers">
      <Parts parts={report.cover_parts} />
      <Row label="Different first page">{report.title_page_cover ? 'yes' : 'no'}</Row>
    </Section>
    <Section title="Body headers and footers">
      <Parts parts={report.body_parts} />
      <Row label="Different first page">{report.title_page_body ? 'yes' : 'no'}</Row>
      <Row label="Different odd and even">{report.even_and_odd ? 'yes' : 'no'}</Row>
    </Section>
    {report.styles.length > 0 && (
      <Section title="Styles it uses">
        <li className="flex flex-wrap gap-1">{report.styles.map((s) => <span key={s} className="chip-muted">{s}</span>)}</li>
      </Section>
    )}
  </>
);

const Parts: React.FC<{ parts: FrontMatterPart[] }> = ({ parts }) =>
  parts.length === 0 ? (
    <li>None</li>
  ) : (
    <>
      {[...parts].sort((a, b) => `${a.kind}${a.type}`.localeCompare(`${b.kind}${b.type}`)).map((p) => (
        <li key={p.partname} className="rounded border border-border px-2 py-1.5">
          <div className="flex items-center gap-1.5 text-text-main">
            <span className="capitalize">{p.kind}</span>
            <span className="chip-muted">{p.type}</span>
            {p.images > 0 && <span className="flex items-center gap-0.5"><Image className="size-3" />{p.images}</span>}
          </div>
          {p.text && <div className="mt-0.5 line-clamp-2">{p.text}</div>}
        </li>
      ))}
    </>
  );

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <li className="flex justify-between gap-2"><span>{label}</span><span className="text-text-main">{children}</span></li>
);

const Section: React.FC<{ title: string; tone?: 'danger' | 'warning'; children: React.ReactNode }> = ({ title, tone, children }) => (
  <div>
    <div className={clsx('mb-1.5 font-semibold', tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : 'text-text-main')}>{title}</div>
    <ul className="space-y-1 text-[11px] text-text-muted">{children}</ul>
  </div>
);

import type { EventLabels } from '@/features/migrations/components/ActivityLog';
import { humanize } from '@/features/migrations/status';
import { splitNote } from '@/features/migrations/report';
import { translationStatusInfo } from './status';
import type { JobEvent, TranslationStatus } from './types';

const TITLES: Record<string, string> = {
  created: 'Translation started',
  segments: 'English document cut into segments',
  glossary: 'Glossary snapshotted',
  no_glossary: 'No glossary: free translation',
  front_matter: 'Language template snapshotted',
  no_language_template: 'No language template: English first page, header and footer kept',
  english_render_problems: 'The English render reported problems',
  translator: 'Translated',
  checks: 'Checked',
  repair: 'Repaired',
  render: 'Rendered',
  render_problems: 'The translated render reported problems',
  render_requested: 'Render requested',
  segment_edited: 'Segment edited',
  segments_replaced: 'Find and replace',
  issue_resolved: 'Issue resolved',
  approved: 'Approved',
  export: 'Approved document downloaded',
  cancel_requested: 'Cancel requested',
};

/** The tokens of a stage's usage (``{calls, input_tokens, output_tokens, total_tokens}``). */
const tokens = (usage?: Record<string, number>) =>
  usage ? usage.total_tokens ?? (usage.input_tokens ?? 0) + (usage.output_tokens ?? 0) : 0;

function summary(e: JobEvent): string | null {
  const d = e.detail ?? {};
  switch (e.event) {
    case 'segments':
      return `${d.segments} segments (${d.distinct_texts} distinct texts) in ${d.scopes} parts`;
    case 'glossary':
      return `${d.glossary_id} v${d.version} · ${d.entries} terms${d.style_notes ? ' · style notes' : ''}`;
    case 'front_matter':
      return `${d.template_id} v${d.version}`;
    case 'translator': {
      const used = tokens(d.usage);
      return `${d.translated} of ${d.groups} distinct texts translated, ${d.copied} copied · ${d.calls} calls${d.failed_calls ? ` (${d.failed_calls} failed)` : ''}${d.terms ? ` · ${d.terms_translated}/${d.terms} document terms` : ''}${used ? ` · ${used.toLocaleString()} tokens` : ''}`;
    }
    case 'checks':
      return `Round ${d.round}: ${d.open} open issue(s)${d.gate_issues ? `, ${d.gate_issues} blocking` : ''}${d.repair ? ` · ${d.repair} to repair` : ''}`;
    case 'repair':
      return `${d.segments} segment(s) retranslated · ${d.improved} improved, ${d.kept_previous} kept`;
    case 'render':
      return `Document v${d.docx_version} · ${d.kept_english ? `${d.kept_english} segment(s) shown in English` : 'every segment written'}${d.toc_entries ? ` · ${d.toc_entries} TOC entries` : ''}${d.front_matter ? ' · language template applied' : ''}`;
    case 'render_problems':
    case 'english_render_problems':
      return (d.problems ?? []).slice(0, 3).join(' · ');
    case 'segment_edited':
      return `${d.segment_id}${(d.applied_to?.length ?? 1) > 1 ? ` and ${d.applied_to.length - 1} with the same English` : ''}: "${d.after}"`;
    case 'segments_replaced':
      return `"${d.find}" → "${d.replace}" · ${d.count} occurrence(s)${d.section ? ` in ${d.section}` : ''}${d.term_updated?.length ? ' · document term agreed' : ''}`;
    case 'issue_resolved':
      return `${d.issue_id}: ${splitNote(d.note).text}`;
    case 'approved':
      return `Document v${d.docx_version}${d.note ? ` · ${d.note}` : ''}`;
    case 'export':
      return `Document v${d.docx_version}`;
    default:
      return null;
  }
}

export const TRANSLATION_LABELS: EventLabels = {
  status: (s) => translationStatusInfo(s as TranslationStatus).label,
  title: (e) => (e.to_status ? null : TITLES[e.event] ?? humanize(e.event)),
  summary,
};

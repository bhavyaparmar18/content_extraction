import type { MigrationJobRow } from '@/features/migrations/types';
import type { GlossaryRecord, LanguageChoice, LanguageCode, LanguageTemplateRecord, TranslationJobRow } from './types';

/** A resource version a start dialog offers: ``"<id>@<version>"``, or ``""`` for none. */
export type ResourcePick = string;

export const pickOf = (id: string, version: number): ResourcePick => `${id}@${version}`;

function parsePick(pick: ResourcePick): { id: string; version: number } | null {
  const at = pick.lastIndexOf('@');
  return at > 0 ? { id: pick.slice(0, at), version: Number(pick.slice(at + 1)) } : null;
}

/** The versions a language may use, newest change first: approved glossaries, ready language templates. */
export function usableGlossaries(records: GlossaryRecord[], language: LanguageCode): GlossaryRecord[] {
  return records.filter((r) => r.language === language && r.status === 'approved').sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.version - a.version);
}

export function usableTemplates(records: LanguageTemplateRecord[], language: LanguageCode): LanguageTemplateRecord[] {
  return records.filter((r) => r.language === language && r.status === 'ready').sort((a, b) => b.updated_at.localeCompare(a.updated_at) || b.version - a.version);
}

/** The start dialog's preselection for a language: the newest usable glossary and language template, else none. */
export function defaultPicks(language: LanguageCode, glossaries: GlossaryRecord[], templates: LanguageTemplateRecord[]): { glossary: ResourcePick; template: ResourcePick } {
  const glossary = usableGlossaries(glossaries, language)[0];
  const template = usableTemplates(templates, language)[0];
  return {
    glossary: glossary ? pickOf(glossary.glossary_id, glossary.version) : '',
    template: template ? pickOf(template.template_id, template.version) : '',
  };
}

/** One language of a start request, with its picked versions (none left out). */
export function languageChoice(language: LanguageCode, picks: { glossary: ResourcePick; template: ResourcePick }): LanguageChoice {
  const glossary = parsePick(picks.glossary);
  const template = parsePick(picks.template);
  return {
    language,
    ...(glossary ? { glossary_id: glossary.id, glossary_version: glossary.version } : {}),
    ...(template ? { language_template_id: template.id, language_template_version: template.version } : {}),
  };
}

/** Migration job id → the title of its SOP (translation rows name only their migration). */
export function jobSopTitles(migrations: Pick<MigrationJobRow, 'job_id' | 'sop_record_id'>[], sopTitles: Map<number, string>): Map<string, string> {
  return new Map(
    migrations.map((m) => [m.job_id, sopTitles.get(m.sop_record_id) ?? `SOP #${m.sop_record_id}`] as const),
  );
}

/** The translation jobs of each migration, newest first (the list is already newest first). */
export function jobsByMigration(jobs: TranslationJobRow[]): Map<string, TranslationJobRow[]> {
  const out = new Map<string, TranslationJobRow[]>();
  jobs.forEach((j) => out.set(j.migration_job_id, [...(out.get(j.migration_job_id) ?? []), j]));
  return out;
}

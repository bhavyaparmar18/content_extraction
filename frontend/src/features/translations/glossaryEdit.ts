import type { GlossaryEntry } from './types';

/** A glossary entry being edited; ``key`` keeps React rows stable while terms change. */
export interface TermRow extends Required<Omit<GlossaryEntry, 'note'>> {
  key: number;
  note: string;
}

let nextKey = 1;

export function toRows(entries: GlossaryEntry[]): TermRow[] {
  return entries.map((e) => ({
    key: nextKey++,
    source_term: e.source_term,
    target_term: e.do_not_translate ? '' : e.target_term,
    note: e.note ?? '',
    case_sensitive: !!e.case_sensitive,
    do_not_translate: !!e.do_not_translate,
  }));
}

export const emptyRow = (): TermRow => ({
  key: nextKey++,
  source_term: '',
  target_term: '',
  note: '',
  case_sensitive: false,
  do_not_translate: false,
});

/** Whitespace collapsed, as the server's validator does. */
const squash = (text: string) => text.split(/\s+/).filter(Boolean).join(' ');

/** The case-folded term a duplicate is detected by (case kept when case-sensitive), as ``GlossaryEntry.key``. */
const termKey = (row: TermRow) => (row.case_sensitive ? squash(row.source_term) : squash(row.source_term).toLocaleLowerCase());

/** Why each row cannot be saved (by row key; rows left completely empty are ignored, they are dropped on save). */
export function rowProblems(rows: TermRow[]): Map<number, string[]> {
  const problems = new Map<number, string[]>();
  const add = (row: TermRow, message: string) => problems.set(row.key, [...(problems.get(row.key) ?? []), message]);
  const seen = new Map<string, number>();
  rows.forEach((row) => {
    if (isBlank(row)) return;
    const source = squash(row.source_term);
    if (!source) add(row, 'A source term is needed');
    if (!row.do_not_translate && !squash(row.target_term)) add(row, 'A target term is needed (or tick "do not translate")');
    if (source) {
      const key = termKey(row);
      const first = seen.get(key);
      if (first !== undefined) add(row, `"${source}" is listed more than once`);
      else seen.set(key, row.key);
    }
  });
  return problems;
}

const isBlank = (row: TermRow) => !row.source_term.trim() && !row.target_term.trim() && !row.note.trim();

/** The rows as API entries: blank rows dropped, whitespace collapsed, a do-not-translate target = its source. */
export function toEntries(rows: TermRow[]): GlossaryEntry[] {
  return rows
    .filter((row) => !isBlank(row))
    .map((row) => {
      const source = squash(row.source_term);
      const entry: GlossaryEntry = {
        source_term: source,
        target_term: row.do_not_translate ? source : squash(row.target_term),
        case_sensitive: row.case_sensitive,
        do_not_translate: row.do_not_translate,
      };
      if (row.note.trim()) entry.note = row.note.trim();
      return entry;
    });
}

/** Whether the edited rows differ from the saved entries. */
export function rowsChanged(rows: TermRow[], saved: GlossaryEntry[]): boolean {
  return JSON.stringify(toEntries(rows)) !== JSON.stringify(toEntries(toRows(saved)));
}

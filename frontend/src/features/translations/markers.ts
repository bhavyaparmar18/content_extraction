/**
 * The placeholders a translation must keep (docs/translation/CONTRACTS.md): ``{{ref:<id>}}`` reference tokens,
 * ``⟦k⟧…⟦/k⟧`` formatting pairs and standalone ``⟦k⟧`` objects of template text (``⟦1⟧`` is also a
 * cross-reference's number), and the ``|`` cell separators of an edited table row. The structural check mirrors the
 * server's EMPTY, REF_TOKENS, TAGS and CELLS checks (`app/services/translation/checks.py`).
 */

export type Part =
  | { type: 'text'; text: string }
  | { type: 'break' }
  | { type: 'open'; k: number; raw: string }
  | { type: 'close'; k: number; raw: string }
  | { type: 'object'; k: number; raw: string }
  | { type: 'ref'; id: string; raw: string }
  | { type: 'cell'; raw: string };

export type MarkerPart = Exclude<Part, { type: 'text' } | { type: 'break' }>;

const TAG = /⟦(\/?)(\d+)⟧/g;
const REF = /\{\{ref:([A-Za-z0-9._-]+)\}\}/g;
const SPLIT = /(⟦\/?\d+⟧|\{\{ref:[A-Za-z0-9._-]+\}\}|\||\n)/;

/** The ``⟦k⟧`` tags of a text in order, a ``⟦k⟧`` without its ``⟦/k⟧`` being an object (as ``parse_tags``). */
export function parseTags(text: string): { kind: 'open' | 'close' | 'object'; k: number }[] {
  const tags: { kind: 'open' | 'close'; k: number }[] = [...(text ?? '').matchAll(TAG)].map((m) => ({ kind: m[1] ? 'close' : 'open', k: Number(m[2]) }));
  const closed = new Set(tags.filter((t) => t.kind === 'close').map((t) => t.k));
  return tags.map((t) => (t.kind === 'open' && !closed.has(t.k) ? { kind: 'object', k: t.k } : t));
}

export const stripTags = (text: string) => (text ?? '').replace(TAG, '');
const refsOf = (text: string) => [...(text ?? '').matchAll(REF)].map((m) => m[1]);

/**
 * The text as parts. ``cells``: whether ``|`` separates cells (only when the English has one: an edited table row);
 * otherwise a ``|`` is text.
 */
export function tokenize(text: string, cells: boolean): Part[] {
  const tags = parseTags(text);
  let tagIndex = 0;
  const parts: Part[] = [];
  (text ?? '').split(SPLIT).forEach((piece) => {
    if (!piece) return;
    if (piece === '\n') parts.push({ type: 'break' });
    else if (piece === '|' && cells) parts.push({ type: 'cell', raw: piece });
    else if (piece.startsWith('{{ref:')) parts.push({ type: 'ref', id: piece.slice(6, -2), raw: piece });
    else if (piece.startsWith('⟦') && /^⟦\/?\d+⟧$/.test(piece)) {
      const tag = tags[tagIndex++];
      parts.push({ type: tag.kind, k: tag.k, raw: piece });
    } else {
      const last = parts[parts.length - 1];
      if (last?.type === 'text') last.text += piece;
      else parts.push({ type: 'text', text: piece });
    }
  });
  return parts;
}

export const partsToText = (parts: Part[]) =>
  parts.map((p) => (p.type === 'text' ? p.text : p.type === 'break' ? '\n' : p.raw)).join('');

/** Whether the English uses ``|`` as cell separators. */
export const hasCells = (english: string) => (english ?? '').includes('|');

/** The markers of some parts as a sorted multiset key: what an edit may move but never add, drop or change. */
export function markerKey(parts: Part[]): string {
  return parts
    .filter((p): p is MarkerPart => p.type !== 'text' && p.type !== 'break')
    .map((p) => p.raw)
    .sort()
    .join('\u0000');
}

function counts<T>(values: T[]): Map<T, number> {
  const out = new Map<T, number>();
  values.forEach((v) => out.set(v, (out.get(v) ?? 0) + 1));
  return out;
}

function minus<T>(a: Map<T, number>, b: Map<T, number>): T[] {
  const out: T[] = [];
  a.forEach((n, v) => {
    for (let i = 0; i < n - (b.get(v) ?? 0); i++) out.push(v);
  });
  return out;
}

/** Why a translation of ``english`` could not be shown in the document (empty when it can). */
export function structuralProblems(english: string, target: string): string[] {
  const problems: string[] = [];
  if (!stripTags(target).trim()) return ['no translation'];

  const wantRefs = counts(refsOf(english));
  const gotRefs = counts(refsOf(target));
  const lostRefs = minus(wantRefs, gotRefs);
  const addedRefs = minus(gotRefs, wantRefs);
  if (lostRefs.length || addedRefs.length) {
    problems.push(['reference tokens changed:', lostRefs.length ? `lost ${lostRefs.map((r) => `{{ref:${r}}}`).join(' ')}` : '', addedRefs.length ? `added ${addedRefs.map((r) => `{{ref:${r}}}`).join(' ')}` : ''].filter(Boolean).join(' '));
  }

  const show = (t: { kind: string; k: number }) => (t.kind === 'close' ? `⟦/${t.k}⟧` : `⟦${t.k}⟧`);
  const wantTags = counts(parseTags(english).map(show));
  const tags = parseTags(target);
  const gotTags = counts(tags.map(show));
  const missing = minus(wantTags, gotTags);
  const extra = minus(gotTags, wantTags);
  if (missing.length) problems.push(`lost the marker(s) ${missing.join(' ')}`);
  if (extra.length) problems.push(`added or changed the marker(s) ${extra.join(' ')}`);
  const stack: number[] = [];
  for (const t of tags) {
    if (t.kind === 'open') stack.push(t.k);
    else if (t.kind === 'close') {
      if (stack[stack.length - 1] !== t.k) {
        problems.push(`the pair ⟦${t.k}⟧…⟦/${t.k}⟧ is out of order or crosses another pair`);
        break;
      }
      stack.pop();
    }
  }

  if (hasCells(english)) {
    const want = english.split('|').length - 1;
    const got = target.split('|').length - 1;
    if (want !== got) problems.push(`${want} table cell separator(s) '|' in the English, ${got} in the translation`);
  }
  return problems;
}

/** Text a reviewer pastes or types: markers and token delimiters removed, so only the locked chips carry them. */
export const cleanTyped = (text: string) => text.replace(/[⟦⟧]/g, '').replace(/\{\{|\}\}/g, '');

/** The ``⟦k⟧`` pair each text part sits inside (for underlining the formatted words), by part index. */
export function formattedRuns(parts: Part[]): Map<number, number> {
  const out = new Map<number, number>();
  const open: number[] = [];
  parts.forEach((p, i) => {
    if (p.type === 'open') open.push(p.k);
    else if (p.type === 'close') {
      const at = open.lastIndexOf(p.k);
      if (at >= 0) open.splice(at, 1);
    } else if (p.type === 'text' && open.length) out.set(i, open[open.length - 1]);
  });
  return out;
}

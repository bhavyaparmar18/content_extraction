/**
 * Best-effort location of source passages in a document rendered by docx-preview: the rendered HTML has no
 * unit IDs, so passages are found by their text.
 */

const NEEDLE_LENGTH = 80;
const MIN_BLOCK_LENGTH = 12;

/** Lower case, letters and digits only, single spaces: survives smart quotes, list numbers and odd spacing. */
export function normalizeText(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

/** The part of a passage to look for: its start, long enough to be specific. */
export function needleOf(text: string): string {
  const normalized = normalizeText(text);
  if (normalized.length <= NEEDLE_LENGTH) return normalized;
  const cut = normalized.lastIndexOf(' ', NEEDLE_LENGTH);
  return normalized.slice(0, cut > 40 ? cut : NEEDLE_LENGTH);
}

/**
 * Indexes of the blocks that hold each needle (the first match per needle, in document order).
 * A block matches when it contains the needle, or when a short needle (a table cell, a one-line step)
 * contains the whole block.
 */
export function findBlocks(blockTexts: string[], needles: string[]): number[] {
  const blocks = blockTexts.map(normalizeText);
  const found = new Set<number>();
  for (const needle of needles) {
    if (needle.length < 3) continue;
    let index = blocks.findIndex((b) => b.length > 0 && b.includes(needle));
    if (index < 0) {
      index = blocks.findIndex((b) => b.length >= MIN_BLOCK_LENGTH && needle.includes(b));
    }
    if (index >= 0) found.add(index);
  }
  return [...found].sort((x, y) => x - y);
}

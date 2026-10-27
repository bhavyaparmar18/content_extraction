import type { MarkerPart } from './markers';

/** Colours per formatting pair, so the words between ⟦k⟧ and ⟦/k⟧ read as one run in both columns. */
const RUN_COLOURS = ['decoration-sky-400', 'decoration-amber-400', 'decoration-fuchsia-400', 'decoration-emerald-400', 'decoration-rose-400'];
export const runColour = (k: number) => RUN_COLOURS[(k - 1) % RUN_COLOURS.length];

export const CHIP_CLASS =
  'mx-[1px] inline-flex select-none items-center rounded border px-1 align-baseline font-mono text-[10px] leading-[14px]';

/** How a marker shows: its label, colour and what it stands for. */
export function chipLook(part: MarkerPart, xref = false): { label: string; className: string; title: string } {
  switch (part.type) {
    case 'open':
      return { label: `${part.k}›`, className: 'border-sky-400/40 bg-sky-400/10 text-sky-300', title: `Start of formatted run ${part.k}: the words up to ‹${part.k} keep the English formatting` };
    case 'close':
      return { label: `‹${part.k}`, className: 'border-sky-400/40 bg-sky-400/10 text-sky-300', title: `End of formatted run ${part.k}` };
    case 'object':
      return xref
        ? { label: 'No.', className: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300', title: 'The reference number (filled in by the document)' }
        : { label: `◆${part.k}`, className: 'border-violet-400/40 bg-violet-400/10 text-violet-300', title: `Object ${part.k} of the English (a tab, field, link or image), kept in place` };
    case 'ref':
      return { label: '→ ref', className: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-300', title: `Reference to ${part.id}: becomes a cross-reference in the document` };
    case 'cell':
      return { label: '|', className: 'border-amber-400/40 bg-amber-400/10 text-amber-300', title: 'Table cell separator' };
  }
}

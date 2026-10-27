import type { JSONContent } from '@tiptap/react';
import type { Node as PmNode } from '@tiptap/pm/model';
import { cleanTyped, tokenize, type Part } from './markers';

/** The raw markers in a document (sorted): an edit may move text around them, never add, drop or change one. */
export function markersIn(doc: PmNode): string {
  const raws: string[] = [];
  doc.descendants((node) => {
    if (node.type.name === 'marker') raws.push(node.attrs.raw as string);
  });
  return raws.sort().join('\u0000');
}

/** A segment's text as the editor's document: one paragraph of text, hard breaks and marker nodes. */
export function toEditorDoc(text: string, cells: boolean): JSONContent {
  const content: JSONContent[] = tokenize(text, cells).map((p: Part) => {
    if (p.type === 'text') return { type: 'text', text: p.text };
    if (p.type === 'break') return { type: 'hardBreak' };
    return { type: 'marker', attrs: { raw: p.raw, kind: p.type, k: 'k' in p ? p.k : 0, id: p.type === 'ref' ? p.id : '' } };
  });
  return { type: 'doc', content: [{ type: 'paragraph', content }] };
}

/** The editor's text back, with what the reviewer typed cleaned of marker characters. */
export function fromEditorDoc(doc: JSONContent): string {
  const parts: string[] = [];
  const walk = (node: JSONContent) => {
    if (node.type === 'text') parts.push(cleanTyped(node.text ?? ''));
    else if (node.type === 'hardBreak') parts.push('\n');
    else if (node.type === 'marker') parts.push(String(node.attrs?.raw ?? ''));
    node.content?.forEach(walk);
  };
  walk(doc);
  return parts.join('');
}

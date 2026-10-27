import React, { useEffect, useMemo, useRef } from 'react';
import { EditorContent, Extension, Node, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Plugin } from '@tiptap/pm/state';
import { clsx } from 'clsx';
import { cleanTyped, type MarkerPart } from '../markers';
import { CHIP_CLASS, chipLook } from '../chips';
import { fromEditorDoc, markersIn, toEditorDoc } from '../editorDoc';

/** One paragraph of text, hard breaks and locked marker chips. */
const SegmentDoc = Node.create({ name: 'doc', topNode: true, content: 'paragraph' });

const Marker = Node.create<{ xref: boolean }>({
  name: 'marker',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: false,
  draggable: false,
  addOptions: () => ({ xref: false }),
  addAttributes: () => ({
    raw: { default: '' },
    kind: { default: 'object' },
    k: { default: 0 },
    id: { default: '' },
  }),
  parseHTML: () => [{ tag: 'span[data-marker]', getAttrs: (el) => ({ raw: (el as HTMLElement).dataset.marker }) }],
  renderHTML({ node }) {
    const part = { type: node.attrs.kind, k: node.attrs.k, id: node.attrs.id, raw: node.attrs.raw } as MarkerPart;
    const look = chipLook(part, this.options.xref);
    return ['span', { 'data-marker': node.attrs.raw, contenteditable: 'false', title: look.title, class: clsx(CHIP_CLASS, look.className) }, look.label];
  },
});

/** Keeps the markers: refuses any change (typing over, deleting, cutting, dropping) that would alter them. */
const LockMarkers = Extension.create({
  name: 'lockMarkers',
  addProseMirrorPlugins() {
    return [new Plugin({ filterTransaction: (tr, state) => !tr.docChanged || markersIn(tr.doc) === markersIn(state.doc) })];
  },
});

/**
 * The target text of one segment, editable around its locked markers. Ctrl/Cmd+Enter saves, Escape cancels,
 * Enter adds a line break.
 */
export const SegmentEditor: React.FC<{
  initial: string;
  cells: boolean;
  xref?: boolean;
  onChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
  className?: string;
}> = ({ initial, cells, xref = false, onChange, onSave, onCancel, className }) => {
  // The latest callbacks, for the keyboard shortcuts the editor registered once.
  const handlers = useRef({ onSave, onCancel, onChange });
  useEffect(() => {
    handlers.current = { onSave, onCancel, onChange };
  });
  const extensions = useMemo(
    () => [
      StarterKit.configure({
        document: false, heading: false, blockquote: false, bold: false, italic: false, strike: false, code: false,
        codeBlock: false, horizontalRule: false, bulletList: false, orderedList: false, listItem: false, listKeymap: false,
        link: false, underline: false, trailingNode: false,
      }),
      SegmentDoc,
      Marker.configure({ xref }),
      LockMarkers,
      Extension.create({
        name: 'segmentKeys',
        addKeyboardShortcuts: () => ({
          'Mod-Enter': () => (handlers.current.onSave(), true),
          Escape: () => (handlers.current.onCancel(), true),
          Enter: ({ editor }) => editor.commands.setHardBreak(),
        }),
      }),
    ],
    [xref],
  );
  const editor = useEditor({
    extensions,
    content: toEditorDoc(initial, cells),
    autofocus: 'end',
    editorProps: {
      attributes: { class: 'min-h-[2.5rem] whitespace-pre-wrap break-words px-2.5 py-2 text-xs leading-relaxed text-text-main focus:outline-none', 'aria-label': 'Translation' },
      transformPastedText: (text) => cleanTyped(text),
    },
    onUpdate: ({ editor: e }) => handlers.current.onChange(fromEditorDoc(e.getJSON())),
  });
  return <EditorContent editor={editor} className={clsx('rounded-md border border-primary/50 bg-black/20', className)} />;
};

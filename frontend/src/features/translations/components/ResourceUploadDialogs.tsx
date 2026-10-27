import React, { useState } from 'react';
import { BookOpen, FileText, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { useLanguages, useResourceMutations } from '../hooks';
import type { GlossaryRecord, LanguageCode, LanguageTemplateRecord } from '../types';
import { ErrorPanel, Modal } from './parts';

/** The language select of an upload: fixed for a new version of an existing record. */
const LanguageSelect: React.FC<{ value: LanguageCode | ''; onChange: (code: LanguageCode) => void; fixed?: boolean }> = ({
  value,
  onChange,
  fixed,
}) => {
  const languages = useLanguages();
  return (
    <div>
      <label className="field-label" htmlFor="upload-language">Language</label>
      <select id="upload-language" className="field" value={value} disabled={fixed} onChange={(e) => onChange(e.target.value as LanguageCode)}>
        <option value="" disabled>Choose a language…</option>
        {(languages.data ?? []).map((l) => <option key={l.code} value={l.code}>{l.name} ({l.code})</option>)}
      </select>
    </div>
  );
};

/** Upload a glossary (.csv / .xlsx), start an empty one, or add a version to an existing one (``base``). */
export const GlossaryUploadDialog: React.FC<{
  open: boolean;
  base?: GlossaryRecord;
  language?: LanguageCode;
  onClose: () => void;
  onCreated: (record: GlossaryRecord) => void;
}> = ({ open, base, language: preset, onClose, onCreated }) => {
  const { success } = useToast();
  const { createGlossary } = useResourceMutations();
  const [language, setLanguage] = useState<LanguageCode | ''>(base?.language ?? preset ?? '');
  const [name, setName] = useState(base?.name ?? '');
  const [notes, setNotes] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const close = () => {
    createGlossary.reset();
    onClose();
  };
  const submit = () =>
    createGlossary.mutate(
      { language: language as LanguageCode, name: name.trim() || undefined, glossary_id: base?.glossary_id, style_notes: notes.trim() || undefined, file: file ?? undefined },
      {
        onSuccess: (record) => {
          success(`${record.total_entries ?? 0} terms, in review until approved.`, `Glossary ${record.glossary_id} v${record.version} saved`);
          onCreated(record);
        },
      },
    );

  return (
    <Modal
      open={open}
      onClose={close}
      icon={<BookOpen className="size-4 text-primary" />}
      title={base ? `New version of ${base.glossary_id}` : 'New glossary'}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={close}>Cancel</Button>
          <Button variant="primary" size="sm" leftIcon={<Upload className="size-3.5" />} disabled={!language || (!file && !name.trim() && !base)}
            isLoading={createGlossary.isPending} onClick={submit}>
            {file ? 'Upload' : 'Create empty glossary'}
          </Button>
        </>
      }
    >
      <LanguageSelect value={language} onChange={setLanguage} fixed={!!base} />
      <div>
        <label className="field-label" htmlFor="glossary-name">Name</label>
        <input id="glossary-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. GxP terms (German)" />
        {!base && <p className="mt-1 text-[11px] text-text-muted">The glossary's id is made from the name, or from the file name when the name is empty.</p>}
      </div>
      <div>
        <label className="field-label" htmlFor="glossary-file">File (optional)</label>
        <input id="glossary-file" type="file" accept=".csv,.xlsx" className="block w-full text-xs text-text-muted file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-1.5 file:text-xs file:text-primary"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <p className="mt-1 text-[11px] text-text-muted">
          CSV or XLSX with the columns <span className="font-mono">source_term, target_term, note, case_sensitive, do_not_translate</span>.
          An XLSX "Style notes" sheet is read too. Leave empty to start an empty glossary and add terms in the editor.
        </p>
      </div>
      <div>
        <label className="field-label" htmlFor="glossary-notes">Style notes (optional)</label>
        <textarea id="glossary-notes" className="field min-h-[72px]" value={notes} onChange={(e) => setNotes(e.target.value)}
          placeholder="Passed to the translator as written, e.g. “Use the formal Sie form.”" />
      </div>
      <ErrorPanel error={createGlossary.error} details={apiErrorDetails(createGlossary.error)} />
    </Modal>
  );
};

/** Upload a language template (.docx): its first page, headers and footers are extracted at once. */
export const LanguageTemplateUploadDialog: React.FC<{
  open: boolean;
  base?: LanguageTemplateRecord;
  language?: LanguageCode;
  onClose: () => void;
  onCreated: (record: LanguageTemplateRecord) => void;
}> = ({ open, base, language: preset, onClose, onCreated }) => {
  const { success, warning } = useToast();
  const { createTemplate } = useResourceMutations();
  const [language, setLanguage] = useState<LanguageCode | ''>(base?.language ?? preset ?? '');
  const [name, setName] = useState(base?.name ?? '');
  const [file, setFile] = useState<File | null>(null);

  const close = () => {
    createTemplate.reset();
    onClose();
  };
  const submit = () =>
    createTemplate.mutate(
      { language: language as LanguageCode, file: file!, name: name.trim() || undefined, template_id: base?.template_id },
      {
        onSuccess: (record) => {
          if (record.status === 'failed') warning(record.error ?? 'The first page could not be extracted.', `${record.template_id} v${record.version} saved, extraction failed`);
          else success('Check the extracted first page, headers and footers, then mark it ready.', `${record.template_id} v${record.version} extracted`);
          onCreated(record);
        },
      },
    );

  return (
    <Modal
      open={open}
      onClose={close}
      icon={<FileText className="size-4 text-primary" />}
      title={base ? `New version of ${base.template_id}` : 'New language template'}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={close}>Cancel</Button>
          <Button variant="primary" size="sm" leftIcon={<Upload className="size-3.5" />} disabled={!language || !file}
            isLoading={createTemplate.isPending} onClick={submit}>
            Upload and extract
          </Button>
        </>
      }
    >
      <LanguageSelect value={language} onChange={setLanguage} fixed={!!base} />
      <div>
        <label className="field-label" htmlFor="ltpl-name">Name</label>
        <input id="ltpl-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Defaults to the file name" />
      </div>
      <div>
        <label className="field-label" htmlFor="ltpl-file">Word template (.docx)</label>
        <input id="ltpl-file" type="file" accept=".docx" className="block w-full text-xs text-text-muted file:mr-3 file:rounded-md file:border-0 file:bg-primary/15 file:px-3 file:py-1.5 file:text-xs file:text-primary"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <p className="mt-1 text-[11px] text-text-muted">
          Only its first page (up to the first section or page break), headers and footers are used. They replace the English ones in a
          translation, unchanged and untranslated. The rest of the file is ignored.
        </p>
      </div>
      <ErrorPanel error={createTemplate.error} details={apiErrorDetails(createTemplate.error)} />
    </Modal>
  );
};

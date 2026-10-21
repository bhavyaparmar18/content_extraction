import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRightLeft, CheckCircle2, Layers, X } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { api } from '@/lib/api';
import { getDisplayTitle } from '@/lib/sopDisplay';
import type { SopRecord } from '@/types';
import { migrationsApi } from '../api';
import { migrationKeys } from '../hooks';
import type { JobMode } from '../types';

interface Props {
  sop: SopRecord | null;
  onClose: () => void;
}

const READINESS: Record<string, string> = {
  needs_normalization: 'Not prepared: use "Prepare" on the Templates page',
  needs_review: 'Needs decisions: use "Prepare" on the Templates page',
};

/** Start a v2 migration of one SOP: the template, an optional GWP and whether to pause for plan review. */
export const StartMigrationDialog: React.FC<Props> = ({ sop, onClose }) => {
  const navigate = useNavigate();
  const client = useQueryClient();
  const { success } = useToast();
  const [picked, setTemplateId] = useState('');
  const [gwpId, setGwpId] = useState('');
  const [mode, setMode] = useState<JobMode>('review');

  const templates = useQuery({ queryKey: ['templates', 'all'], queryFn: () => api.getTemplates(), enabled: !!sop });
  const guides = useQuery({ queryKey: ['gwp', 'approved'], queryFn: () => migrationsApi.guides(), enabled: !!sop });

  // Newest version of each template, ready ones first.
  const options = Object.values(
    (templates.data ?? []).reduce<Record<string, NonNullable<typeof templates.data>[number]>>((acc, t) => {
      if (!acc[t.template_uid] || acc[t.template_uid].template_version < t.template_version) acc[t.template_uid] = t;
      return acc;
    }, {}),
  ).sort((a, b) => Number(b.readiness_status === 'ready') - Number(a.readiness_status === 'ready'));
  const templateId = picked || options.find((t) => t.readiness_status === 'ready')?.template_uid || '';
  const guideOptions = Object.values(
    (guides.data ?? []).reduce<Record<string, NonNullable<typeof guides.data>[number]>>((acc, g) => {
      if (!acc[g.guide_id] || acc[g.guide_id].version < g.version) acc[g.guide_id] = g;
      return acc;
    }, {}),
  );

  const create = useMutation({
    mutationFn: () =>
      migrationsApi.create({
        sop_record_id: sop!.id,
        template_id: templateId,
        template_version: options.find((t) => t.template_uid === templateId)?.template_version,
        gwp_id: gwpId || undefined,
        gwp_version: guideOptions.find((g) => g.guide_id === gwpId)?.version,
        mode,
      }),
    onSuccess: (job) => {
      client.invalidateQueries({ queryKey: migrationKeys.list() });
      success('The migration has started.', 'Migration started');
      onClose();
      navigate(`/migrations/${job.job_id}`);
    },
  });

  if (!sop) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onMouseDown={onClose}>
      <div className="dashboard-card w-full max-w-lg" onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
            <ArrowRightLeft className="size-4 text-primary" /> Migrate to a template
          </div>
          <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded text-text-muted hover:bg-white/5">
            <X className="size-4" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <div className="rounded-md border border-border bg-black/10 px-3 py-2 text-xs">
            <div className="font-medium text-text-main">{getDisplayTitle(sop)}</div>
            <div className="text-text-muted">{sop.document_Uid} · v{sop.document_version ?? '?'} · {sop.file_type?.toUpperCase()}</div>
          </div>

          <div>
            <label className="field-label">Template</label>
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {templates.isLoading && <p className="text-xs text-text-muted">Loading templates…</p>}
              {!templates.isLoading && options.length === 0 && <p className="text-xs text-text-muted">No template uploaded yet.</p>}
              {options.map((t) => {
                const ready = t.readiness_status === 'ready';
                return (
                  <button
                    key={t.template_uid}
                    type="button"
                    disabled={!ready}
                    onClick={() => setTemplateId(t.template_uid)}
                    className={clsx(
                      'flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-xs transition',
                      templateId === t.template_uid ? 'border-primary/60 bg-primary/10' : 'border-border hover:bg-white/5',
                      !ready && 'cursor-not-allowed opacity-50 hover:bg-transparent',
                    )}
                  >
                    <Layers className="size-4 shrink-0 text-text-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-text-main">{t.template_name}</span>
                      <span className="block text-text-muted">
                        {t.template_uid} v{t.template_version} · {ready ? 'ready' : READINESS[t.readiness_status ?? ''] ?? 'Not prepared: use "Prepare" on the Templates page'}
                      </span>
                    </span>
                    {templateId === t.template_uid && <CheckCircle2 className="size-4 text-primary" />}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="field-label" htmlFor="gwp">Good Writing Practice guide (optional)</label>
            <select id="gwp" className="field" value={gwpId} onChange={(e) => setGwpId(e.target.value)}>
              <option value="">None: place the SOP's content as written</option>
              {guideOptions.map((g) => (
                <option key={g.guide_id} value={g.guide_id}>{g.guide_name} ({g.guide_id} v{g.version}, {g.approved_rules ?? g.total_rules ?? 0} rules)</option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-text-muted">With a guide, the text is rewritten to its rules; without one, the wording stays the SOP's own.</p>
          </div>

          <fieldset>
            <legend className="field-label">Review</legend>
            <div className="grid grid-cols-2 gap-2">
              {([
                ['review', 'Review the plans', 'Pause for you to check the section and slot mapping before drafting'],
                ['auto', 'Run straight through', 'Draft without pausing; you review the result'],
              ] as const).map(([value, label, hint]) => (
                <label key={value} className={clsx('cursor-pointer rounded-md border px-3 py-2 text-xs', mode === value ? 'border-primary/60 bg-primary/10' : 'border-border hover:bg-white/5')}>
                  <input type="radio" className="sr-only" name="mode" value={value} checked={mode === value} onChange={() => setMode(value)} />
                  <span className="block font-medium text-text-main">{label}</span>
                  <span className="block text-[11px] text-text-muted">{hint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {create.error && <div className="error-panel text-xs text-danger">{create.error.message}</div>}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={!templateId} isLoading={create.isPending} onClick={() => create.mutate()} leftIcon={<ArrowRightLeft className="size-3.5" />}>
            Start migration
          </Button>
        </div>
      </div>
    </div>
  );
};

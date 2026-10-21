import React from 'react';
import { CheckCircle2, Lock, RotateCcw, Save } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import type { Origin } from '../types';

interface PlanToolbarProps {
  title: string;
  description: string;
  plan?: { version: number; origin: Origin; model?: string; approved_by?: string };
  editable: boolean;
  dirty: boolean;
  saving: boolean;
  approving: boolean;
  /** Why approval is not possible (blocking issues, unsaved edits); empty when it is. */
  approveBlockers: string[];
  onSave: () => void;
  onDiscard: () => void;
  onApprove: () => void;
  children?: React.ReactNode;
}

const ORIGIN_LABEL: Record<Origin, string> = { rule: 'rules', llm: 'rules + LLM', human: 'reviewer' };

/** Title, plan version and the save / discard / approve actions of a plan review step. */
export const PlanToolbar: React.FC<PlanToolbarProps> = ({
  title,
  description,
  plan,
  editable,
  dirty,
  saving,
  approving,
  approveBlockers,
  onSave,
  onDiscard,
  onApprove,
  children,
}) => (
  <div className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3">
    <div className="min-w-0">
      <h2 className="text-sm font-semibold text-text-main">{title}</h2>
      <p className="mt-0.5 max-w-2xl text-xs text-text-muted">{description}</p>
      {plan && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-text-muted">
          <span className="chip-muted">v{plan.version}</span>
          <span>by {ORIGIN_LABEL[plan.origin] ?? plan.origin}</span>
          {plan.model && <span>· {plan.model}</span>}
          {plan.approved_by && <span className="text-primary">· approved by {plan.approved_by}</span>}
          {children}
        </div>
      )}
    </div>
    <div className="flex items-center gap-2">
      {!editable ? (
        <span className="flex items-center gap-1.5 text-xs text-text-muted">
          <Lock className="size-3.5" /> Read only
        </span>
      ) : (
        <>
          {dirty && (
            <>
              <span className="text-[11px] text-warning">Unsaved changes</span>
              <Button size="sm" variant="ghost" leftIcon={<RotateCcw className="size-3.5" />} onClick={onDiscard} disabled={saving}>
                Discard
              </Button>
              <Button size="sm" variant="secondary" leftIcon={<Save className="size-3.5" />} onClick={onSave} isLoading={saving}>
                Save changes
              </Button>
            </>
          )}
          <span title={approveBlockers.join('\n')}>
            <Button
              size="sm"
              variant="primary"
              leftIcon={<CheckCircle2 className="size-3.5" />}
              onClick={onApprove}
              disabled={approveBlockers.length > 0}
              isLoading={approving}
            >
              Approve and continue
            </Button>
          </span>
        </>
      )}
    </div>
  </div>
);

import React from 'react';
import { Check, History, Loader2, Lock } from 'lucide-react';
import { clsx } from 'clsx';
import { STEPS, stepStates, type Step, type StepState } from '../status';
import type { MigrationJob } from '../types';

export type View = Step | 'activity';

/** ① Section mapping → ② Slot mapping → ③ Draft & issues → ④ Final document, plus the activity log. */
export const StageStepper: React.FC<{ job: MigrationJob; view: View; onChange: (view: View) => void }> = ({ job, view, onChange }) => {
  const states = stepStates(job);
  return (
    <nav className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-3 py-1.5">
      {STEPS.map((step, index) => {
        const state = states[step.id];
        return (
          <React.Fragment key={step.id}>
            {index > 0 && <div className={clsx('h-px w-6 shrink-0', state === 'locked' ? 'bg-border' : 'bg-primary/40')} />}
            <button
              type="button"
              disabled={state === 'locked'}
              onClick={() => onChange(step.id)}
              title={TITLES[state]}
              className={clsx(
                'flex shrink-0 items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-medium transition',
                view === step.id ? 'bg-primary/10 text-text-main ring-1 ring-primary/40' : 'text-text-muted hover:bg-white/5 hover:text-text-main',
                state === 'locked' && 'cursor-not-allowed opacity-45 hover:bg-transparent hover:text-text-muted',
              )}
            >
              <StepBadge index={index + 1} state={state} />
              <span className="hidden sm:inline">{step.label}</span>
              <span className="sm:hidden">{step.short}</span>
              {state === 'current' && <span className="size-1.5 rounded-full bg-warning" aria-label="needs your review" />}
            </button>
          </React.Fragment>
        );
      })}
      <button
        type="button"
        onClick={() => onChange('activity')}
        className={clsx(
          'ml-auto flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition',
          view === 'activity' ? 'bg-primary/10 text-text-main ring-1 ring-primary/40' : 'text-text-muted hover:bg-white/5 hover:text-text-main',
        )}
      >
        <History className="size-3.5" /> Activity
      </button>
    </nav>
  );
};

const TITLES: Record<StepState, string> = {
  done: 'Done; open to see it',
  current: 'Waiting for your review',
  working: 'The pipeline is working on this step',
  available: 'Available',
  locked: 'Not reached yet',
};

const StepBadge: React.FC<{ index: number; state: StepState }> = ({ index, state }) => (
  <span
    className={clsx(
      'grid size-5 shrink-0 place-items-center rounded-full border text-[10px] font-semibold',
      state === 'done' && 'border-primary/50 bg-primary/15 text-primary',
      state === 'current' && 'border-warning/60 bg-warning/15 text-warning',
      state === 'working' && 'border-info/50 bg-info/10 text-info',
      state === 'available' && 'border-primary/40 text-primary',
      state === 'locked' && 'border-border text-text-muted',
    )}
  >
    {state === 'done' ? <Check className="size-3" /> : state === 'working' ? <Loader2 className="size-3 animate-spin" /> : state === 'locked' ? <Lock className="size-2.5" /> : index}
  </span>
);

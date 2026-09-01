import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, ShieldCheck, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface QaCheckItem {
  rule: string;
  status: 'passed' | 'warning' | 'error';
  message: string;
}

export const TranslationQaPanel: React.FC = () => {
  const qaChecks: QaCheckItem[] = [
    { rule: 'Protected Terms', status: 'passed', message: 'All SOP IDs and product codes preserved unchanged.' },
    { rule: 'Number Consistency', status: 'passed', message: '100% match on numeric figures and indices.' },
    { rule: 'Unit Matching', status: 'passed', message: 'SI and pharmaceutical units consistent (°C, mL, mg).' },
    { rule: 'Glossary Compliance', status: 'warning', message: '1 optional glossary synonym available for "Scope".' },
    { rule: 'Punctuation & Marks', status: 'passed', message: 'Section numbering punctuation preserved.' },
    { rule: 'Untranslated Fragments', status: 'passed', message: 'No leftover source language detected.' },
  ];

  const hasErrors = qaChecks.some((c) => c.status === 'error');
  const hasWarnings = qaChecks.some((c) => c.status === 'warning');

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <ShieldCheck className="size-3.5 text-primary" />
          <span>Translation QA Checks</span>
        </div>
        <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
          Ready for Approval
        </span>
      </div>

      <div className="flex-1 p-3 overflow-y-auto space-y-2 text-xs">
        {qaChecks.map((item, idx) => (
          <div
            key={idx}
            className={`rounded-lg border p-3 space-y-1 ${
              item.status === 'error'
                ? 'border-red-500/30 bg-red-500/10'
                : item.status === 'warning'
                ? 'border-amber-500/30 bg-amber-500/10'
                : 'border-border bg-card'
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-text-main flex items-center gap-1.5">
                {item.status === 'passed' && <CheckCircle2 className="size-3.5 text-emerald-400" />}
                {item.status === 'warning' && <AlertTriangle className="size-3.5 text-amber-400" />}
                {item.status === 'error' && <XCircle className="size-3.5 text-red-400" />}
                {item.rule}
              </span>
              <span className="text-[10px] uppercase font-semibold text-text-muted">
                {item.status}
              </span>
            </div>
            <p className="text-xs text-text-muted leading-relaxed">{item.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

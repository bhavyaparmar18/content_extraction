import React from 'react';
import {
  Save,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Languages,
  ArrowRightLeft,
  Check,
  ShieldAlert,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface ActionFooterProps {
  availableActions: string[];
  isSaving?: boolean;
  isApproving?: boolean;
  onSave?: () => void;
  onApprove?: () => void;
  onRequestReprocessing?: () => void;
  onReportIssue?: () => void;
  onRunQa?: () => void;
  onValidateMigration?: () => void;
  onAiTranslate?: () => void;
  onAiMigrate?: () => void;
}

export const ActionFooter: React.FC<ActionFooterProps> = ({
  availableActions = [],
  isSaving = false,
  isApproving = false,
  onSave,
  onApprove,
  onRequestReprocessing,
  onReportIssue,
  onRunQa,
  onValidateMigration,
  onAiTranslate,
  onAiMigrate,
}) => {
  const hasAction = (act: string) => availableActions.includes(act);

  return (
    <footer className="sticky-action-bar">
      {/* Left Action Group */}
      <div className="flex items-center gap-2">
        {hasAction('REQUEST_REPROCESSING') && onRequestReprocessing && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onRequestReprocessing}
            leftIcon={<RotateCcw className="size-3.5 text-amber-400" />}
          >
            Request Reprocessing
          </Button>
        )}

        {hasAction('REPORT_ISSUE') && onReportIssue && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onReportIssue}
            leftIcon={<ShieldAlert className="size-3.5 text-red-400" />}
          >
            Report Issue
          </Button>
        )}

        {hasAction('RUN_QA') && onRunQa && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onRunQa}
            leftIcon={<Sparkles className="size-3.5 text-sky-400" />}
          >
            Run QA Checks
          </Button>
        )}

        {hasAction('VALIDATE') && onValidateMigration && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onValidateMigration}
            leftIcon={<Sparkles className="size-3.5 text-emerald-400" />}
          >
            Validate Sections
          </Button>
        )}
      </div>

      {/* Right Action Group */}
      <div className="flex items-center gap-2.5">
        {hasAction('AI_TRANSLATE') && onAiTranslate && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onAiTranslate}
            leftIcon={<Languages className="size-3.5 text-primary" />}
          >
            AI Translate
          </Button>
        )}

        {hasAction('AI_MIGRATE') && onAiMigrate && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onAiMigrate}
            leftIcon={<ArrowRightLeft className="size-3.5 text-primary" />}
          >
            AI Auto-Map
          </Button>
        )}

        {hasAction('SAVE') && onSave && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onSave}
            isLoading={isSaving}
            leftIcon={<Save className="size-3.5" />}
          >
            Save Draft
          </Button>
        )}

        {hasAction('APPROVE') && onApprove && (
          <Button
            variant="primary"
            size="sm"
            onClick={onApprove}
            isLoading={isApproving}
            leftIcon={<CheckCircle2 className="size-4" />}
          >
            Approve & Finalize
          </Button>
        )}
      </div>
    </footer>
  );
};

import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Eye,
  Download,
  Languages,
  ArrowRightLeft,
  CheckSquare,
  MoreHorizontal,
  Sparkles,
} from 'lucide-react';
import { ReviewBootstrap, ReviewMode } from '@/types';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileTypeIcon } from '@/components/ui/FileTypeIcon';
import { Button } from '@/components/ui/Button';

interface ReviewHeaderProps {
  bootstrap: ReviewBootstrap;
  currentMode: ReviewMode;
  onModeChange: (mode: ReviewMode) => void;
  onDownload: () => void;
  onToggleOriginalViewer?: () => void;
}

export const ReviewHeader: React.FC<ReviewHeaderProps> = ({
  bootstrap,
  currentMode,
  onModeChange,
  onDownload,
  onToggleOriginalViewer,
}) => {
  const navigate = useNavigate();
  const { document, reviewContext } = bootstrap;

  const modeTitles = {
    review: 'Extraction Review',
    translation: 'AI Translation Review',
    migration: 'AI Migration Review',
  };

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-card/90 px-6 py-3.5 backdrop-blur">
      {/* Left: Back + Doc Identity */}
      <div className="flex items-center gap-3 min-w-0">
        <Button
          variant="icon"
          size="sm"
          onClick={() => navigate(`/sops/${document.recordId}`)}
          title="Back to Content View"
          aria-label="Back"
        >
          <ArrowLeft className="size-4" />
        </Button>

        <FileTypeIcon fileType={document.fileType} size="md" className="shrink-0" />

        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="font-bold text-text-main text-sm sm:text-base truncate max-w-xs sm:max-w-md">
              {document.title}
            </h1>
            <StatusBadge status={reviewContext.status} size="sm" />
          </div>
          <div className="text-[11px] text-text-muted mt-0.5 truncate">
            {document.sopNumber ? `${document.sopNumber} • ` : ''}v{document.version} • {document.pageCount} pages •{' '}
            <span className="text-primary font-medium">{modeTitles[currentMode]}</span>
          </div>
        </div>
      </div>

      {/* Center: Mode Switcher Tabs */}
      <div className="flex items-center rounded-lg border border-border bg-black/20 p-1">
        <button
          type="button"
          onClick={() => onModeChange('review')}
          className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition ${
            currentMode === 'review'
              ? 'bg-primary/20 text-primary font-semibold'
              : 'text-text-muted hover:text-text-main'
          }`}
        >
          <CheckSquare className="size-3.5" />
          <span>Extraction</span>
        </button>

        <button
          type="button"
          onClick={() => onModeChange('translation')}
          className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition ${
            currentMode === 'translation'
              ? 'bg-primary/20 text-primary font-semibold'
              : 'text-text-muted hover:text-text-main'
          }`}
        >
          <Languages className="size-3.5" />
          <span>Translation</span>
        </button>

        <button
          type="button"
          onClick={() => onModeChange('migration')}
          className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition ${
            currentMode === 'migration'
              ? 'bg-primary/20 text-primary font-semibold'
              : 'text-text-muted hover:text-text-main'
          }`}
        >
          <ArrowRightLeft className="size-3.5" />
          <span>Migration</span>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        {onToggleOriginalViewer && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onToggleOriginalViewer}
            leftIcon={<Eye className="size-3.5 text-primary" />}
          >
            Original Doc
          </Button>
        )}

        <Button
          variant="secondary"
          size="sm"
          onClick={onDownload}
          leftIcon={<Download className="size-3.5" />}
        >
          Export
        </Button>
      </div>
    </header>
  );
};

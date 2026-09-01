import React, { useState } from 'react';
import { ZoomIn, ZoomOut, RotateCcw, ChevronLeft, ChevronRight, FileText, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface OriginalDocumentViewerProps {
  documentId: string;
  fileType?: string;
  currentPage?: number;
  highlightBbox?: number[] | null;
  onPageChange?: (page: number) => void;
}

export const OriginalDocumentViewer: React.FC<OriginalDocumentViewerProps> = ({
  documentId,
  fileType = 'pdf',
  currentPage = 1,
  highlightBbox,
  onPageChange,
}) => {
  const [zoom, setZoom] = useState(100);
  const [page, setPage] = useState(currentPage);

  const fileUrl = `/documents/${encodeURIComponent(documentId)}/file`;
  const isPdf = fileType.toLowerCase() === 'pdf';

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    onPageChange?.(newPage);
  };

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      {/* Viewer Toolbar */}
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-3 py-2 text-xs">
        <div className="flex items-center gap-1.5 font-medium text-text-main">
          <FileText className="size-3.5 text-primary" />
          <span>Original Document</span>
        </div>

        {/* Zoom & Page Controls */}
        <div className="flex items-center gap-1">
          <Button
            variant="icon"
            size="sm"
            onClick={() => setZoom((prev) => Math.max(prev - 15, 50))}
            title="Zoom Out"
          >
            <ZoomOut className="size-3" />
          </Button>

          <span className="font-mono text-[11px] text-text-muted px-1 w-10 text-center">
            {zoom}%
          </span>

          <Button
            variant="icon"
            size="sm"
            onClick={() => setZoom((prev) => Math.min(prev + 15, 200))}
            title="Zoom In"
          >
            <ZoomIn className="size-3" />
          </Button>

          <div className="h-3.5 w-px bg-border mx-1" />

          <Button
            variant="icon"
            size="sm"
            onClick={() => window.open(fileUrl, '_blank')}
            title="Open in new tab"
          >
            <ExternalLink className="size-3" />
          </Button>
        </div>
      </div>

      {/* Embedded Document Viewport */}
      <div className="flex-1 overflow-auto bg-black/40 p-4 flex items-center justify-center relative">
        {isPdf ? (
          <div
            className="w-full h-full flex flex-col items-center justify-center transition-transform"
            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}
          >
            <iframe
              src={`${fileUrl}#page=${page}&toolbar=0&navpanes=0`}
              title="Original PDF Document"
              className="w-full h-full min-h-[500px] rounded border border-border bg-white"
            />

            {/* Bounding Box Highlight Overlay */}
            {highlightBbox && (
              <div
                className="absolute border-2 border-primary bg-primary/20 pointer-events-none rounded shadow-glow animate-pulse"
                style={{
                  left: `${highlightBbox[0]}px`,
                  top: `${highlightBbox[1]}px`,
                  width: `${highlightBbox[2]}px`,
                  height: `${highlightBbox[3]}px`,
                }}
              />
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center p-8 text-center text-text-muted space-y-3">
            <FileText className="size-12 text-primary/60" />
            <div>
              <div className="text-sm font-semibold text-text-main">Word Document (.docx)</div>
              <div className="text-xs text-text-muted mt-0.5">
                Structured content extracted directly from OpenXML AST
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.open(fileUrl, '_blank')}
              leftIcon={<ExternalLink className="size-3.5" />}
            >
              Download Original DOCX
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

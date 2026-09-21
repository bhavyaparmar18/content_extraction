import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { MigrationElement, MigrationIconRef, MigrationTableCell, TemplateElement, TemplateIconRef } from '@/types';
import { api } from '@/lib/api';
import { Table, Image as ImageIcon, HelpCircle, ImageOff } from 'lucide-react';
import { clsx } from 'clsx';

interface ElementRendererProps {
  element: MigrationElement | TemplateElement;
  documentId: string;
  index?: number;
  isTemplate?: boolean;
}

function resolveAssetUrl(documentId: string, value: unknown, isTemplate?: boolean): string {
  if (value && typeof value === 'object') {
    if ('image_path' in value && typeof (value as any).image_path === 'string') {
      value = (value as any).image_path;
    } else if ('path' in value && typeof (value as any).path === 'string') {
      value = (value as any).path;
    }
  }

  if (typeof value !== 'string' || !value) return '';

  // Check if already an absolute or root-relative URL starting with /templates, /documents, http, etc.
  if (
    value.startsWith('/templates/') ||
    value.startsWith('/documents/') ||
    value.startsWith('http://') ||
    value.startsWith('https://')
  ) {
    return value;
  }

  const fileName = api.assetFileName(value);
  if (!fileName) return '';

  if (isTemplate) {
    return api.getTemplateAssetUrl(documentId, fileName);
  }
  return api.getAssetUrl(documentId, fileName);
}

function IconThumbs({
  icons,
  documentId,
  isTemplate,
}: {
  icons?: Array<string | MigrationIconRef | TemplateIconRef>;
  documentId: string;
  isTemplate?: boolean;
}) {
  if (!icons || icons.length === 0) return null;
  return (
    <div className="flex shrink-0 flex-col items-center gap-1.5 pt-0.5">
      {icons.map((icon, idx) => {
        const url = resolveAssetUrl(documentId, icon, isTemplate);
        if (!url) return null;
        const alt =
          typeof icon === 'object' && icon && 'semantic_meaning' in icon && (icon as any).semantic_meaning && (icon as any).semantic_meaning !== 'unknown'
            ? (icon as any).semantic_meaning
            : 'Extracted icon';
        return (
          <img
            key={idx}
            src={url}
            alt={alt}
            title={alt}
            className="size-6 rounded border border-border bg-white/5 object-contain p-0.5 shadow-sm"
            loading="lazy"
            onError={(e) => {
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
        );
      })}
    </div>
  );
}

class ElementErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Failed to render SOP element', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/[0.05] px-3 py-2 text-xs text-amber-300">
          This element could not be displayed.
        </div>
      );
    }
    return this.props.children;
  }
}

export const ElementRenderer: React.FC<ElementRendererProps> = (props) => (
  <ElementErrorBoundary>
    <ElementRendererInner {...props} />
  </ElementErrorBoundary>
);

const ElementRendererInner: React.FC<ElementRendererProps> = ({
  element,
  documentId,
  isTemplate,
}) => {
  switch (element.element_type) {
    case 'heading': {
      const level = Math.min(Math.max(element.level || 2, 1), 6) as 1 | 2 | 3 | 4 | 5 | 6;
      const HeadingTag = `h${level}` as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';

      const headingClasses = {
        1: 'text-2xl font-bold tracking-tight text-text-main mt-6 mb-3',
        2: 'text-xl font-semibold text-text-main mt-5 mb-2.5',
        3: 'text-lg font-semibold text-primary mt-4 mb-2',
        4: 'text-base font-medium text-text-main mt-3 mb-1.5',
        5: 'text-sm font-semibold text-text-muted mt-2 mb-1',
        6: 'text-xs font-bold uppercase tracking-wider text-text-muted mt-2 mb-1',
      }[level] || 'text-lg font-semibold text-text-main';

      return (
        <div className="py-1">
          <IconThumbs icons={element.icons} documentId={documentId} isTemplate={isTemplate} />
          <HeadingTag className={headingClasses}>{element.text}</HeadingTag>
        </div>
      );
    }

    case 'paragraph': {
      const isInst = (element as any).is_instruction;
      return (
        <div
          className={clsx(
            'flex items-start gap-2 py-1.5 leading-relaxed text-sm',
            isInst
              ? 'text-sky-300 font-medium pl-3 border-l-2 border-sky-400 bg-sky-500/5 rounded-r-lg py-2 my-1'
              : 'text-text-main/90'
          )}
        >
          <IconThumbs icons={element.icons} documentId={documentId} isTemplate={isTemplate} />
          <p className="min-w-0 flex-1 whitespace-pre-line">{element.text}</p>
        </div>
      );
    }

    case 'list': {
      const items = element.items || (element.text ? [element.text] : []);
      const isInst = (element as any).is_instruction;
      return (
        <div
          className={clsx(
            'flex items-start gap-2 py-2',
            isInst && 'rounded-lg bg-sky-500/5 p-2 border-l-2 border-sky-400'
          )}
        >
          <IconThumbs icons={element.icons} documentId={documentId} isTemplate={isTemplate} />
          <ul className="min-w-0 flex-1 list-disc space-y-1.5 pl-5 text-sm text-text-main/90 marker:text-primary">
            {items.map((item, idx) => (
              <li key={idx} className={clsx('leading-relaxed', isInst && 'text-sky-200')}>
                {item}
              </li>
            ))}
          </ul>
        </div>
      );
    }

    case 'table': {
      const cells = element.cells || [];
      const rows: Record<number, MigrationTableCell[]> = {};
      cells.forEach((cell) => {
        const rowIndex = cell.row_index ?? 0;
        if (!rows[rowIndex]) rows[rowIndex] = [];
        rows[rowIndex].push(cell);
      });

      const isInst = (element as any).is_instruction;

      return (
        <div className={clsx('my-4 space-y-2', isInst && 'rounded-xl border border-sky-500/30 bg-sky-500/[0.02] p-3')}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconThumbs icons={element.icons} documentId={documentId} isTemplate={isTemplate} />
              {element.title && (
                <div className="flex items-center gap-2 text-xs font-semibold text-text-main">
                  <Table className="size-3.5 text-primary" />
                  <span>{element.title}</span>
                </div>
              )}
              {isInst && (
                <span className="rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 px-2 py-0.5 text-[10px] font-mono">
                  Instruction Table
                </span>
              )}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-border bg-black/20 shadow-inner">
            <table className="w-full border-collapse text-left text-xs">
              <tbody>
                {Object.keys(rows)
                  .map(Number)
                  .sort((a, b) => a - b)
                  .map((rIdx) => {
                    const rowCells = [...rows[rIdx]].sort(
                      (a, b) => (a.col_index ?? 0) - (b.col_index ?? 0)
                    );
                    const isHeaderRow = rIdx === 0 && rowCells.some((c) => c.is_header);

                    return (
                      <tr
                        key={rIdx}
                        className={clsx(
                          'border-b border-border/50 transition hover:bg-white/[0.02]',
                          isHeaderRow && 'bg-primary/10 font-semibold text-primary'
                        )}
                      >
                        {rowCells.map((c, cIdx) => {
                          const CellTag = c.is_header ? 'th' : 'td';
                          const cellIconUrl = resolveAssetUrl(documentId, c.icon_path, isTemplate);
                          const cellImageUrl = resolveAssetUrl(documentId, c.image_path, isTemplate);
                          const hasOnlyIcon = !c.text && (cellIconUrl || cellImageUrl);

                          return (
                            <CellTag
                              key={cIdx}
                              rowSpan={c.row_span > 1 ? c.row_span : undefined}
                              colSpan={c.col_span > 1 ? c.col_span : undefined}
                              className={clsx(
                                'border-r border-border/40 px-3 py-2.5 align-middle leading-relaxed',
                                c.is_header
                                  ? 'bg-primary/[0.08] font-semibold text-primary'
                                  : 'text-text-main',
                                hasOnlyIcon && 'w-14 text-center'
                              )}
                            >
                              {cellIconUrl && (
                                <div className="flex items-center justify-center py-0.5">
                                  <img
                                    src={cellIconUrl}
                                    alt="Icon"
                                    className="size-6 object-contain rounded border border-border/60 bg-white/5 p-0.5 shadow-sm"
                                    loading="lazy"
                                    onError={(e) => {
                                      (e.target as HTMLElement).style.display = 'none';
                                    }}
                                  />
                                </div>
                              )}
                              {c.text && <div>{c.text}</div>}
                              {cellImageUrl && (
                                <img
                                  src={cellImageUrl}
                                  alt=""
                                  className="mt-1 max-h-24 max-w-full object-contain rounded"
                                  loading="lazy"
                                  onError={(e) => {
                                    (e.target as HTMLElement).style.display = 'none';
                                  }}
                                />
                              )}
                            </CellTag>
                          );
                        })}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    case 'image': {
      const url = resolveAssetUrl(
        documentId,
        (element as any).asset_filename || element.image_path,
        isTemplate
      );

      return (
        <div className="my-4 space-y-2 rounded-xl border border-border bg-black/20 p-4">
          <IconThumbs icons={element.icons} documentId={documentId} isTemplate={isTemplate} />
          <div className="flex min-h-[140px] items-center justify-center overflow-hidden rounded-lg bg-card/60">
            {url ? (
              <img
                src={url}
                alt={element.title || 'Extracted graphic'}
                className="max-h-96 max-w-full rounded object-contain"
                loading="lazy"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            ) : (
              <div className="flex flex-col items-center gap-2 p-6 text-text-muted">
                <ImageOff className="size-8 opacity-50" />
                <span className="text-xs">Image unavailable</span>
              </div>
            )}
          </div>
          {element.title && (
            <div className="text-center text-xs italic text-text-muted">{element.title}</div>
          )}
        </div>
      );
    }

    case 'icon': {
      const url = resolveAssetUrl(
        documentId,
        (element as any).asset_filename || element.image_path || element.icons?.[0],
        isTemplate
      );

      return (
        <div className="my-1 inline-flex items-center gap-2 rounded border border-border bg-black/10 px-2.5 py-1">
          {url ? (
            <img
              src={url}
              alt={element.text || 'Icon'}
              className="size-5 object-contain"
              loading="lazy"
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
          ) : (
            <ImageIcon className="size-4 text-text-muted" />
          )}
          {element.text && <span className="text-xs text-text-main">{element.text}</span>}
        </div>
      );
    }

    default:
      return (
        <div className="my-2 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.05] p-3 text-xs text-amber-300">
          <HelpCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <span className="font-semibold uppercase">{element.element_type}</span>
            {element.text ? `: ${element.text}` : ''}
          </div>
        </div>
      );
  }
};

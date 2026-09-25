import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import {
  MigrationElement,
  MigrationIconRef,
  MigrationTableCell,
  TemplateCalloutStyle,
  TemplateElement,
  TemplateIconEntry,
  TemplateIconRef,
  TemplateTableCell,
} from '@/types';
import { api } from '@/lib/api';
import { Table, Image as ImageIcon, HelpCircle, ImageOff } from 'lucide-react';
import { clsx } from 'clsx';

/** icon_key -> library entry. Template v2.0 references icons by key only. */
export type IconLibraryMap = Record<string, TemplateIconEntry>;
/** callout_type -> registered style, for background and border colours. */
export type CalloutStyleMap = Record<string, TemplateCalloutStyle>;

interface ElementRendererProps {
  element: MigrationElement | TemplateElement;
  documentId: string;
  index?: number;
  isTemplate?: boolean;
  iconLibrary?: IconLibraryMap;
  calloutStyles?: CalloutStyleMap;
}

/** Accepts both bare hex ("E2EFDA") and prefixed ("#E2EFDA") template values. */
function toCssColor(value?: string | null): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
}

function resolveAssetUrl(
  documentId: string,
  value: unknown,
  isTemplate?: boolean,
  iconLibrary?: IconLibraryMap
): string {
  if (value && typeof value === 'object') {
    const ref = value as any;
    if (typeof ref.icon_key === 'string' && iconLibrary?.[ref.icon_key]) {
      value = iconLibrary[ref.icon_key].asset_path;
    } else if (typeof ref.image_path === 'string') {
      value = ref.image_path;
    } else if (typeof ref.path === 'string') {
      value = ref.path;
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

function iconLabel(icon: unknown, iconLibrary?: IconLibraryMap): string {
  const ref = icon as any;
  const entry =
    ref && typeof ref === 'object' && typeof ref.icon_key === 'string'
      ? iconLibrary?.[ref.icon_key]
      : undefined;
  const meaning =
    entry?.display_name ||
    (entry?.semantic_meaning !== 'unknown' ? entry?.semantic_meaning : undefined) ||
    (ref?.semantic_meaning !== 'unknown' ? ref?.semantic_meaning : undefined);
  return meaning || 'Extracted icon';
}

function IconThumbs({
  icons,
  documentId,
  isTemplate,
  iconLibrary,
}: {
  icons?: Array<string | MigrationIconRef | TemplateIconRef>;
  documentId: string;
  isTemplate?: boolean;
  iconLibrary?: IconLibraryMap;
}) {
  if (!icons || icons.length === 0) return null;
  return (
    <div className="flex shrink-0 flex-col items-center gap-1.5 pt-0.5">
      {icons.map((icon, idx) => {
        const url = resolveAssetUrl(documentId, icon, isTemplate, iconLibrary);
        if (!url) return null;
        const alt = iconLabel(icon, iconLibrary);
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
  iconLibrary,
  calloutStyles,
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
          <IconThumbs
            icons={element.icons}
            documentId={documentId}
            isTemplate={isTemplate}
            iconLibrary={iconLibrary}
          />
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
          <IconThumbs
            icons={element.icons}
            documentId={documentId}
            isTemplate={isTemplate}
            iconLibrary={iconLibrary}
          />
          <p className="min-w-0 flex-1 whitespace-pre-line">{element.text}</p>
        </div>
      );
    }

    case 'callout': {
      const calloutType = (element as TemplateElement).callout_type || undefined;
      const style = calloutType ? calloutStyles?.[calloutType] : undefined;
      const background =
        toCssColor((element as TemplateElement).shading_hex) ||
        toCssColor(style?.background_color_hex);
      const borderColor = toCssColor(style?.left_border_color_hex) || background;
      const fontColor =
        toCssColor((element as TemplateElement).font_color_hex) ||
        toCssColor(style?.font_color_hex);

      // Template callout fills are light, so text goes dark against them. Without
      // a fill we fall back to the app's own dark-theme callout treatment.
      const icons =
        element.icons && element.icons.length > 0
          ? element.icons
          : style?.icon_key
            ? [{ icon_key: style.icon_key } as TemplateIconRef]
            : undefined;

      return (
        <div
          className={clsx(
            'my-3 flex items-start gap-3 rounded-r-lg border-l-4 px-4 py-3',
            !background && 'border-primary/60 bg-primary/[0.06]'
          )}
          style={background ? { backgroundColor: background, borderLeftColor: borderColor } : undefined}
        >
          <IconThumbs
            icons={icons}
            documentId={documentId}
            isTemplate={isTemplate}
            iconLibrary={iconLibrary}
          />
          <div className="min-w-0 flex-1 space-y-1">
            {calloutType && (
              <div
                className={clsx(
                  'text-[10px] font-bold uppercase tracking-wider',
                  background ? 'text-slate-900/60' : 'text-primary'
                )}
              >
                {style?.display_name || calloutType.replace(/_/g, ' ')}
              </div>
            )}
            <p
              className={clsx(
                'whitespace-pre-line text-sm leading-relaxed',
                background ? 'text-slate-900' : 'text-text-main/90'
              )}
              style={background && fontColor ? { color: fontColor } : undefined}
            >
              {element.text}
            </p>
          </div>
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
          <IconThumbs
            icons={element.icons}
            documentId={documentId}
            isTemplate={isTemplate}
            iconLibrary={iconLibrary}
          />
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
      const cells = (element.cells || []) as Array<MigrationTableCell | TemplateTableCell>;
      const rows: Record<number, Array<MigrationTableCell | TemplateTableCell>> = {};
      cells.forEach((cell) => {
        const rowIndex = cell.row_index ?? 0;
        if (!rows[rowIndex]) rows[rowIndex] = [];
        rows[rowIndex].push(cell);
      });

      const isInst = (element as any).is_instruction;
      // Icons that already sit in a cell must not be drawn again above the grid.
      const cellIconKeys = new Set(
        cells
          .map((cell) => ('icon_key' in cell ? (cell as TemplateTableCell).icon_key : undefined))
          .filter((key): key is string => Boolean(key))
      );
      const iconsBesideTable = (element.icons || []).filter((icon) => {
        const key =
          icon && typeof icon === 'object' && 'icon_key' in icon
            ? (icon as TemplateIconRef).icon_key
            : undefined;
        return !key || !cellIconKeys.has(key);
      });

      const showTableChrome = iconsBesideTable.length > 0 || Boolean(element.title) || isInst;

      return (
        <div className={clsx('my-4 space-y-2', isInst && 'rounded-xl border border-sky-500/30 bg-sky-500/[0.02] p-3')}>
          {showTableChrome && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <IconThumbs
                  icons={iconsBesideTable}
                  documentId={documentId}
                  isTemplate={isTemplate}
                  iconLibrary={iconLibrary}
                />
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
          )}

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
                          const templateCell = c as TemplateTableCell;
                          const cellIconUrl = resolveAssetUrl(
                            documentId,
                            templateCell.icon_key
                              ? { icon_key: templateCell.icon_key }
                              : c.icon_path,
                            isTemplate,
                            iconLibrary
                          ) || resolveAssetUrl(documentId, c.icon_path, isTemplate, iconLibrary);
                          const cellImageUrl = resolveAssetUrl(documentId, c.image_path, isTemplate, iconLibrary);
                          const hasOnlyIcon = !c.text && (cellIconUrl || cellImageUrl);
                          const cellShading = toCssColor(templateCell.shading_hex);
                          // Rotated headers in the role matrix need the same
                          // orientation they have in the template.
                          const isVerticalText =
                            templateCell.text_direction === 'btLr' ||
                            templateCell.text_direction === 'tbRl';

                          return (
                            <CellTag
                              key={cIdx}
                              rowSpan={c.row_span > 1 ? c.row_span : undefined}
                              colSpan={c.col_span > 1 ? c.col_span : undefined}
                              className={clsx(
                                'border-r border-border/40 px-3 py-2.5 leading-relaxed',
                                cellShading
                                  ? 'text-slate-900'
                                  : c.is_header
                                    ? 'bg-primary/[0.08] font-semibold text-primary'
                                    : 'text-text-main',
                                templateCell.bold && 'font-semibold',
                                hasOnlyIcon && 'w-14 text-center',
                                templateCell.valign === 'top'
                                  ? 'align-top'
                                  : templateCell.valign === 'bottom'
                                    ? 'align-bottom'
                                    : 'align-middle'
                              )}
                              style={{
                                ...(cellShading ? { backgroundColor: cellShading } : {}),
                                ...(isVerticalText
                                  ? {
                                      writingMode: 'vertical-rl',
                                      transform:
                                        templateCell.text_direction === 'btLr'
                                          ? 'rotate(180deg)'
                                          : undefined,
                                    }
                                  : {}),
                              }}
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
        isTemplate,
        iconLibrary
      );

      return (
        <div className="my-4 space-y-2 rounded-xl border border-border bg-black/20 p-4">
          <IconThumbs
            icons={element.icons}
            documentId={documentId}
            isTemplate={isTemplate}
            iconLibrary={iconLibrary}
          />
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
        isTemplate,
        iconLibrary
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

import { ImageOff } from 'lucide-react'
import { Fragment, type ReactNode } from 'react'
import { assetUrl } from '../../lib/api'
import type { MigrationElement, MigrationIconRef, MigrationTableCell } from '../../types'

function IconThumbs({ icons }: { icons: MigrationIconRef[] }) {
  if (icons.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {icons.map((icon) => (
        <img
          key={icon.icon_id}
          src={assetUrl(icon.path)}
          alt={icon.semantic_meaning ?? 'icon'}
          className="h-10 w-10 rounded-md border border-[var(--border)] bg-white/5 object-contain p-1"
          loading="lazy"
        />
      ))}
    </div>
  )
}

function HeadingElement({ element }: { element: MigrationElement }) {
  const level = element.level ?? 2
  const text = element.text ?? ''
  if (level <= 1) return <h2 className="mt-2 text-xl font-semibold tracking-tight">{text}</h2>
  if (level === 2) return <h3 className="mt-2 text-lg font-semibold">{text}</h3>
  return <h4 className="mt-2 text-base font-semibold">{text}</h4>
}

function ParagraphElement({ element }: { element: MigrationElement }) {
  if (!element.text) return null
  return (
    <div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-main)]">{element.text}</p>
      {element.icons && <IconThumbs icons={element.icons} />}
    </div>
  )
}

function ListElement({ element }: { element: MigrationElement }) {
  const items = element.items ?? []
  if (items.length === 0) return null
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-[var(--text-main)]">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}

/** Groups flat table cells into rows (sorted by col_index), ready for a native <table>. */
function groupCellsByRow(cells: MigrationTableCell[]): MigrationTableCell[][] {
  const byRow = new Map<number, MigrationTableCell[]>()
  for (const cell of cells) {
    const row = byRow.get(cell.row_index) ?? []
    row.push(cell)
    byRow.set(cell.row_index, row)
  }
  return [...byRow.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, row]) => row.sort((a, b) => a.col_index - b.col_index))
}

function TableElement({ element }: { element: MigrationElement }) {
  const cells = element.cells ?? []
  if (cells.length === 0) return null
  const rows = groupCellsByRow(cells)

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full border-collapse text-sm">
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-[var(--border)] last:border-b-0">
              {row.map((cell) => {
                const Tag = cell.is_header ? 'th' : 'td'
                return (
                  <Tag
                    key={`${cell.row_index}-${cell.col_index}`}
                    rowSpan={cell.row_span > 1 ? cell.row_span : undefined}
                    colSpan={cell.col_span > 1 ? cell.col_span : undefined}
                    className={`border-r border-[var(--border)] px-3 py-2 text-left align-top last:border-r-0 ${
                      cell.is_header ? 'bg-white/5 font-semibold' : ''
                    }`}
                  >
                    {cell.text}
                    {cell.icon_path && (
                      <img
                        src={assetUrl(cell.icon_path)}
                        alt=""
                        className="mt-1 h-6 w-6 object-contain"
                        loading="lazy"
                      />
                    )}
                  </Tag>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ImageElement({ element }: { element: MigrationElement }) {
  return (
    <figure className="space-y-2">
      {element.image_path ? (
        <img
          src={assetUrl(element.image_path)}
          alt={element.title || 'Extracted figure'}
          className="max-h-[480px] w-auto max-w-full rounded-lg border border-[var(--border)] object-contain"
          loading="lazy"
        />
      ) : (
        <div className="flex h-40 w-full max-w-md items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--border)] text-[var(--text-muted)]">
          <ImageOff size={18} />
          <span className="text-sm">Image unavailable</span>
        </div>
      )}
      {element.title && <figcaption className="text-xs text-[var(--text-muted)]">{element.title}</figcaption>}
      {element.icons && <IconThumbs icons={element.icons} />}
    </figure>
  )
}

function UnsupportedElement({ element }: { element: MigrationElement }) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border)] px-3 py-2 text-xs text-[var(--text-muted)]">
      Unsupported element type: <span className="font-mono">{element.element_type}</span>
    </div>
  )
}

/** Dispatches a single reading-order element to its type-specific renderer. */
export function ElementRenderer({ element }: { element: MigrationElement }) {
  let body: ReactNode
  switch (element.element_type) {
    case 'heading':
      body = <HeadingElement element={element} />
      break
    case 'paragraph':
      body = <ParagraphElement element={element} />
      break
    case 'list':
      body = <ListElement element={element} />
      break
    case 'table':
      body = <TableElement element={element} />
      break
    case 'image':
      body = <ImageElement element={element} />
      break
    default:
      body = <UnsupportedElement element={element} />
  }
  return <Fragment>{body}</Fragment>
}

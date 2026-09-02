import { defaultStyles, FileIcon } from 'react-file-icon'
import type { DefaultExtensionType, FileIconProps } from 'react-file-icon'

const SIZE_WIDTH: Record<'sm' | 'md', number> = { sm: 26, md: 32 }

const FALLBACK_STYLE: Partial<FileIconProps> = {
  color: '#64748b',
  foldColor: '#475569',
  glyphColor: 'rgba(255,255,255,0.4)',
  labelColor: '#475569',
  labelUppercase: true,
  type: 'document',
}

interface FileTypeIconProps {
  fileType: string
  size?: 'sm' | 'md'
}

/**
 * Realistic folded-corner file icon (colored body + extension label), the same
 * visual language used by Drive/Dropbox-style file browsers. Falls back to a
 * neutral gray document icon for any type we don't have a branded style for.
 */
export function FileTypeIcon({ fileType, size = 'md' }: FileTypeIconProps) {
  const ext = (fileType ?? '').toLowerCase() as DefaultExtensionType
  const style = defaultStyles[ext] ?? FALLBACK_STYLE
  const width = SIZE_WIDTH[size]

  return (
    <div className="flex-none" style={{ width }} title={fileType ? fileType.toUpperCase() : undefined}>
      <FileIcon extension={ext.toUpperCase()} {...style} />
    </div>
  )
}

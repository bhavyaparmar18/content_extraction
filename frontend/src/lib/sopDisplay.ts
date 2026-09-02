import type { SopRecord } from '../types'

export function displayTitle(sop: SopRecord): string {
  return sop.document_title || sop.document_name || sop.source_filename || sop.document_Uid
}

/**
 * Compact "number · name · pages · version" line shown under the title,
 * matching the mockup layout. Skips any part that's missing, and skips the
 * name if it's identical to the number (a common case in the source data).
 */
export function displaySubline(sop: SopRecord): string {
  const parts: string[] = []
  if (sop.document_number) parts.push(sop.document_number)
  if (sop.document_name && sop.document_name !== sop.document_number) parts.push(sop.document_name)
  if (sop.page_count) parts.push(`${sop.page_count} page${sop.page_count === 1 ? '' : 's'}`)
  if (sop.document_version) {
    const suffix = sop.gpdat_version > 1 ? ` (upload #${sop.gpdat_version})` : ''
    parts.push(`v${sop.document_version}${suffix}`)
  }
  return parts.length > 0 ? parts.join(' · ') : '—'
}

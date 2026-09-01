import { SopRecord, SopStatus } from '@/types';

export function getDisplayTitle(sop: Partial<SopRecord>): string {
  if (sop.document_title && sop.document_title.trim()) {
    return sop.document_title.trim();
  }
  if (sop.document_name && sop.document_name.trim()) {
    return sop.document_name.trim();
  }
  if (sop.document_Uid) {
    return sop.document_Uid;
  }
  return 'Untitled SOP';
}

export function getDisplaySubline(sop: Partial<SopRecord>): string {
  const parts: string[] = [];
  if (sop.document_number) parts.push(sop.document_number);
  if (sop.document_version) parts.push(`v${sop.document_version}`);
  if (sop.document_type) parts.push(sop.document_type);
  if (sop.page_count && sop.page_count > 0) parts.push(`${sop.page_count} pages`);
  return parts.join(' • ') || 'No metadata available';
}

export interface StatusConfig {
  label: string;
  bgClass: string;
  textClass: string;
  borderClass: string;
  dotClass: string;
}

export function getStatusConfig(status?: SopStatus | string): StatusConfig {
  switch (status) {
    case 'approved':
      return {
        label: 'Approved',
        bgClass: 'bg-emerald-500/10',
        textClass: 'text-emerald-400',
        borderClass: 'border-emerald-500/30',
        dotClass: 'bg-emerald-400',
      };
    case 'rejected':
      return {
        label: 'Rejected',
        bgClass: 'bg-red-500/10',
        textClass: 'text-red-400',
        borderClass: 'border-red-500/30',
        dotClass: 'bg-red-400',
      };
    case 'in_review':
    default:
      return {
        label: 'In Review',
        bgClass: 'bg-amber-500/10',
        textClass: 'text-amber-400',
        borderClass: 'border-amber-500/30',
        dotClass: 'bg-amber-400',
      };
  }
}

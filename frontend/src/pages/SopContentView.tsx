import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronLeft, ChevronRight, Loader2, TriangleAlert, XCircle } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ElementRenderer } from '../components/content/ElementRenderer'
import { SectionNav } from '../components/content/SectionNav'
import { FileTypeIcon } from '../components/FileTypeIcon'
import { Layout } from '../components/Layout'
import { StatusBadge } from '../components/StatusBadge'
import type { ToastMessage } from '../components/Toast'
import { ToastStack } from '../components/Toast'
import { Button } from '../components/ui/Button'
import { ApiError, getDocumentContent, getSop, updateSopStatus } from '../lib/api'
import { displaySubline, displayTitle } from '../lib/sopDisplay'
import type { MigrationDocument, SopRecord, SopStatus } from '../types'

const STATUS_ACTIONS: { status: SopStatus; label: string; icon: typeof CheckCircle2 }[] = [
  { status: 'approved', label: 'Approve', icon: CheckCircle2 },
  { status: 'in_review', label: 'Needs Review', icon: TriangleAlert },
  { status: 'rejected', label: 'Reject', icon: XCircle },
]

export function SopContentView() {
  const { recordId } = useParams<{ recordId: string }>()
  const numericId = recordId ? Number(recordId) : NaN

  const [record, setRecord] = useState<SopRecord | null>(null)
  const [content, setContent] = useState<MigrationDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState(0)
  const [updatingStatus, setUpdatingStatus] = useState<SopStatus | null>(null)

  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const toastIdRef = useRef(0)
  const pushToast = useCallback((kind: ToastMessage['kind'], text: string) => {
    toastIdRef.current += 1
    setToasts((prev) => [...prev, { id: toastIdRef.current, kind, text }])
  }, [])
  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const load = useCallback(async () => {
    if (!Number.isFinite(numericId)) {
      setError('Invalid SOP id.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const rec = await getSop(numericId)
      setRecord(rec)
      setActiveSection(0)
      const doc = await getDocumentContent(rec.document_Uid)
      setContent(doc)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load SOP content.')
    } finally {
      setLoading(false)
    }
  }, [numericId])

  useEffect(() => {
    load()
  }, [load])

  async function handleStatusChange(status: SopStatus) {
    if (!record || status === record.status) return
    setUpdatingStatus(status)
    try {
      await updateSopStatus(record.id, status)
      setRecord((prev) => (prev ? { ...prev, status } : prev))
      pushToast('success', `Status updated to "${STATUS_ACTIONS.find((a) => a.status === status)?.label}".`)
    } catch (err) {
      pushToast('error', err instanceof ApiError ? err.message : 'Failed to update status.')
    } finally {
      setUpdatingStatus(null)
    }
  }

  const sections = content?.sections ?? []
  const currentSection = sections[activeSection]

  const breadcrumb = useMemo(() => (record ? displayTitle(record) : 'SOP Content'), [record])

  if (loading) {
    return (
      <Layout breadcrumb={breadcrumb}>
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-[var(--text-muted)]">
          <Loader2 size={28} className="animate-spin" />
          <p className="text-sm">Loading SOP content…</p>
        </div>
      </Layout>
    )
  }

  if (error || !record || !content) {
    return (
      <Layout breadcrumb="Not found">
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-400/10 text-red-300">
            <AlertTriangle size={26} />
          </div>
          <p className="text-base font-medium">{error ?? 'SOP not found.'}</p>
          <Link to="/">
            <Button variant="ghost">
              <ArrowLeft size={16} />
              Back to repository
            </Button>
          </Link>
        </div>
      </Layout>
    )
  }

  return (
    <Layout breadcrumb={breadcrumb}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <Link
            to="/"
            className="mt-1 flex h-9 w-9 flex-none items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]"
          >
            <ArrowLeft size={16} />
          </Link>
          <FileTypeIcon fileType={record.file_type} />
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{displayTitle(record)}</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">{displaySubline(record)}</p>
          </div>
        </div>
        <div className="flex flex-none flex-col items-end gap-2">
          <StatusBadge status={record.status} />
          <div className="flex items-center gap-2">
            {STATUS_ACTIONS.map(({ status, label, icon: Icon }) => (
              <Button
                key={status}
                variant={status === record.status ? 'primary' : 'ghost'}
                disabled={status === record.status || updatingStatus !== null}
                onClick={() => handleStatusChange(status)}
                className="px-3 py-2 text-xs"
              >
                {updatingStatus === status ? <Loader2 size={14} className="animate-spin" /> : <Icon size={14} />}
                {label}
              </Button>
            ))}
          </div>
        </div>
      </header>

      <div className="mt-6 flex flex-col gap-4 lg:flex-row">
        <SectionNav sections={sections} activeIndex={activeSection} onSelect={setActiveSection} />

        <div className="dashboard-card min-w-0 flex-1 p-6">
          {currentSection ? (
            <>
              <div className="border-b border-[var(--border)] pb-4">
                <div className="text-[11px] uppercase tracking-[0.12em] text-[var(--text-muted)]">
                  Page {currentSection.page_start}
                  {currentSection.page_end !== currentSection.page_start ? `–${currentSection.page_end}` : ''}
                </div>
                <h2 className="mt-1 text-xl font-semibold">
                  {currentSection.section_number ? `${currentSection.section_number}. ` : ''}
                  {currentSection.title}
                </h2>
              </div>

              <div className="mt-5 space-y-4">
                {currentSection.elements.length > 0 ? (
                  currentSection.elements.map((element, index) => (
                    <ElementRenderer key={index} element={element} />
                  ))
                ) : (
                  <p className="text-sm text-[var(--text-muted)]">This section has no extracted content.</p>
                )}
              </div>

              <div className="mt-8 flex items-center justify-between border-t border-[var(--border)] pt-4">
                <Button
                  variant="ghost"
                  disabled={activeSection === 0}
                  onClick={() => setActiveSection((i) => Math.max(0, i - 1))}
                >
                  <ChevronLeft size={16} />
                  Previous
                </Button>
                <span className="text-xs text-[var(--text-muted)]">
                  Section {activeSection + 1} of {sections.length}
                </span>
                <Button
                  variant="ghost"
                  disabled={activeSection === sections.length - 1}
                  onClick={() => setActiveSection((i) => Math.min(sections.length - 1, i + 1))}
                >
                  Next
                  <ChevronRight size={16} />
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm text-[var(--text-muted)]">No sections were extracted for this document.</p>
          )}
        </div>
      </div>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  )
}

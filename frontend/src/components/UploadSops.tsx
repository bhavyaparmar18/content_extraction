import { AnimatePresence, motion } from 'framer-motion'
import { Loader2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError, uploadBatch } from '../lib/api'
import type { BatchJob } from '../types'
import { FileTypeIcon } from './FileTypeIcon'
import { Button } from './ui/Button'

function extensionOf(filename: string): string {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex >= 0 ? filename.slice(dotIndex + 1) : ''
}

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx']

interface UploadSopsProps {
  open: boolean
  onClose: () => void
  /** Called with the freshly-created batch job so the parent can start polling it. */
  onUploaded: (job: BatchJob) => void
}

function hasAcceptedExtension(file: File): boolean {
  const name = file.name.toLowerCase()
  return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))
}

export function UploadSops({ open, onClose, onUploaded }: UploadSopsProps) {
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  function reset() {
    setFiles([])
    setError(null)
    setIsDragging(false)
  }

  function handleClose() {
    if (submitting) return
    reset()
    onClose()
  }

  function addFiles(incoming: FileList | File[]) {
    const accepted: File[] = []
    const rejected: string[] = []
    for (const file of Array.from(incoming)) {
      if (hasAcceptedExtension(file)) {
        accepted.push(file)
      } else {
        rejected.push(file.name)
      }
    }
    setFiles((prev) => [...prev, ...accepted])
    if (rejected.length > 0) {
      setError(`Skipped unsupported file(s): ${rejected.join(', ')}. Only .pdf and .docx are allowed.`)
    }
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  async function handleSubmit() {
    if (files.length === 0 || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const job = await uploadBatch(files)
      onUploaded(job)
      reset()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={handleClose}
        >
          <motion.div
            className="dashboard-card w-full max-w-lg overflow-hidden"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
              <h2 className="text-lg font-semibold">Upload SOPs</h2>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-md p-1 text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5">
              <div
                onDragOver={(event) => {
                  event.preventDefault()
                  setIsDragging(true)
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(event) => {
                  event.preventDefault()
                  setIsDragging(false)
                  addFiles(event.dataTransfer.files)
                }}
                onClick={() => inputRef.current?.click()}
                className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors ${
                  isDragging
                    ? 'border-[var(--primary)] bg-[var(--primary)]/5'
                    : 'border-[var(--border)] hover:border-[var(--primary)]/40'
                }`}
              >
                <Upload size={24} className="text-[var(--primary)]" />
                <p className="text-sm font-medium">Drag & drop files, or click to browse</p>
                <p className="text-xs text-[var(--text-muted)]">PDF or DOCX, up to 50 MB each</p>
                <input
                  ref={inputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_EXTENSIONS.join(',')}
                  className="hidden"
                  onChange={(event) => {
                    if (event.target.files) addFiles(event.target.files)
                    event.target.value = ''
                  }}
                />
              </div>

              {files.length > 0 && (
                <ul className="mt-4 max-h-40 space-y-1.5 overflow-y-auto">
                  {files.map((file, index) => (
                    <li
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-2.5 rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
                    >
                      <FileTypeIcon fileType={extensionOf(file.name)} size="sm" />
                      <span className="min-w-0 flex-1 truncate">{file.name}</span>
                      <span className="flex-none text-xs text-[var(--text-muted)]">
                        {(file.size / 1024).toFixed(0)} KB
                      </span>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="flex-none rounded-md p-1 text-[var(--text-muted)] hover:bg-white/5 hover:text-red-300"
                      >
                        <X size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-5 py-4">
              <Button variant="ghost" onClick={handleClose} disabled={submitting}>
                Cancel
              </Button>
              <Button onClick={handleSubmit} disabled={files.length === 0 || submitting}>
                {submitting ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
                {submitting ? 'Uploading...' : `Upload ${files.length || ''} SOP${files.length === 1 ? '' : 's'}`}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

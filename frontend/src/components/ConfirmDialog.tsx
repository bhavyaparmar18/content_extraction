import { AnimatePresence, motion } from 'framer-motion'
import { Loader2, TriangleAlert } from 'lucide-react'
import { Button } from './ui/Button'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** Reusable destructive-action confirmation modal (replaces window.confirm). */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Delete',
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => !busy && onCancel()}
        >
          <motion.div
            className="dashboard-card w-full max-w-sm overflow-hidden"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start gap-3 p-5">
              <div className="flex-none rounded-full bg-red-400/10 p-2 text-red-300">
                <TriangleAlert size={18} />
              </div>
              <div>
                <h2 className="text-base font-semibold">{title}</h2>
                <p className="mt-1 text-sm text-[var(--text-muted)]">{description}</p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-5 py-4">
              <Button variant="ghost" onClick={onCancel} disabled={busy}>
                Cancel
              </Button>
              <Button
                onClick={onConfirm}
                disabled={busy}
                className="!bg-red-500 !text-white hover:!bg-red-600"
              >
                {busy ? <Loader2 size={16} className="animate-spin" /> : null}
                {busy ? 'Deleting...' : confirmLabel}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

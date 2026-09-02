import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, X, XCircle } from 'lucide-react'
import { useEffect } from 'react'

export interface ToastMessage {
  id: number
  kind: 'success' | 'error'
  text: string
}

interface ToastStackProps {
  toasts: ToastMessage[]
  onDismiss: (id: number) => void
}

const AUTO_DISMISS_MS = 4000

function ToastItem({ toast, onDismiss }: { toast: ToastMessage; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), AUTO_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [toast.id, onDismiss])

  const isSuccess = toast.kind === 'success'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.98 }}
      className={`dashboard-card flex items-start gap-2.5 px-4 py-3 pr-2 shadow-lg ${
        isSuccess ? 'border-[var(--primary)]/30' : 'border-red-400/30'
      }`}
    >
      {isSuccess ? (
        <CheckCircle2 size={18} className="mt-0.5 flex-none text-[var(--primary)]" />
      ) : (
        <XCircle size={18} className="mt-0.5 flex-none text-red-300" />
      )}
      <p className="flex-1 text-sm">{toast.text}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className="flex-none rounded-md p-1 text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]"
      >
        <X size={14} />
      </button>
    </motion.div>
  )
}

/** Fixed bottom-right toast stack for lightweight success/error feedback (e.g. delete outcomes). */
export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2">
      <AnimatePresence>
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto">
            <ToastItem toast={toast} onDismiss={onDismiss} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  )
}

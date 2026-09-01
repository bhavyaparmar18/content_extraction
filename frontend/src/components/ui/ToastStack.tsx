import React, { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react';
import { clsx } from 'clsx';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title?: string;
  message: string;
  durationMs?: number;
}

interface ToastContextValue {
  toast: (options: Omit<Toast, 'id'>) => void;
  success: (message: string, title?: string) => void;
  error: (message: string, title?: string) => void;
  warning: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return ctx;
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    ({ type, title, message, durationMs = 4000 }: Omit<Toast, 'id'>) => {
      const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const newToast: Toast = { id, type, title, message, durationMs };
      setToasts((prev) => [...prev, newToast]);

      if (durationMs > 0) {
        setTimeout(() => {
          removeToast(id);
        }, durationMs);
      }
    },
    [removeToast]
  );

  const success = useCallback((message: string, title?: string) => addToast({ type: 'success', message, title }), [addToast]);
  const error = useCallback((message: string, title?: string) => addToast({ type: 'error', message, title }), [addToast]);
  const warning = useCallback((message: string, title?: string) => addToast({ type: 'warning', message, title }), [addToast]);
  const info = useCallback((message: string, title?: string) => addToast({ type: 'info', message, title }), [addToast]);

  return (
    <ToastContext.Provider value={{ toast: addToast, success, error, warning, info, removeToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none p-4">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 16, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.15 } }}
              className={clsx(
                'pointer-events-auto flex items-start gap-3 rounded-lg border p-3.5 shadow-panel backdrop-blur bg-card/95',
                t.type === 'success' && 'border-emerald-500/40 text-text-main',
                t.type === 'error' && 'border-red-500/40 text-text-main',
                t.type === 'warning' && 'border-amber-500/40 text-text-main',
                t.type === 'info' && 'border-sky-500/40 text-text-main'
              )}
            >
              <span className="shrink-0 mt-0.5">
                {t.type === 'success' && <CheckCircle2 className="size-5 text-emerald-400" />}
                {t.type === 'error' && <XCircle className="size-5 text-red-400" />}
                {t.type === 'warning' && <AlertTriangle className="size-5 text-amber-400" />}
                {t.type === 'info' && <Info className="size-5 text-sky-400" />}
              </span>

              <div className="flex-1 min-w-0">
                {t.title && <div className="text-xs font-semibold">{t.title}</div>}
                <div className="text-xs text-text-muted mt-0.5 leading-relaxed">{t.message}</div>
              </div>

              <button
                onClick={() => removeToast(t.id)}
                className="shrink-0 text-text-muted hover:text-text-main p-0.5 transition"
                aria-label="Close notification"
              >
                <X className="size-4" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
};

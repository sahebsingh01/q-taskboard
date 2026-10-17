import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

type ToastVariant = "success" | "warning" | "error";

type Toast = {
  id: number;
  variant: ToastVariant;
  title: string;
  description?: string;
};

type ToastInput = Omit<Toast, "id">;

const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

const DURATION_MS: Record<ToastVariant, number> = { success: 5000, warning: 8000, error: 8000 };

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  success: "border-emerald-500/60",
  warning: "border-amber-500/60",
  error: "border-red-500/60",
};

const ICONS: Record<ToastVariant, string> = { success: "✓", warning: "!", error: "✕" };

const ICON_CLASSES: Record<ToastVariant, string> = {
  success: "text-emerald-400",
  warning: "text-amber-400",
  error: "text-red-400",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((all) => all.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((toast: ToastInput) => {
    const id = nextId.current++;
    setToasts((all) => [...all, { ...toast, id }]);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div
        className="fixed bottom-4 right-4 left-4 sm:left-auto z-[60] flex flex-col gap-2 sm:w-96"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), DURATION_MS[toast.variant]);
    return () => window.clearTimeout(timer);
  }, [paused, toast.id, toast.variant, onDismiss]);

  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className={`flex items-start gap-3 bg-surface border ${VARIANT_CLASSES[toast.variant]} rounded-lg p-3 shadow-lg shadow-black/40`}
    >
      <span className={`text-sm font-semibold ${ICON_CLASSES[toast.variant]}`} aria-hidden>
        {ICONS[toast.variant]}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && (
          <p className="text-xs text-muted mt-0.5 break-words">{toast.description}</p>
        )}
      </div>
      <button
        onClick={() => onDismiss(toast.id)}
        className="text-muted hover:text-white text-xs"
        aria-label="dismiss"
      >
        ✕
      </button>
    </div>
  );
}

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast must be used inside <ToastProvider>");
  return useMemo(() => ({ show }), [show]);
}

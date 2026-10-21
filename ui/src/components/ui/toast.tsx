"use client";

import * as React from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info" | "warning";

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
  leaving: boolean;
}

interface ToastContextValue {
  notify: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

/** Errors stay up longer so there is time to read what went wrong. */
const DURATION_MS: Record<ToastVariant, number> = {
  success: 4000,
  info: 4000,
  warning: 5500,
  error: 6500,
};

/** Matches the toast-out keyframe length in globals.css. */
const EXIT_MS = 200;
const MAX_VISIBLE = 4;

const VARIANTS: Record<
  ToastVariant,
  { icon: React.ElementType; title: string; iconWrap: string; accent: string; bar: string }
> = {
  success: {
    icon: CheckCircle2,
    title: "Success",
    iconWrap: "bg-brand-50 text-brand-600 ring-brand-200",
    accent: "bg-brand-600",
    bar: "bg-brand-500",
  },
  error: {
    icon: XCircle,
    title: "Error",
    iconWrap: "bg-red-50 text-red-600 ring-red-200",
    accent: "bg-red-500",
    bar: "bg-red-500",
  },
  warning: {
    icon: AlertTriangle,
    title: "Warning",
    iconWrap: "bg-amber-50 text-amber-600 ring-amber-200",
    accent: "bg-brand-gold",
    bar: "bg-brand-gold",
  },
  info: {
    icon: Info,
    title: "Info",
    iconWrap: "bg-sky-50 text-sky-600 ring-sky-200",
    accent: "bg-sky-500",
    bar: "bg-sky-500",
  },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const nextId = React.useRef(0);

  const remove = React.useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  // Play the exit animation first, then drop the toast.
  const dismiss = React.useCallback(
    (id: number) => {
      setToasts((current) => current.map((toast) => (toast.id === id ? { ...toast, leaving: true } : toast)));
      setTimeout(() => remove(id), EXIT_MS);
    },
    [remove],
  );

  const notify = React.useCallback((message: string, variant: ToastVariant = "info") => {
    setToasts((current) => {
      // A double-click or retry loop should not stack identical messages.
      if (current.some((toast) => !toast.leaving && toast.message === message && toast.variant === variant)) {
        return current;
      }
      const next = [...current, { id: nextId.current++, message, variant, leaving: false }];
      return next.slice(-MAX_VISIBLE);
    });
  }, []);

  const value = React.useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 top-4 z-[2000] flex flex-col items-center gap-3 px-4 sm:inset-x-auto sm:right-4 sm:items-end sm:px-0"
        aria-live="polite"
        aria-label="Notifications"
        role="region"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  const style = VARIANTS[toast.variant];
  const Icon = style.icon;
  const [paused, setPaused] = React.useState(false);

  return (
    <div
      role={toast.variant === "error" ? "alert" : "status"}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className={cn(
        "toast-motion pointer-events-auto relative w-full max-w-sm overflow-hidden rounded-xl bg-white/95 shadow-[0_12px_32px_-8px_rgba(11,42,26,0.28)] ring-1 ring-black/5 backdrop-blur-md",
        toast.leaving
          ? "animate-[toast-out_200ms_ease-in_forwards]"
          : "animate-[toast-in_320ms_cubic-bezier(0.21,1.02,0.73,1)]",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", style.accent)} />

      <div className="flex items-start gap-3 py-3.5 pr-3 pl-5">
        <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-1", style.iconWrap)}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-sm font-semibold text-ink">{style.title}</p>
          <p className="mt-0.5 text-sm leading-snug break-words text-slate-600">{toast.message}</p>
        </div>
        <button
          type="button"
          onClick={() => onDismiss(toast.id)}
          aria-label="Dismiss notification"
          className="-mt-0.5 rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>

      {/* Countdown bar; it pauses on hover or focus, and auto-dismiss fires when it runs out. */}
      <span
        aria-hidden
        onAnimationEnd={() => onDismiss(toast.id)}
        className={cn("absolute bottom-0 left-0 h-[3px] w-full origin-left opacity-70", style.bar)}
        style={{
          animation: `toast-progress ${DURATION_MS[toast.variant]}ms linear forwards`,
          animationPlayState: paused || toast.leaving ? "paused" : "running",
        }}
      />
    </div>
  );
}

export function useToast(): ToastContextValue {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside a ToastProvider.");
  }
  return context;
}

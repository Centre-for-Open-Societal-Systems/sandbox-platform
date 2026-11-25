"use client";

import { cn } from "@/lib/utils";

interface StatusToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Accessible name, e.g. "Active status of Jane Doe". */
  label: string;
  disabled?: boolean;
}

/** 36×20 switch used for enable/disable in every admin table. */
export function StatusToggle({ checked, onChange, label, disabled = false }: StatusToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={checked ? "Active — click to deactivate" : "Inactive — click to activate"}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "inline-flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-bright",
        checked ? "bg-nav-active" : "bg-slate-300",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          "h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
          checked && "translate-x-4",
        )}
      />
    </button>
  );
}

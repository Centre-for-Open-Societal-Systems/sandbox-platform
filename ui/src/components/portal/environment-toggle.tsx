"use client";

import { ENVIRONMENTS, type Environment } from "@/lib/config";
import { cn } from "@/lib/utils";

const LABELS: Record<Environment, string> = { UAT: "UAT", PRODUCTION: "Production" };

/**
 * UAT / Production switch (a radio group). An environment the account is not
 * approved for is shown, disabled, so the participant sees it exists.
 */
export function EnvironmentToggle({
  value,
  onChange,
  available,
  label = "Environment",
  counts,
}: {
  value: Environment;
  onChange: (environment: Environment) => void;
  available: Environment[];
  label?: string;
  /** Optional number shown next to each option, e.g. apps per environment. */
  counts?: Partial<Record<Environment, number>>;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl border border-hairline bg-white p-1">
      {ENVIRONMENTS.map((environment) => {
        const allowed = available.includes(environment);
        const selected = environment === value;
        return (
          <button
            key={environment}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={!allowed}
            title={allowed ? undefined : "Your account is not approved for this environment yet."}
            onClick={() => onChange(environment)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm font-semibold transition-colors",
              selected ? "bg-brand-bright text-white shadow-sm" : "text-ink hover:bg-surface-soft",
              !allowed && "cursor-not-allowed text-subtle opacity-60 hover:bg-transparent",
            )}
          >
            {LABELS[environment]}
            {counts?.[environment] !== undefined ? (
              <span
                className={cn(
                  "rounded-full px-1.5 text-xs font-medium",
                  selected ? "bg-white/25 text-white" : "bg-surface-soft text-subtle",
                )}
              >
                {counts[environment]}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

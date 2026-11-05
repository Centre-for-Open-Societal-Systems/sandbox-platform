"use client";

import * as React from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ApiCallSource, GatewaySyncStatus } from "@/types/api";

const SUBSCRIPTION_VARIANTS: Record<number, "warning" | "success" | "danger" | "neutral"> = {
  0: "warning",
  1: "success",
  2: "danger",
  3: "neutral",
};

/** An app's access to one API product: pending / approved / rejected / revoked. */
export function SubscriptionBadge({ status, label }: { status: number; label: string }) {
  return <Badge variant={SUBSCRIPTION_VARIANTS[status] ?? "neutral"}>{label}</Badge>;
}

const APP_STATUS_VARIANTS: Record<number, "warning" | "success" | "danger"> = {
  0: "warning", // awaiting approval
  1: "success", // active
  2: "danger", // revoked
  3: "danger", // rejected
};

export function AppStatusBadge({ status, label }: { status: number; label: string }) {
  return <Badge variant={APP_STATUS_VARIANTS[status] ?? "danger"}>{label}</Badge>;
}

const GATEWAY_STATES: Record<GatewaySyncStatus, { label: string; variant: "success" | "warning" | "danger" | "neutral" }> = {
  SYNCED: { label: "On gateway", variant: "success" },
  PENDING: { label: "Sync pending", variant: "warning" },
  FAILED: { label: "Sync failed", variant: "danger" },
  DISABLED: { label: "Gateway sync off", variant: "neutral" },
};

/** Where an API history row came from: the portal's try-it, or a direct call with an app key. */
export function SourceBadge({ source, appName }: { source: ApiCallSource; appName?: string | null }) {
  return (
    <span className="flex flex-col items-start gap-0.5">
      <Badge variant={source === "DIRECT" ? "success" : "info"}>{source === "DIRECT" ? "Direct" : "Try-it"}</Badge>
      {appName ? <span className="text-xs text-subtle">{appName}</span> : null}
    </span>
  );
}

/** "60 / min · 5,000 / day", or "No limit". */
export function limitText(perMinute: number | null | undefined, perDay: number | null | undefined): string {
  const parts = [
    perMinute ? `${perMinute.toLocaleString()} / min` : null,
    perDay ? `${perDay.toLocaleString()} / day` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No limit";
}

/** One IP or CIDR per line (commas and spaces also separate). */
export function parseIpList(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function GatewayBadge({ status }: { status: GatewaySyncStatus }) {
  const state = GATEWAY_STATES[status] ?? GATEWAY_STATES.PENDING;
  return <Badge variant={state.variant}>{state.label}</Badge>;
}

/**
 * Read-only credential value with copy, optionally masked until revealed
 * (API keys are shown masked by default; a fresh secret is shown in clear).
 */
export function SecretField({
  label,
  value,
  masked = false,
  className,
}: {
  label: string;
  value: string;
  masked?: boolean;
  className?: string;
}) {
  const [visible, setVisible] = React.useState(!masked);
  const [copied, setCopied] = React.useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-xs font-medium text-subtle">{label}</span>
      <div className="flex items-center gap-2 rounded-lg border border-hairline bg-surface-soft px-3 py-2">
        <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink" title={visible ? value : undefined}>
          {visible ? value : "•".repeat(Math.min(32, value.length))}
        </code>
        {masked ? (
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="rounded p-1 text-subtle hover:bg-white hover:text-ink"
            aria-label={visible ? `Hide ${label}` : `Show ${label}`}
            title={visible ? "Hide" : "Show"}
          >
            {visible ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
          </button>
        ) : null}
        <button
          type="button"
          onClick={copy}
          className="rounded p-1 text-subtle hover:bg-white hover:text-ink"
          aria-label={`Copy ${label}`}
          title={copied ? "Copied" : "Copy"}
        >
          {copied ? <Check className="h-4 w-4 text-brand-600" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
        </button>
      </div>
    </div>
  );
}

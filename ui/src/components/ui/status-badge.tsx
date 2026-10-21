import { Badge } from "@/components/ui/badge";
import { QUERY_STATUSES } from "@/lib/support";
import type { Participant } from "@/types/api";

const APPROVAL_STATES: Record<number, { label: string; variant: "success" | "warning" | "danger" }> = {
  0: { label: "Pending", variant: "warning" },
  1: { label: "Approved", variant: "success" },
  2: { label: "Rejected", variant: "danger" },
};

export function ApprovalBadge({ status, rejected }: { status: number; rejected?: boolean }) {
  if (rejected) {
    return <Badge variant="danger">Rejected</Badge>;
  }
  const state = APPROVAL_STATES[status] ?? APPROVAL_STATES[0]!;
  return <Badge variant={state.variant}>{state.label}</Badge>;
}

export function EnabledBadge({ enabled }: { enabled: boolean }) {
  return <Badge variant={enabled ? "success" : "neutral"}>{enabled ? "Active" : "Disabled"}</Badge>;
}

export function PublishedBadge({ published }: { published: boolean }) {
  return (
    <Badge variant={published ? "success" : "neutral"}>{published ? "Published" : "Draft"}</Badge>
  );
}

/** The highest environment a participant has been promoted to. */
export function EnvironmentBadge({ participant }: { participant: Participant }) {
  if (participant.is_prod_approved) {
    return <Badge variant="success">Production</Badge>;
  }
  if (participant.is_uat_approved) {
    return <Badge variant="info">UAT</Badge>;
  }
  if (participant.is_sandbox_approved) {
    return <Badge variant="neutral">Sandbox</Badge>;
  }
  return <Badge variant="warning">None</Badge>;
}

export function VerifiedBadge({ verified }: { verified: boolean }) {
  return (
    <Badge variant={verified ? "success" : "warning"}>{verified ? "Verified" : "Unverified"}</Badge>
  );
}

const METHOD_VARIANTS: Record<string, "success" | "info" | "warning" | "danger" | "neutral"> = {
  GET: "info",
  POST: "success",
  PUT: "warning",
  PATCH: "warning",
  DELETE: "danger",
};

export function MethodBadge({ method }: { method: string | null }) {
  const value = (method ?? "GET").toUpperCase();
  return (
    <Badge variant={METHOD_VARIANTS[value] ?? "neutral"} className="font-mono">
      {value}
    </Badge>
  );
}

export function StatusCodeBadge({ code }: { code: number | null }) {
  if (code === null) {
    return <Badge variant="neutral">—</Badge>;
  }
  const variant = code < 300 ? "success" : code < 500 ? "warning" : "danger";
  return (
    <Badge variant={variant} className="font-mono">
      {code}
    </Badge>
  );
}

export function QueryStatusBadge({ status }: { status: number }) {
  const state = QUERY_STATUSES.find((item) => item.value === status) ?? QUERY_STATUSES[0];
  return <Badge variant={state.variant}>{state.label}</Badge>;
}

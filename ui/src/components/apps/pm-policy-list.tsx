import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";
import type { PmPolicyRequest } from "@/types/api";

const STATUS: Record<PmPolicyRequest["status"], { label: string; variant: "success" | "neutral" | "danger" }> = {
  ACTIVE: { label: "Approved", variant: "success" },
  PENDING: { label: "Awaiting PM approval", variant: "neutral" },
  WAITING: { label: "Waiting for partner approval in PM", variant: "neutral" },
  REVOKING: { label: "Revocation awaiting PM", variant: "neutral" },
  REJECTED: { label: "Rejected by PM", variant: "danger" },
  FAILED: { label: "Not sent (retrying)", variant: "danger" },
};

/** "data_controller:farmer_registry" -> "Registry farmer_registry" */
function keyLabel(key: string): string {
  const [kind, value] = key.split(/:(.*)/s);
  return `${kind === "use_case" ? "Use case" : "Registry"} ${value ?? key}`;
}

/** Partner Management policies the sandbox asked for, with their state. */
export function PmPolicyList({ policies, showRequests = false }: { policies: PmPolicyRequest[]; showRequests?: boolean }) {
  return (
    <ul className="mt-2 space-y-2">
      {policies.map((p) => {
        const status =
          p.backend === "cm" && p.status === "PENDING"
            ? { label: "Awaiting AWE approval", variant: "neutral" as const }
            : (STATUS[p.status] ?? STATUS.FAILED);
        const where = p.backend === "cm" ? "Consent Manager" : "PM";
        const scopes = p.policy?.allowed_data_scopes ?? [];
        return (
          <li key={`${p.environment}-${p.backend ?? "pm"}-${p.policy_key}`} className="text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{keyLabel(p.policy_key)}</span>
              <Badge variant={status.variant}>{status.label}</Badge>
              <span className="text-subtle">
                {p.environment === "PRODUCTION" ? "Production" : "UAT"} {where}
              </span>
              {showRequests && p.request_id ? <code className="font-mono text-subtle">{p.request_id}</code> : null}
              {p.synced_at ? <span className="text-subtle">· {formatDateTime(p.synced_at)}</span> : null}
            </div>
            {scopes.length ? <p className="text-subtle">Scopes: {scopes.join(", ")}</p> : null}
            {p.products.length ? <p className="text-subtle">From: {p.products.join(", ")}</p> : null}
            {p.error ? <p className="break-words text-red-700">{p.error}</p> : null}
          </li>
        );
      })}
    </ul>
  );
}

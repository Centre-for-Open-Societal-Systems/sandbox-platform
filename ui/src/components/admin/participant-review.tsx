"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { showBlobInTab } from "@/lib/api-client";
import { adminApi } from "@/lib/services/admin";
import { catalogApi } from "@/lib/services/catalog";
import { formatDateTime, formatNumber } from "@/lib/utils";
import type { PromotionRequest } from "@/types/api";

const PENDING = { label: "Pending", variant: "warning" } as const;
const REQUEST_STATUS: Record<number, { label: string; variant: "warning" | "success" | "danger" }> = {
  0: PENDING,
  1: { label: "Approved", variant: "success" },
  2: { label: "Rejected", variant: "danger" },
};

function fileName(path: string) {
  // Stored names carry a 32-character random prefix: "<hex>_<original name>".
  return path.split("/").pop()?.replace(/^[0-9a-f]{32}_/, "") ?? path;
}

/** Opens a private upload in a new tab using the admin session. */
function DocumentButton({ path, label }: { path: string; label: string }) {
  const { notify } = useToast();
  const [opening, setOpening] = React.useState(false);

  async function open() {
    const tab = window.open("", "_blank");
    setOpening(true);
    try {
      showBlobInTab(await adminApi.participantFile(path), tab);
    } catch (error) {
      tab?.close();
      notify(error instanceof Error ? error.message : "The document could not be opened.", "error");
    } finally {
      setOpening(false);
    }
  }

  return (
    <Button type="button" size="sm" variant="outline" onClick={open} loading={opening} title={fileName(path)}>
      <FileText className="h-4 w-4" aria-hidden />
      {label}
    </Button>
  );
}

/**
 * Documents and environment requests of one participant, for the console's
 * participant details dialog.
 */
export function ParticipantReview({ participantId }: { participantId: number }) {
  const detailQuery = useQuery({
    queryKey: ["admin", "participants", "detail", participantId],
    queryFn: () => adminApi.getParticipant(participantId),
  });

  const detail = detailQuery.data;
  const needsEndpointNames = Boolean(detail?.requests.some((request) => request.extra_data?.endpoint_ids?.length));
  const endpointsQuery = useQuery({
    queryKey: ["admin", "endpoints", "names"],
    queryFn: () => catalogApi.listEndpoints({ page: 1, limit: 200 }),
    enabled: needsEndpointNames,
    staleTime: 5 * 60_000,
  });
  const endpointNames = React.useMemo(
    () =>
      new Map(
        (endpointsQuery.data?.endpoints ?? []).map((endpoint) => [
          endpoint.endpoint_id,
          `${endpoint.method ?? ""} ${endpoint.display_name || endpoint.endpoint_url || ""}`.trim(),
        ]),
      ),
    [endpointsQuery.data],
  );

  if (detailQuery.isLoading) {
    return (
      <p className="flex items-center gap-2 text-sm text-subtle">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading documents and requests…
      </p>
    );
  }
  if (detailQuery.isError || !detail) {
    return <p className="text-sm text-red-600">{(detailQuery.error as Error | null)?.message ?? "Not available."}</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      <section>
        <h3 className="mb-2 text-sm font-semibold text-nav-active">Documents</h3>
        {detail.id_proof ? (
          <DocumentButton path={detail.id_proof} label="View ID proof" />
        ) : (
          <p className="text-sm text-subtle">No ID proof uploaded.</p>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-nav-active">Environment requests</h3>
        {detail.requests.length === 0 ? (
          <p className="text-sm text-subtle">No UAT or production requests yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {detail.requests.map((request) => (
              <RequestCard key={request.request_id} request={request} endpointNames={endpointNames} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function RequestCard({ request, endpointNames }: { request: PromotionRequest; endpointNames: Map<number, string> }) {
  const status = REQUEST_STATUS[request.status] ?? PENDING;
  const details = request.extra_data ?? {};
  const rows: Array<[string, React.ReactNode]> = [];
  if (details.daily_volume !== undefined) rows.push(["Expected daily volume", formatNumber(details.daily_volume)]);
  if (details.integration_contact) rows.push(["Integration contact", details.integration_contact]);
  if (details.escalation_contact) rows.push(["Escalation contact", details.escalation_contact]);
  if (request.remarks) rows.push(["Remarks", request.remarks]);
  if (request.rejection_reason) rows.push(["Rejection reason", request.rejection_reason]);

  return (
    <li className="rounded-xl border border-hairline p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-ink">{request.target_environment}</p>
        <div className="flex items-center gap-2">
          <span className="text-xs text-subtle">{formatDateTime(request.added_date)}</span>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
      </div>

      {rows.length ? (
        <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-medium text-subtle">{label}</dt>
              <dd className="mt-0.5 break-words whitespace-pre-wrap text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {details.endpoint_ids?.length ? (
        <div className="mt-3">
          <p className="text-xs font-medium text-subtle">End-points ({details.endpoint_ids.length})</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {details.endpoint_ids.map((id) => (
              <li key={id} className="rounded bg-surface-soft px-2 py-0.5 font-mono text-xs text-ink">
                {endpointNames.get(id) ?? `#${id}`}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {details.public_key ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-subtle">Public key</summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded-lg border border-hairline bg-white p-2 font-mono text-[0.7rem] break-all whitespace-pre-wrap">
            {details.public_key}
          </pre>
        </details>
      ) : null}

      {request.certificate_path || request.document_path ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {request.certificate_path ? <DocumentButton path={request.certificate_path} label="Certificate" /> : null}
          {request.document_path ? <DocumentButton path={request.document_path} label="Data retention policy" /> : null}
        </div>
      ) : null}
    </li>
  );
}

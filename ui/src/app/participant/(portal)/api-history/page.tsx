"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, Loader2, Play, RotateCcw, SlidersHorizontal } from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { FilterField, SearchBox } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { MethodBadge, StatusCodeBadge } from "@/components/ui/status-badge";
import { useListQuery } from "@/hooks/use-list-query";
import { ENVIRONMENTS, HTTP_METHODS } from "@/lib/config";
import { participantApi } from "@/lib/services/participant";
import { cn, formatDateTime, prettyJson } from "@/lib/utils";
import type { ApiLog } from "@/types/api";

const STATUS_CODES = [200, 201, 400, 401, 403, 404, 422, 429, 500, 502, 504];
const CODE_BLOCK =
  "max-h-[50vh] min-h-32 overflow-auto rounded-xl bg-[#0f1d16] p-4 font-mono text-xs leading-relaxed text-[#d9f2df]";

type DetailTab = "overview" | "request" | "response";

export default function ParticipantApiHistoryPage() {
  const list = useListQuery({ sortBy: "log_timestamp" });
  const [viewingId, setViewingId] = React.useState<number | null>(null);

  const logsQuery = useQuery({
    queryKey: ["participant", "api-history", list.query],
    queryFn: () => participantApi.apiHistory(list.query),
  });

  const columns: Column<ApiLog>[] = [
    {
      key: "log_timestamp",
      header: "Date & Time",
      sortable: true,
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.log_timestamp)}</span>,
    },
    {
      key: "endpoint_url",
      header: "End-Point",
      render: (row) => (
        <div className="flex items-center gap-2">
          <MethodBadge method={row.method} />
          <code className="font-mono text-xs">{row.endpoint_url ?? "—"}</code>
        </div>
      ),
    },
    { key: "environment", header: "Environment", render: (row) => <EnvironmentChip value={row.environment} /> },
    {
      key: "status_code",
      header: "Status",
      sortable: true,
      render: (row) => <StatusCodeBadge code={row.status_code} />,
    },
    {
      key: "latency_ms",
      header: "Latency",
      sortable: true,
      render: (row) => (row.latency_ms === null ? "—" : `${Math.round(row.latency_ms)} ms`),
    },
    {
      key: "transaction_id",
      header: "Transaction ID",
      render: (row) => <code className="font-mono text-xs text-slate-600">{row.transaction_id ?? "—"}</code>,
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`call ${row.transaction_id ?? row.id}`}
          onView={() => setViewingId(row.id)}
          extra={
            row.endpoint_id
              ? [{ icon: Play, label: "Open this end-point in the console", href: `/participant/catalog/${row.endpoint_id}` }]
              : []
          }
        />
      ),
    },
  ];

  const activeFilters =
    Object.values(list.filters).filter((value) => value !== "" && value !== undefined && value !== null).length +
    (list.searchInput.trim() ? 1 : 0);

  return (
    <>
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="API History"
        title="API History"
        description="Every call you have made through the sandbox console, with its outcome. Open a call to see the full request and response."
        image="/assets/home/bean-harvest.webp"
      />

      {/* ------------------------------------------------- search and filters */}
      <section className="mt-6 mb-6 rounded-2xl border border-hairline bg-white p-5 shadow-sm" aria-label="Search and filters">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-brand-bright" aria-hidden />
            <h2 className="text-base font-semibold text-nav-active">Search &amp; filter calls</h2>
            {activeFilters > 0 ? <Badge variant="info">{activeFilters} active</Badge> : null}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 sm:flex-none">
              <SearchBox value={list.searchInput} onChange={list.setSearchInput} placeholder="End-point or transaction ID" />
            </div>
            <Button variant="outline" onClick={list.resetFilters} disabled={activeFilters === 0}>
              <RotateCcw className="h-4 w-4" aria-hidden />
              Clear
            </Button>
          </div>
        </div>

        <div className="mt-5 grid gap-4 border-t border-hairline pt-5 sm:grid-cols-2 lg:grid-cols-5">
          <FilterField className="sm:max-w-none" label="Environment" htmlFor="environment">
            <Select
              id="environment"
              value={(list.filters.environment as string) ?? ""}
              onChange={(event) => list.setFilter("environment", event.target.value)}
            >
              <option value="">All</option>
              {ENVIRONMENTS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField className="sm:max-w-none" label="Method" htmlFor="method">
            <Select
              id="method"
              value={(list.filters.method as string) ?? ""}
              onChange={(event) => list.setFilter("method", event.target.value)}
            >
              <option value="">All</option>
              {HTTP_METHODS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField className="sm:max-w-none" label="Status" htmlFor="status">
            <Select
              id="status"
              value={String(list.filters.status_code ?? "")}
              onChange={(event) => list.setFilter("status_code", event.target.value ? Number(event.target.value) : "")}
            >
              <option value="">All</option>
              {STATUS_CODES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          </FilterField>
          <FilterField className="sm:max-w-none" label="From" htmlFor="date-from">
            <Input
              id="date-from"
              type="date"
              value={(list.filters.date_from as string) ?? ""}
              onChange={(event) => list.setFilter("date_from", event.target.value)}
            />
          </FilterField>
          <FilterField className="sm:max-w-none" label="To" htmlFor="date-to">
            <Input
              id="date-to"
              type="date"
              value={(list.filters.date_to as string) ?? ""}
              onChange={(event) => list.setFilter("date_to", event.target.value)}
            />
          </FilterField>
        </div>
      </section>

      <DataTable
        columns={columns}
        rows={logsQuery.data?.logs ?? []}
        rowKey={(row) => row.id}
        pagination={logsQuery.data?.pagination}
        loading={logsQuery.isLoading}
        noun="calls"
        emptyMessage="No calls match. Try an end-point from the API Catalogue and it will appear here."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      <CallDetailDialog key={viewingId ?? "closed"} logId={viewingId} onClose={() => setViewingId(null)} />
    </>
  );
}

function EnvironmentChip({ value }: { value: string | null }) {
  if (!value) {
    return <span>—</span>;
  }
  const variant = value === "PRODUCTION" ? "success" : value === "UAT" ? "info" : "warning";
  return <Badge variant={variant}>{value}</Badge>;
}

function CallDetailDialog({ logId, onClose }: { logId: number | null; onClose: () => void }) {
  const [tab, setTab] = React.useState<DetailTab>("overview");
  const [copied, setCopied] = React.useState(false);

  const detailQuery = useQuery({
    queryKey: ["participant", "api-history", "detail", logId],
    queryFn: () => participantApi.apiHistoryDetail(logId!),
    enabled: logId !== null,
  });
  const detail = detailQuery.data;

  const tabText =
    tab === "request"
      ? prettyJson({ headers: detail?.request_headers ?? {}, body: detail?.request_body ?? null })
      : prettyJson(detail?.response_body);

  async function copy() {
    await navigator.clipboard.writeText(tabText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Dialog open={logId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>API Call Details</DialogTitle>
          <DialogDescription className="font-mono">{detail?.transaction_id ?? " "}</DialogDescription>
        </DialogHeader>

        {detailQuery.isLoading ? (
          <p className="flex items-center gap-2 py-10 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
            Loading…
          </p>
        ) : !detail ? (
          <p className="py-10 text-center text-sm text-subtle">This call could not be loaded.</p>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-white p-3">
              <MethodBadge method={detail.method} />
              <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink">{detail.endpoint_url}</code>
              <StatusCodeBadge code={detail.status_code} />
              <span className="text-xs text-subtle">
                {detail.latency_ms === null ? "—" : `${Math.round(detail.latency_ms)} ms`}
              </span>
            </div>

            <div className="mb-4 flex items-center justify-between gap-3 border-b border-hairline" role="tablist">
              <div className="flex gap-1">
                {(["overview", "request", "response"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    role="tab"
                    aria-selected={tab === item}
                    onClick={() => setTab(item)}
                    className={cn(
                      "-mb-px border-b-2 px-3 pb-2.5 text-sm capitalize transition-colors",
                      tab === item
                        ? "border-nav-active font-semibold text-nav-active"
                        : "border-transparent text-slate-600 hover:text-ink",
                    )}
                  >
                    {item}
                  </button>
                ))}
              </div>
              {tab !== "overview" ? (
                <button
                  type="button"
                  onClick={copy}
                  className="mb-2 inline-flex items-center gap-1.5 rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-surface-soft"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-brand-bright" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
                  {copied ? "Copied" : "Copy"}
                </button>
              ) : null}
            </div>

            {tab === "overview" ? (
              <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                {[
                  ["Environment", detail.environment],
                  ["Requested at", formatDateTime(detail.request_time ?? detail.log_timestamp)],
                  ["Responded at", formatDateTime(detail.response_time)],
                  ["Transaction ID", detail.transaction_id],
                  ["Target URL", detail.target_url],
                  ["Error", detail.error_message],
                ].map(([label, value]) => (
                  <div key={label} className={label === "Target URL" || label === "Error" ? "sm:col-span-2" : undefined}>
                    <dt className="text-xs font-medium text-subtle">{label}</dt>
                    <dd className="mt-0.5 font-mono text-sm break-all text-ink">{value || "—"}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <pre className={CODE_BLOCK}>{tabText || "(empty)"}</pre>
            )}

            {detail.endpoint_id ? (
              <div className="mt-6 flex justify-end">
                <Button asChild variant="outline">
                  <Link href={`/participant/catalog/${detail.endpoint_id}`}>
                    <Play className="h-4 w-4" aria-hidden />
                    Open in console
                  </Link>
                </Button>
              </div>
            ) : null}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

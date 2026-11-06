"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { SourceBadge } from "@/components/apps/app-ui";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { SearchableMultiSelect, type LookupItem } from "@/components/ui/searchable-multi-select";
import { MethodBadge, StatusCodeBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { saveBlob } from "@/lib/api-client";
import { ENVIRONMENTS, HTTP_METHODS } from "@/lib/config";
import { adminApi } from "@/lib/services/admin";
import { formatDateTime } from "@/lib/utils";
import type { ApiLog } from "@/types/api";

export default function ApiHistoryPage() {
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "log_timestamp" });
  const [viewingId, setViewingId] = React.useState<number | null>(null);

  const logsQuery = useQuery({
    queryKey: ["admin", "logs", "api-history", list.query],
    queryFn: () => adminApi.apiHistory(list.query),
  });

  const [partners, setPartners] = React.useState<LookupItem[]>([]);

  function choosePartners(items: LookupItem[]) {
    setPartners(items);
    list.setFilter("participant_ids", items.length ? items.map((item) => item.id) : undefined);
  }

  function clearFilters() {
    setPartners([]);
    list.resetFilters();
  }

  const detailQuery = useQuery({
    queryKey: ["admin", "logs", "api-history", "detail", viewingId],
    queryFn: () => adminApi.apiHistoryDetail(viewingId!),
    enabled: viewingId !== null,
  });

  async function handleExport() {
    try {
      const blob = await adminApi.exportApiHistory(list.query);
      saveBlob(blob, `api-history-${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Export failed.", "error");
    }
  }

  const columns: Column<ApiLog>[] = [
    {
      key: "log_timestamp",
      header: "Date & Time",
      sortable: true,
      render: (row) => formatDateTime(row.log_timestamp),
    },
    {
      key: "participant_name",
      header: "Partner",
      render: (row) => row.participant_name ?? "—",
    },
    { key: "method", header: "Method", render: (row) => <MethodBadge method={row.method} /> },
    {
      key: "endpoint_url",
      header: "End-Point",
      render: (row) => <code className="font-mono text-xs">{row.endpoint_url ?? "—"}</code>,
    },
    { key: "source", header: "Source", render: (row) => <SourceBadge source={row.source} appName={row.app_name} /> },
    { key: "environment", header: "Environment", render: (row) => row.environment ?? "—" },
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
      render: (row) => <code className="font-mono text-xs">{row.transaction_id ?? "—"}</code>,
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions recordLabel={`call ${row.transaction_id ?? row.id}`} onView={() => setViewingId(row.id)} />
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="API's History"
        description="Every call routed through the sandbox, with its outcome and latency."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Audit Logs" }, { label: "API's History" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "End-point or transaction ID" }}
        actions={
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4" aria-hidden />
            Export
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="Partner" htmlFor="partner">
          <SearchableMultiSelect
            id="partner"
            queryKey={["admin", "logs", "api-usage", "lookup", "partners"]}
            fetchPage={adminApi.lookupUsagePartners}
            value={partners}
            onChange={choosePartners}
            placeholder="All partners"
            noun="partners"
            searchPlaceholder="Search name or email"
          />
        </FilterField>
        <FilterField label="Result" htmlFor="status-class">
          <Select
            id="status-class"
            value={(list.filters.status_class as string) ?? ""}
            onChange={(event) => list.setFilter("status_class", event.target.value)}
          >
            <option value="">All results</option>
            <option value="2xx">Success (2xx)</option>
            <option value="3xx">Redirect (3xx)</option>
            <option value="4xx">Client error (4xx)</option>
            <option value="5xx">Server error / no answer (5xx)</option>
          </Select>
        </FilterField>
        <FilterField label="Source" htmlFor="source">
          <Select
            id="source"
            value={(list.filters.source as string) ?? ""}
            onChange={(event) => list.setFilter("source", event.target.value)}
          >
            <option value="">All</option>
            <option value="TRYIT">Try-it</option>
            <option value="DIRECT">Direct (app key)</option>
          </Select>
        </FilterField>
        <FilterField label="Environment" htmlFor="environment">
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
        <FilterField label="Method" htmlFor="method">
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
        <FilterField label="From" htmlFor="date-from">
          <Input
            id="date-from"
            type="date"
            value={(list.filters.date_from as string) ?? ""}
            onChange={(event) => list.setFilter("date_from", event.target.value)}
          />
        </FilterField>
        <FilterField label="To" htmlFor="date-to">
          <Input
            id="date-to"
            type="date"
            value={(list.filters.date_to as string) ?? ""}
            onChange={(event) => list.setFilter("date_to", event.target.value)}
          />
        </FilterField>
        <Button variant="ghost" onClick={clearFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={logsQuery.data?.logs ?? []}
        rowKey={(row) => row.id}
        pagination={logsQuery.data?.pagination}
        loading={logsQuery.isLoading}
        noun="calls"
        emptyMessage="No API calls match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      <Dialog open={viewingId !== null} onOpenChange={(open) => !open && setViewingId(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>API Call Details</DialogTitle>
            <DialogDescription>{detailQuery.data?.transaction_id ?? "Loading…"}</DialogDescription>
          </DialogHeader>
          {detailQuery.data ? (
            <pre className="max-h-[60vh] overflow-auto rounded-xl border border-hairline bg-white p-4 font-mono text-xs text-ink">
              {JSON.stringify(detailQuery.data, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-subtle">{detailQuery.isError ? "Could not load this call." : "Loading…"}</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

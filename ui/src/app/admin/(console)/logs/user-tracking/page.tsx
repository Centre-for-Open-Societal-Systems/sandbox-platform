"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { saveBlob } from "@/lib/api-client";
import { adminApi } from "@/lib/services/admin";
import { formatDateTime } from "@/lib/utils";
import type { UserActionLog } from "@/types/api";

const ACTOR_TYPES = ["admin", "user", "system"];

export default function UserTrackingPage() {
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "timestamp" });
  const [viewing, setViewing] = React.useState<UserActionLog | null>(null);

  const logsQuery = useQuery({
    queryKey: ["admin", "logs", "user-tracking", list.query],
    queryFn: () => adminApi.userTracking(list.query),
  });

  async function handleExport() {
    try {
      const blob = await adminApi.exportUserTracking(list.query);
      saveBlob(blob, `user-tracking-${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Export failed.", "error");
    }
  }

  const columns: Column<UserActionLog>[] = [
    {
      key: "timestamp",
      header: "Date & Time",
      sortable: true,
      render: (row) => formatDateTime(row.timestamp),
    },
    {
      key: "actor_name",
      header: "User",
      render: (row) => (
        <div>
          <p className="font-medium">{row.actor_name ?? "—"}</p>
          <p className="text-xs text-subtle">{row.actor_type}</p>
        </div>
      ),
    },
    {
      key: "action",
      header: "Action",
      sortable: true,
      render: (row) => <Badge variant="info">{row.action}</Badge>,
    },
    {
      key: "entity",
      header: "Target",
      render: (row) => `${row.entity ?? "—"}${row.entity_id ? ` #${row.entity_id}` : ""}`,
    },
    {
      key: "description",
      header: "Detail",
      render: (row) => <span className="line-clamp-1 max-w-sm text-subtle">{row.description ?? "—"}</span>,
    },
    { key: "ip_address", header: "IP Address", render: (row) => row.ip_address ?? "—" },
    {
      key: "actions",
      header: "Actions",
      render: (row) => <RowActions recordLabel={`activity ${row.action}`} onView={() => setViewing(row)} />,
    },
  ];

  return (
    <>
      <PageHeader
        title="User Tracking"
        description="Audit trail of every state-changing action taken in the console and portal."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Audit Logs" }, { label: "User Tracking" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "User, action or description" }}
        actions={
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4" aria-hidden />
            Export
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="User Type" htmlFor="actor-type">
          <Select
            id="actor-type"
            value={(list.filters.actor_type as string) ?? ""}
            onChange={(event) => list.setFilter("actor_type", event.target.value)}
          >
            <option value="">All</option>
            {ACTOR_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="From" htmlFor="audit-from">
          <Input
            id="audit-from"
            type="date"
            value={(list.filters.date_from as string) ?? ""}
            onChange={(event) => list.setFilter("date_from", event.target.value)}
          />
        </FilterField>
        <FilterField label="To" htmlFor="audit-to">
          <Input
            id="audit-to"
            type="date"
            value={(list.filters.date_to as string) ?? ""}
            onChange={(event) => list.setFilter("date_to", event.target.value)}
          />
        </FilterField>
        <Button variant="ghost" onClick={list.resetFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={logsQuery.data?.logs ?? []}
        rowKey={(row) => row.id}
        pagination={logsQuery.data?.pagination}
        loading={logsQuery.isLoading}
        noun="activities"
        emptyMessage="No activity matches these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      <Dialog open={viewing !== null} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Activity Details</DialogTitle>
            <DialogDescription>{viewing ? formatDateTime(viewing.timestamp) : null}</DialogDescription>
          </DialogHeader>
          {viewing ? (
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {[
                ["User", viewing.actor_name],
                ["User type", viewing.actor_type],
                ["Action", viewing.action],
                ["Target", `${viewing.entity ?? "—"}${viewing.entity_id ? ` #${viewing.entity_id}` : ""}`],
                ["IP address", viewing.ip_address],
                ["Correlation ID", viewing.correlation_id],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-medium text-subtle">{label}</dt>
                  <dd className="mt-0.5 text-sm break-words text-ink">{value || "—"}</dd>
                </div>
              ))}
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-subtle">Detail</dt>
                <dd className="mt-0.5 text-sm text-ink">{viewing.description || "—"}</dd>
              </div>
              {viewing.changes ? (
                <div className="sm:col-span-2">
                  <dt className="text-xs font-medium text-subtle">Changes</dt>
                  <dd>
                    <pre className="mt-1 max-h-64 overflow-auto rounded-xl border border-hairline bg-white p-3 font-mono text-xs">
                      {JSON.stringify(viewing.changes, null, 2)}
                    </pre>
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

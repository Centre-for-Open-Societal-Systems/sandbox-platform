"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareReply } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { QueryStatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { adminApi } from "@/lib/services/admin";
import { QUERY_STATUSES, QUERY_TYPES, queryTypeLabel } from "@/lib/support";
import { formatDateTime } from "@/lib/utils";
import type { SupportQuery } from "@/types/api";

/** Status the reply form proposes: answered, unless the query was already closed. */
function defaultReplyStatus(query: SupportQuery) {
  return query.status === 3 ? 3 : 2;
}

export default function UserQueriesPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "added_date" });
  const [viewing, setViewing] = React.useState<SupportQuery | null>(null);
  const [replying, setReplying] = React.useState<SupportQuery | null>(null);
  const [reply, setReply] = React.useState({ response: "", status: 2 });

  const queriesQuery = useQuery({
    queryKey: ["admin", "queries", list.query],
    queryFn: () => adminApi.listQueries(list.query),
  });

  const respond = useMutation({
    mutationFn: () => adminApi.respondToQuery(replying!.query_id, reply.response.trim(), reply.status),
    onSuccess: () => {
      notify("Reply sent to the user.", "success");
      setReplying(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "queries"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function openReply(query: SupportQuery) {
    setViewing(null);
    setReply({ response: query.response ?? "", status: defaultReplyStatus(query) });
    setReplying(query);
  }

  const columns: Column<SupportQuery>[] = [
    {
      key: "participant_name",
      header: "Name",
      render: (row) => (
        <div>
          <p className="font-medium">{row.participant_name || "—"}</p>
          <p className="text-xs text-subtle">{row.company_name || ""}</p>
        </div>
      ),
    },
    { key: "email_id", header: "Email Id", render: (row) => row.email_id ?? "—" },
    { key: "query_type", header: "Query Type", sortable: true, render: (row) => queryTypeLabel(row.query_type) },
    {
      key: "subject",
      header: "Subject",
      render: (row) => <span className="line-clamp-1 max-w-xs">{row.subject ?? "—"}</span>,
    },
    { key: "status", header: "Status", sortable: true, render: (row) => <QueryStatusBadge status={row.status} /> },
    {
      key: "added_date",
      header: "Created At",
      sortable: true,
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.added_date)}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`query ${row.subject ?? row.query_id}`}
          onView={() => setViewing(row)}
          extra={[{ icon: MessageSquareReply, label: "Reply", onClick: () => openReply(row) }]}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="User Queries"
        description="Questions raised from the portal's Support & Queries page. Replies are emailed to the user."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Participants" }, { label: "User Queries" }]}
        search={{
          value: list.searchInput,
          onChange: list.setSearchInput,
          placeholder: "Name, email, company or subject",
        }}
      />

      <FilterBar>
        <FilterField label="Status" htmlFor="query-status">
          <Select
            id="query-status"
            value={list.filters.status === undefined ? "" : String(list.filters.status)}
            onChange={(event) => list.setFilter("status", event.target.value)}
          >
            <option value="">All</option>
            {QUERY_STATUSES.map((status) => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="Query Type" htmlFor="query-type">
          <Select
            id="query-type"
            value={list.filters.query_type === undefined ? "" : String(list.filters.query_type)}
            onChange={(event) => list.setFilter("query_type", event.target.value)}
          >
            <option value="">All</option>
            {QUERY_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </Select>
        </FilterField>
        <Button variant="ghost" onClick={list.resetFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={queriesQuery.data?.queries ?? []}
        rowKey={(row) => row.query_id}
        pagination={queriesQuery.data?.pagination}
        loading={queriesQuery.isLoading}
        noun="queries"
        emptyMessage="No queries match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {/* ------------------------------------------------------------ view */}
      <Dialog open={viewing !== null} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Query Details</DialogTitle>
            <DialogDescription>{viewing ? formatDateTime(viewing.added_date) : null}</DialogDescription>
          </DialogHeader>
          {viewing ? (
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {[
                ["Name", viewing.participant_name],
                ["Email ID", viewing.email_id],
                ["Organisation Name", viewing.company_name],
                ["Query Type", queryTypeLabel(viewing.query_type)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-medium text-subtle">{label}</dt>
                  <dd className="mt-0.5 text-sm break-words text-ink">{value || "—"}</dd>
                </div>
              ))}
              <div>
                <dt className="text-xs font-medium text-subtle">Status</dt>
                <dd className="mt-1">
                  <QueryStatusBadge status={viewing.status} />
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-subtle">Subject</dt>
                <dd className="mt-0.5 text-sm break-words text-ink">{viewing.subject || "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium text-subtle">Description</dt>
                <dd className="mt-0.5 text-sm whitespace-pre-wrap break-words text-ink">
                  {viewing.description || "—"}
                </dd>
              </div>
              {viewing.response ? (
                <div className="sm:col-span-2 rounded-lg border border-hairline bg-surface-soft p-3">
                  <dt className="text-xs font-medium text-subtle">
                    Reply · {formatDateTime(viewing.responded_date)}
                  </dt>
                  <dd className="mt-0.5 text-sm whitespace-pre-wrap break-words text-ink">{viewing.response}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setViewing(null)}>
              Close
            </Button>
            {viewing ? (
              <Button onClick={() => openReply(viewing)}>
                <MessageSquareReply className="h-4 w-4" aria-hidden />
                {viewing.response ? "Edit reply" : "Reply"}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ----------------------------------------------------------- reply */}
      <Dialog open={replying !== null} onOpenChange={(open) => !open && setReplying(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Reply to Query</DialogTitle>
            <DialogDescription>
              {replying ? `${replying.subject ?? "Query"} — ${replying.participant_name || replying.email_id || ""}` : null}
            </DialogDescription>
          </DialogHeader>
          <form
            id="query-reply-form"
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!reply.response.trim()) {
                notify("Write a reply before sending.", "warning");
                return;
              }
              respond.mutate();
            }}
          >
            {replying?.description ? (
              <p className="max-h-32 overflow-auto rounded-lg bg-surface-soft p-3 text-sm whitespace-pre-wrap text-slate-700">
                {replying.description}
              </p>
            ) : null}
            <div className="flex flex-col gap-2">
              <Label htmlFor="query-reply" required>
                Reply
              </Label>
              <Textarea
                id="query-reply"
                rows={6}
                maxLength={4000}
                value={reply.response}
                onChange={(event) => setReply({ ...reply, response: event.target.value })}
                placeholder="Your answer is emailed to the user and shown on their Support page."
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="query-reply-status">Set status to</Label>
              <Select
                id="query-reply-status"
                value={reply.status}
                onChange={(event) => setReply({ ...reply, status: Number(event.target.value) })}
              >
                {QUERY_STATUSES.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </Select>
            </div>
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReplying(null)}>
              Cancel
            </Button>
            <Button type="submit" form="query-reply-form" loading={respond.isPending}>
              Send reply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

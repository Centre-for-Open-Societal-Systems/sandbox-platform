"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, MessageSquareReply, Send } from "lucide-react";

import { TicketThread } from "@/components/support/ticket-thread";
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
import type { SupportQuery, SupportThread } from "@/types/api";

const BODY_MAX = 4000;

export default function UserQueriesPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "added_date" });
  const [openId, setOpenId] = React.useState<number | null>(null);

  const queriesQuery = useQuery({
    queryKey: ["admin", "queries", list.query],
    queryFn: () => adminApi.listQueries(list.query),
  });

  const columns: Column<SupportQuery>[] = [
    {
      key: "ticket_no",
      header: "Ticket",
      render: (row) => (
        <span className="inline-flex items-center gap-2 whitespace-nowrap font-medium">
          {row.unread ? (
            <span className="h-2 w-2 rounded-full bg-brand-bright" title="New message from the user" aria-label="New message" />
          ) : null}
          {row.ticket_no ?? `#${row.query_id}`}
        </span>
      ),
    },
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
    { key: "query_type", header: "Ticket Type", sortable: true, render: (row) => queryTypeLabel(row.query_type) },
    {
      key: "subject",
      header: "Subject",
      render: (row) => (
        <span className="line-clamp-1 max-w-xs">
          {row.subject ?? "—"}
          {row.message_count && row.message_count > 1 ? (
            <span className="ml-1.5 text-xs text-subtle">({row.message_count})</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (row) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <QueryStatusBadge status={row.status} />
          {row.is_overdue ? (
            <span
              className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"
              title={`Answer was due ${formatDateTime(row.due_date ?? null)}`}
            >
              Overdue
            </span>
          ) : null}
        </span>
      ),
    },
    {
      key: "last_message_date",
      header: "Last Message",
      sortable: true,
      render: (row) => (
        <span className="whitespace-nowrap">
          {formatDateTime(row.last_message_date ?? row.added_date)}
          <span className="block text-xs text-subtle">
            {row.last_message_by === "admin" ? "by the team" : row.last_message_by === "participant" ? "by the user" : ""}
          </span>
        </span>
      ),
    },
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
          recordLabel={`ticket ${row.subject ?? row.query_id}`}
          onView={() => setOpenId(row.query_id)}
          extra={[{ icon: MessageSquareReply, label: "Open conversation", onClick: () => setOpenId(row.query_id) }]}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Support Tickets"
        description="Tickets raised from the portal's Help & Support page. Each ticket is a conversation; replies are emailed to the user."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Participants" }, { label: "Support Tickets" }]}
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
        <FilterField label="Ticket Type" htmlFor="query-type">
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
        noun="tickets"
        emptyMessage="No tickets match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {/* Keyed by ticket: each one opens with a clean composer. */}
      <TicketDialog
        key={openId ?? "none"}
        queryId={openId}
        onClose={() => {
          setOpenId(null);
          void queryClient.invalidateQueries({ queryKey: ["admin", "queries"] });
        }}
        notify={notify}
      />
    </>
  );
}

/** One ticket as a conversation: history, a reply box (or a staff-only note) and the status. */
function TicketDialog({
  queryId,
  onClose,
  notify,
}: {
  queryId: number | null;
  onClose: () => void;
  notify: (message: string, kind?: "success" | "error" | "warning" | "info") => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = React.useState("");
  const [internal, setInternal] = React.useState(false);
  const [status, setStatus] = React.useState(2);

  const thread = useQuery({
    queryKey: ["admin", "query", queryId],
    queryFn: () => adminApi.getQuery(queryId!),
    enabled: queryId !== null,
  });

  function refreshed(data: SupportThread) {
    queryClient.setQueryData(["admin", "query", data.query_id], data);
    void queryClient.invalidateQueries({ queryKey: ["admin", "queries"] });
  }

  const send = useMutation({
    mutationFn: () => adminApi.sendQueryMessage(queryId!, draft.trim(), { internal, status }),
    onSuccess: (data) => {
      notify(internal ? "Note saved (only staff can see it)." : "Reply sent to the user.", "success");
      setDraft("");
      refreshed(data);
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const changeStatus = useMutation({
    mutationFn: (next: number) => adminApi.setQueryStatus(queryId!, next),
    onSuccess: (data) => {
      notify("Status updated.", "success");
      refreshed(data);
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const data = thread.data;

  return (
    <Dialog open={queryId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {data ? `${data.ticket_no} · ${data.subject ?? "Ticket"}` : "Ticket"}
          </DialogTitle>
          <DialogDescription>
            {data
              ? `${data.participant_name || "—"}${data.company_name ? ` · ${data.company_name}` : ""} · ${data.email_id ?? ""} · ${queryTypeLabel(data.query_type)} · raised ${formatDateTime(data.added_date)}`
              : "Loading…"}
          </DialogDescription>
        </DialogHeader>

        {thread.isError ? (
          <p className="text-sm text-red-600">{(thread.error as Error).message}</p>
        ) : data ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <QueryStatusBadge status={data.status} />
              {data.is_overdue ? (
                <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">
                  Overdue · was due {formatDateTime(data.due_date ?? null)}
                </span>
              ) : null}
              <div className="ml-auto flex items-center gap-2">
                <Label htmlFor="ticket-status" className="text-xs">
                  Status
                </Label>
                <Select
                  id="ticket-status"
                  className="h-8 w-40 text-sm"
                  value={data.status}
                  disabled={changeStatus.isPending}
                  onChange={(event) => changeStatus.mutate(Number(event.target.value))}
                >
                  {QUERY_STATUSES.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            <div className="max-h-[45vh] overflow-y-auto rounded-xl bg-surface-soft p-3">
              <TicketThread messages={data.messages} viewer="admin" />
            </div>

            <form
              id="ticket-reply-form"
              className="flex flex-col gap-3"
              onSubmit={(event) => {
                event.preventDefault();
                if (!draft.trim()) {
                  notify("Write a message before sending.", "warning");
                  return;
                }
                send.mutate();
              }}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="ticket-reply">{internal ? "Internal note" : "Reply to the user"}</Label>
                <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={internal}
                    onChange={(event) => setInternal(event.target.checked)}
                    className="h-3.5 w-3.5"
                  />
                  <Lock className="h-3 w-3" aria-hidden />
                  Internal note (staff only, no email)
                </label>
              </div>
              <Textarea
                id="ticket-reply"
                rows={4}
                maxLength={BODY_MAX}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={
                  internal
                    ? "Only staff can see this note."
                    : "Your answer is emailed to the user and shown on their Help & Support page."
                }
              />
              {!internal ? (
                <div className="flex items-center gap-2">
                  <Label htmlFor="ticket-reply-status" className="text-xs">
                    After sending, set status to
                  </Label>
                  <Select
                    id="ticket-reply-status"
                    className="h-8 w-40 text-sm"
                    value={status}
                    onChange={(event) => setStatus(Number(event.target.value))}
                  >
                    {QUERY_STATUSES.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : null}
            </form>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button type="submit" form="ticket-reply-form" loading={send.isPending} disabled={!data}>
            <Send className="h-4 w-4" aria-hidden />
            {internal ? "Save note" : "Send reply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

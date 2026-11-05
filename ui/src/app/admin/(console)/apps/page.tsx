"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, RefreshCw, RotateCcw, X } from "lucide-react";

import { AppStatusBadge, GatewayBadge, SubscriptionBadge, limitText } from "@/components/apps/app-ui";
import { Badge } from "@/components/ui/badge";
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
import { IconAction, RowActions } from "@/components/ui/row-actions";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { adminAppsApi } from "@/lib/services/apps";
import { formatDateTime } from "@/lib/utils";
import type { AdminApp, AppSubscription } from "@/types/api";

type Decision = "approve" | "reject" | "revoke";

/** Product-level decisions: what needs a reason, and how each action reads. */
const DECISIONS: Record<Decision, { title: string; label: string; needsRemarks: boolean }> = {
  approve: { title: "Approve access", label: "Approve", needsRemarks: false },
  reject: { title: "Reject request", label: "Reject", needsRemarks: true },
  revoke: { title: "Revoke access", label: "Revoke", needsRemarks: true },
};

type AppAction = "approve" | "reject" | "revoke";

/** App-level decisions. Approving a new app issues its first API key and secret. */
const APP_ACTIONS: Record<
  AppAction,
  { title: string; description: string; label: string; field: string; needsReason: boolean; done: string }
> = {
  approve: {
    title: "Approve app",
    description:
      "Every open API product request of this app is granted, and its first API key and secret are issued to the participant.",
    label: "Approve",
    field: "Remarks (optional, shown to the participant)",
    needsReason: false,
    done: "App approved. Its API key and secret are now available to the participant.",
  },
  reject: {
    title: "Reject app",
    description: "No key is issued. The participant sees the reason and can create a new app.",
    label: "Reject",
    field: "Reason",
    needsReason: true,
    done: "App rejected.",
  },
  revoke: {
    title: "Revoke app",
    description: "All keys of this app stop working at the gateway. The participant sees the reason.",
    label: "Revoke",
    field: "Reason",
    needsReason: true,
    done: "App revoked. Its keys no longer work.",
  },
};

export default function AppsPage() {
  const queryClient = useQueryClient();
  const list = useListQuery({ sortBy: "added_date" });
  const [viewingId, setViewingId] = React.useState<number | null>(null);

  const appsQuery = useQuery({
    queryKey: ["admin", "apps", list.query],
    queryFn: () => adminAppsApi.listApps(list.query),
  });
  const productsQuery = useQuery({
    queryKey: ["admin", "api-products", "all"],
    queryFn: () => adminAppsApi.listProducts({ limit: 200, sort_by: "sort_order", sort_dir: "asc" }),
  });

  const columns: Column<AdminApp>[] = [
    {
      key: "name",
      header: "App",
      sortable: true,
      render: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="font-mono text-xs text-subtle">{row.gateway_consumer}</p>
        </div>
      ),
    },
    {
      key: "participant",
      header: "Participant",
      render: (row) => (
        <div>
          <p>{row.participant_name || row.participant_email || "—"}</p>
          <p className="text-xs text-subtle">{row.company_name ?? ""}</p>
        </div>
      ),
    },
    {
      key: "products",
      header: "API Products",
      render: (row) => (
        <div className="flex max-w-xs flex-wrap gap-1">
          {row.products.length === 0 ? <span className="text-subtle">None</span> : null}
          {row.products.map((p) => (
            <span key={p.api_product_id} title={p.status_label}>
              <SubscriptionBadge status={p.status} label={p.display_name} />
            </span>
          ))}
        </div>
      ),
    },
    {
      key: "keys",
      header: "Active keys",
      render: (row) => row.credentials.filter((c) => c.status === 1).length,
    },
    { key: "gateway_status", header: "Gateway", render: (row) => <GatewayBadge status={row.gateway_status} /> },
    { key: "status", header: "Status", sortable: true, render: (row) => <AppStatusBadge status={row.status} label={row.status_label} /> },
    {
      key: "added_date",
      header: "Created",
      sortable: true,
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.added_date)}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => <RowActions recordLabel={`app ${row.name}`} onView={() => setViewingId(row.id)} />,
    },
  ];

  return (
    <>
      <PageHeader
        title="Apps & Keys"
        description="Participant apps, the API products they asked for and their keys. Every decision is written to the API gateway at once."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Participants" }, { label: "Apps & Keys" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "App name or consumer" }}
      />

      <FilterBar>
        <FilterField label="Show" htmlFor="apps-pending">
          <Select
            id="apps-pending"
            value={list.filters.pending_only ? "pending" : ""}
            onChange={(event) => list.setFilter("pending_only", event.target.value === "pending" ? true : undefined)}
          >
            <option value="">All apps</option>
            <option value="pending">Awaiting a decision (new apps, product requests)</option>
          </Select>
        </FilterField>
        <FilterField label="Status" htmlFor="apps-status">
          <Select
            id="apps-status"
            value={list.filters.status === undefined ? "" : String(list.filters.status)}
            onChange={(event) => list.setFilter("status", event.target.value === "" ? undefined : Number(event.target.value))}
          >
            <option value="">All</option>
            <option value="0">Awaiting approval</option>
            <option value="1">Active</option>
            <option value="2">Revoked</option>
            <option value="3">Rejected</option>
          </Select>
        </FilterField>
        <FilterField label="API Product" htmlFor="apps-product">
          <Select
            id="apps-product"
            value={list.filters.api_product_id === undefined ? "" : String(list.filters.api_product_id)}
            onChange={(event) =>
              list.setFilter("api_product_id", event.target.value === "" ? undefined : Number(event.target.value))
            }
          >
            <option value="">All</option>
            {(productsQuery.data?.api_products ?? []).map((p) => (
              <option key={p.api_product_id} value={p.api_product_id}>
                {p.display_name}
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
        rows={appsQuery.data?.apps ?? []}
        rowKey={(row) => row.id}
        pagination={appsQuery.data?.pagination}
        loading={appsQuery.isLoading}
        noun="apps"
        emptyMessage="No apps match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {viewingId !== null ? (
        <AppDetailDialog
          appId={viewingId}
          onClose={() => setViewingId(null)}
          onChanged={() => queryClient.invalidateQueries({ queryKey: ["admin", "apps"] })}
        />
      ) : null}
    </>
  );
}

function AppDetailDialog({ appId, onClose, onChanged }: { appId: number; onClose: () => void; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [deciding, setDeciding] = React.useState<{ product: AppSubscription; decision: Decision } | null>(null);
  const [remarks, setRemarks] = React.useState("");
  const [acting, setActing] = React.useState<AppAction | null>(null);
  const [reason, setReason] = React.useState("");

  const appQuery = useQuery({ queryKey: ["admin", "apps", "detail", appId], queryFn: () => adminAppsApi.getApp(appId) });
  const app = appQuery.data;

  function updated(next: AdminApp, message: string) {
    queryClient.setQueryData(["admin", "apps", "detail", appId], next);
    onChanged();
    if (next.gateway_status === "FAILED") {
      notify(`${message} The gateway could not be updated: ${next.gateway_error ?? "unknown error"}`, "warning");
    } else {
      notify(message, "success");
    }
  }
  const onError = (error: Error) => notify(error.message, "error");

  const decide = useMutation({
    mutationFn: () => adminAppsApi.decide(appId, deciding!.product.api_product_id, deciding!.decision, remarks.trim()),
    onSuccess: (next) => {
      updated(next, `${DECISIONS[deciding!.decision].label}d: ${deciding!.product.display_name}.`);
      setDeciding(null);
    },
    onError,
  });
  const act = useMutation({
    mutationFn: () => {
      const text = reason.trim();
      if (acting === "approve") return adminAppsApi.approveApp(appId, text || undefined);
      if (acting === "reject") return adminAppsApi.rejectApp(appId, text);
      return adminAppsApi.revokeApp(appId, text);
    },
    onSuccess: (next) => {
      updated(next, APP_ACTIONS[acting ?? "revoke"].done);
      setActing(null);
    },
    onError,
  });

  function openAction(action: AppAction) {
    setReason("");
    setActing(action);
  }
  const restoreApp = useMutation({
    mutationFn: () => adminAppsApi.restoreApp(appId),
    onSuccess: (next) => updated(next, "App restored."),
    onError,
  });
  const resync = useMutation({
    mutationFn: () => adminAppsApi.resync(appId),
    onSuccess: (next) => updated(next, "Gateway re-synced."),
    onError,
  });

  function openDecision(product: AppSubscription, decision: Decision) {
    setRemarks("");
    setDeciding({ product, decision });
  }

  return (
    <>
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{app?.name ?? "App"}</DialogTitle>
            <DialogDescription>
              {app ? `${app.participant_name || app.participant_email || ""} · created ${formatDateTime(app.added_date)}` : "Loading…"}
            </DialogDescription>
          </DialogHeader>
          {app ? (
            <div className="flex max-h-[65vh] flex-col gap-5 overflow-auto">
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {[
                  ["Participant", `${app.participant_name ?? ""} <${app.participant_email ?? ""}>`],
                  ["Organisation", app.company_name],
                  ["Environment", app.environment],
                  ["Callback URL", app.callback_url],
                  ["Allowed IPs", app.allowed_ips.length ? app.allowed_ips.join(", ") : "Any address"],
                  ["Rate limit", limitText(app.rate_limit_per_minute, app.quota_per_day)],
                  ["Gateway consumer", app.gateway_consumer],
                  ["Last gateway sync", formatDateTime(app.gateway_synced_at)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-xs font-medium text-subtle">{label}</dt>
                    <dd className="mt-0.5 text-sm break-words text-ink">{value || "—"}</dd>
                  </div>
                ))}
                <div>
                  <dt className="text-xs font-medium text-subtle">Status</dt>
                  <dd className="mt-1 flex gap-2">
                    <AppStatusBadge status={app.status} label={app.status_label} />
                    <GatewayBadge status={app.gateway_status} />
                  </dd>
                </div>
                {app.description ? (
                  <div className="sm:col-span-2">
                    <dt className="text-xs font-medium text-subtle">Description</dt>
                    <dd className="mt-0.5 text-sm whitespace-pre-wrap text-ink">{app.description}</dd>
                  </div>
                ) : null}
                {app.status === 0 ? (
                  <div className="sm:col-span-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                    New app awaiting your decision. Approving the app (or any one of its API products) issues its first
                    API key and secret; rejecting it issues nothing.
                  </div>
                ) : null}
                {app.revoked_reason ? (
                  <div className="sm:col-span-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">
                    {app.status === 3 ? "Rejected" : "Revoked"}: {app.revoked_reason}
                  </div>
                ) : null}
                {app.gateway_error ? (
                  <div className="sm:col-span-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">{app.gateway_error}</div>
                ) : null}
              </dl>

              <section>
                <h3 className="mb-2 text-sm font-semibold">API products</h3>
                <div className="overflow-hidden rounded-lg border border-hairline">
                  <table className="w-full text-sm">
                    <thead className="bg-surface-soft text-left text-xs text-subtle">
                      <tr>
                        <th className="px-3 py-2">Product</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Remarks</th>
                        <th className="px-3 py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {app.products.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="px-3 py-3 text-subtle">
                            No API products requested.
                          </td>
                        </tr>
                      ) : null}
                      {app.products.map((p) => (
                        <tr key={p.api_product_id} className="border-t border-hairline">
                          <td className="px-3 py-2">
                            <p className="font-medium">{p.display_name}</p>
                            <p className="font-mono text-xs text-subtle">
                              {p.name} · {p.endpoints.length} API{p.endpoints.length === 1 ? "" : "s"}
                            </p>
                          </td>
                          <td className="px-3 py-2">
                            <SubscriptionBadge status={p.status} label={p.status_label} />
                          </td>
                          <td className="px-3 py-2 text-xs text-subtle">{p.remarks || "—"}</td>
                          <td className="px-3 py-2">
                            <div className="flex gap-2">
                              {p.status !== 1 ? (
                                <IconAction icon={Check} label={`Approve ${p.display_name}`} onClick={() => openDecision(p, "approve")} />
                              ) : null}
                              {p.status === 0 ? (
                                <IconAction icon={X} tone="danger" label={`Reject ${p.display_name}`} onClick={() => openDecision(p, "reject")} />
                              ) : null}
                              {p.status === 1 ? (
                                <IconAction icon={Ban} tone="danger" label={`Revoke ${p.display_name}`} onClick={() => openDecision(p, "revoke")} />
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section>
                <h3 className="mb-2 text-sm font-semibold">Keys</h3>
                {app.credentials.length === 0 ? (
                  <p className="rounded-lg bg-surface-soft px-3 py-2 text-sm text-subtle">
                    No keys yet: the first API key and secret are issued when the app is approved.
                  </p>
                ) : null}
                <ul className="flex flex-col gap-2">
                  {app.credentials.map((c) => (
                    <li key={c.credential_id} className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline px-3 py-2 text-sm">
                      <code className="font-mono">{c.api_key_prefix}…</code>
                      <span className="text-xs text-subtle">secret {c.api_secret_hint}</span>
                      <Badge variant={c.status === 1 ? "success" : "neutral"}>{c.status_label}</Badge>
                      <span className="ml-auto text-xs text-subtle">
                        Issued {formatDateTime(c.issued_date)}
                        {c.revoked_date ? ` · revoked ${formatDateTime(c.revoked_date)}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>

              {app.gateway_warnings.length > 0 || app.gateway_routes.length > 0 ? (
                <section>
                  <h3 className="mb-2 text-sm font-semibold">Gateway</h3>
                  <p className="text-xs text-subtle">{app.gateway_routes.length} route(s) granted to this app.</p>
                  {app.gateway_warnings.map((warning) => (
                    <p key={warning} className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">
                      {warning}
                    </p>
                  ))}
                </section>
              ) : null}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-subtle">Loading…</p>
          )}
          <DialogFooter className="flex-wrap">
            {app ? (
              <>
                <Button variant="outline" onClick={() => resync.mutate()} loading={resync.isPending}>
                  <RefreshCw className="h-4 w-4" aria-hidden />
                  Re-sync gateway
                </Button>
                {app.status === 0 || app.status === 3 ? (
                  <Button onClick={() => openAction("approve")}>
                    <Check className="h-4 w-4" aria-hidden />
                    Approve app
                  </Button>
                ) : null}
                {app.status === 0 ? (
                  <Button variant="destructive" onClick={() => openAction("reject")}>
                    <X className="h-4 w-4" aria-hidden />
                    Reject app
                  </Button>
                ) : null}
                {app.status === 1 ? (
                  <Button variant="destructive" onClick={() => openAction("revoke")}>
                    <Ban className="h-4 w-4" aria-hidden />
                    Revoke app
                  </Button>
                ) : null}
                {app.status === 2 ? (
                  <Button onClick={() => restoreApp.mutate()} loading={restoreApp.isPending}>
                    <RotateCcw className="h-4 w-4" aria-hidden />
                    Restore app
                  </Button>
                ) : null}
              </>
            ) : null}
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ------------------------------------------------ product decision */}
      <Dialog open={deciding !== null} onOpenChange={(open) => !open && setDeciding(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{deciding ? DECISIONS[deciding.decision].title : ""}</DialogTitle>
            <DialogDescription>
              {deciding ? `${deciding.product.display_name} for app "${app?.name ?? ""}"` : null}
            </DialogDescription>
          </DialogHeader>
          <form
            id="app-decision-form"
            onSubmit={(event) => {
              event.preventDefault();
              decide.mutate();
            }}
            className="flex flex-col gap-2"
          >
            <Label htmlFor="app-decision-remarks" required={deciding ? DECISIONS[deciding.decision].needsRemarks : false}>
              Remarks
            </Label>
            <Textarea
              id="app-decision-remarks"
              rows={3}
              maxLength={1000}
              minLength={deciding && DECISIONS[deciding.decision].needsRemarks ? 3 : undefined}
              required={deciding ? DECISIONS[deciding.decision].needsRemarks : false}
              value={remarks}
              onChange={(event) => setRemarks(event.target.value)}
              placeholder="Shown to the participant on their app."
            />
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeciding(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="app-decision-form"
              variant={deciding?.decision === "approve" ? "primary" : "destructive"}
              loading={decide.isPending}
            >
              {deciding ? DECISIONS[deciding.decision].label : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* --------------------------------------- approve / reject / revoke app */}
      <Dialog open={acting !== null} onOpenChange={(open) => !open && setActing(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {acting ? APP_ACTIONS[acting].title : ""}
              {app ? `: ${app.name}` : ""}
            </DialogTitle>
            <DialogDescription>{acting ? APP_ACTIONS[acting].description : null}</DialogDescription>
          </DialogHeader>
          <form
            id="app-action-form"
            onSubmit={(event) => {
              event.preventDefault();
              act.mutate();
            }}
            className="flex flex-col gap-2"
          >
            <Label htmlFor="app-action-reason" required={acting ? APP_ACTIONS[acting].needsReason : false}>
              {acting ? APP_ACTIONS[acting].field : "Reason"}
            </Label>
            <Textarea
              id="app-action-reason"
              rows={3}
              minLength={acting && APP_ACTIONS[acting].needsReason ? 3 : undefined}
              maxLength={1000}
              required={acting ? APP_ACTIONS[acting].needsReason : false}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Shown to the participant on their app."
            />
          </form>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActing(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="app-action-form"
              variant={acting === "approve" ? "primary" : "destructive"}
              loading={act.isPending}
            >
              {acting ? APP_ACTIONS[acting].label : ""}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

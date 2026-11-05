"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronUp,
  Hourglass,
  KeyRound,
  Loader2,
  PackagePlus,
  Pencil,
  Plus,
  ShieldAlert,
  Trash2,
  TriangleAlert,
} from "lucide-react";

import {
  AppStatusBadge,
  GatewayBadge,
  SecretField,
  SubscriptionBadge,
  limitText,
  parseIpList,
} from "@/components/apps/app-ui";
import { PageBanner } from "@/components/layout/page-banner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MethodBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { appsApi } from "@/lib/services/apps";
import { cn, formatDateTime } from "@/lib/utils";
import type { AppSubscription, AvailableApiProduct, IssuedCredential, ParticipantApp } from "@/types/api";

const APPS_KEY = ["participant", "apps"];
/** Same limit as the API (MAX_ACTIVE_CREDENTIALS_PER_APP). */
const MAX_ACTIVE_KEYS = 2;

export default function MyAppsPage() {
  const { notify } = useToast();
  const appsQuery = useQuery({ queryKey: APPS_KEY, queryFn: () => appsApi.list() });
  const productsQuery = useQuery({
    queryKey: ["participant", "api-products"],
    queryFn: () => appsApi.availableProducts(),
  });
  const [creating, setCreating] = React.useState(false);
  const [issued, setIssued] = React.useState<{ appName: string; credential: IssuedCredential } | null>(null);

  const apps = appsQuery.data ?? [];

  return (
    <div>
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="My Apps"
        title="My Apps"
        description="Create an app for each system that calls Open Agri Net APIs. An administrator approves every new app; it then gets its own API key and secret, and can call only the API products it has been granted."
        image="/assets/home/tea-rows.webp"
      />

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-subtle">
          Send the key in the <code className="rounded bg-surface-soft px-1 font-mono">apikey</code> header on every
          call to the gateway.
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" aria-hidden />
          Create app
        </Button>
      </div>

      {appsQuery.isLoading ? (
        <p className="mt-10 flex items-center justify-center gap-2 text-sm text-subtle">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading your apps…
        </p>
      ) : apps.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-hairline bg-white p-10 text-center">
          <KeyRound className="mx-auto h-8 w-8 text-brand-bright" aria-hidden />
          <h2 className="mt-3 font-semibold text-nav-active">No apps yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-subtle">
            Create an app and pick the API products it needs. Once an administrator approves it, you get an API key and
            secret to call them.
          </p>
          <Button className="mt-5" onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" aria-hidden />
            Create your first app
          </Button>
        </div>
      ) : (
        <ul className="mt-6 flex flex-col gap-5">
          {apps.map((app) => (
            <AppCard
              key={app.app_id}
              app={app}
              products={productsQuery.data ?? []}
              onIssued={(credential) => setIssued({ appName: app.name, credential })}
            />
          ))}
        </ul>
      )}

      {creating ? (
        <CreateAppDialog
          products={productsQuery.data ?? []}
          loadingProducts={productsQuery.isLoading}
          onClose={() => setCreating(false)}
          onCreated={(app, credential) => {
            setCreating(false);
            if (credential) {
              setIssued({ appName: app.name, credential });
            } else {
              notify(
                `"${app.name}" is submitted for approval. Your API key and secret appear here once an administrator approves it.`,
                "success",
              );
            }
          }}
        />
      ) : null}

      <Dialog open={issued !== null} onOpenChange={(open) => !open && setIssued(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Your new key for {issued?.appName}</DialogTitle>
            <DialogDescription>Both are also listed on the app, masked until you reveal them.</DialogDescription>
          </DialogHeader>
          {issued ? (
            <div className="flex flex-col gap-4">
              <SecretField label="API key" value={issued.credential.api_key} />
              <SecretField label="Secret" value={issued.credential.api_secret} />
              <p className="flex gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
                Keep both out of source code and browsers. If they leak, revoke the key and issue a new one.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button onClick={() => setIssued(null)}>I have copied them</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AppCard({
  app,
  products,
  onIssued,
}: {
  app: ParticipantApp;
  products: AvailableApiProduct[];
  onIssued: (credential: IssuedCredential) => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { confirm, dialog } = useConfirm();
  const [editing, setEditing] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const pending = app.status === 0;
  const active = app.status === 1;
  const revoked = app.status === 2;
  const rejected = app.status === 3;
  /** Nothing more can be done with the app itself (it can still be deleted). */
  const blocked = revoked || rejected;
  const activeKeys = app.credentials.filter((c) => c.status === 1);

  function refreshWith(next?: ParticipantApp) {
    if (next) {
      queryClient.setQueryData<ParticipantApp[]>(APPS_KEY, (apps) =>
        (apps ?? []).map((a) => (a.app_id === next.app_id ? next : a)),
      );
    }
    queryClient.invalidateQueries({ queryKey: APPS_KEY });
  }
  const onError = (error: Error) => notify(error.message, "error");

  const issueKey = useMutation({
    mutationFn: () => appsApi.issueKey(app.app_id),
    onSuccess: (credential) => {
      refreshWith();
      onIssued(credential);
    },
    onError,
  });
  const revokeKey = useMutation({
    mutationFn: (credentialId: string) => appsApi.revokeKey(app.app_id, credentialId),
    onSuccess: (next) => {
      refreshWith(next);
      notify("Key revoked. Calls with it are now refused.", "success");
    },
    onError,
  });
  const withdraw = useMutation({
    mutationFn: (apiProductId: number) => appsApi.withdrawProduct(app.app_id, apiProductId),
    onSuccess: (next) => {
      refreshWith(next);
      notify("API product removed from the app.", "success");
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: () => appsApi.remove(app.app_id),
    onSuccess: () => {
      refreshWith();
      notify("App deleted. Its keys no longer work.", "success");
    },
    onError,
  });

  const requestable = products.filter(
    (p) => !app.products.some((s) => s.api_product_id === p.api_product_id && (s.status === 0 || s.status === 1)),
  );

  return (
    <li className="rounded-2xl border border-hairline bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold text-nav-active">{app.name}</h2>
            <AppStatusBadge status={app.status} label={app.status_label} />
            <GatewayBadge status={app.gateway_status} />
          </div>
          <p className="mt-1 text-sm text-subtle">
            {app.description || "No description."} · created {formatDateTime(app.added_date)}
          </p>
          {app.callback_url ? <p className="mt-1 text-xs text-subtle">Callback: {app.callback_url}</p> : null}
          <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
            <div className="flex gap-1">
              <dt className="text-subtle">Allowed IPs:</dt>
              <dd className="font-medium text-ink">
                {app.allowed_ips.length ? <code className="font-mono">{app.allowed_ips.join(", ")}</code> : "Any address"}
              </dd>
            </div>
            {app.rate_limit_per_minute || app.quota_per_day ? (
              <div className="flex gap-1">
                <dt className="text-subtle">Rate limit:</dt>
                <dd className="font-medium text-ink">{limitText(app.rate_limit_per_minute, app.quota_per_day)}</dd>
              </div>
            ) : null}
          </dl>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={blocked}>
            <Pencil className="h-3.5 w-3.5" aria-hidden />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={async () => {
              if (
                await confirm({
                  title: "Delete app?",
                  consequence: `"${app.name}" and all its keys stop working immediately.`,
                  confirmLabel: "Delete",
                })
              ) {
                remove.mutate();
              }
            }}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
            Delete
          </Button>
        </div>
      </div>

      {pending ? (
        <p className="mt-4 flex gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          <Hourglass className="h-4 w-4 shrink-0" aria-hidden />
          Awaiting approval. An administrator reviews every new app; your API key and secret appear here once it is
          approved.
        </p>
      ) : null}
      {rejected ? (
        <p className="mt-4 flex gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />
          An administrator declined this app{app.revoked_reason ? `: ${app.revoked_reason}` : "."} No key was issued; you
          can delete it and create a new one with the corrected details.
        </p>
      ) : null}
      {revoked ? (
        <p className="mt-4 flex gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />
          An administrator revoked this app{app.revoked_reason ? `: ${app.revoked_reason}` : "."} Its keys do not work.
        </p>
      ) : null}
      {app.gateway_status === "FAILED" ? (
        <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          The gateway could not be updated yet; your changes are saved and an administrator can re-sync them.
        </p>
      ) : null}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* ------------------------------------------------------- products */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">API products</h3>
              <p className="text-xs text-subtle">Each product is a bundle of APIs this app&apos;s key may call.</p>
            </div>
            <Button variant="link" size="sm" onClick={() => setAdding(true)} disabled={blocked || requestable.length === 0}>
              <PackagePlus className="h-3.5 w-3.5" aria-hidden />
              Request more
            </Button>
          </div>
          {app.products.length === 0 ? (
            <p className="rounded-lg bg-surface-soft p-3 text-sm text-subtle">
              No API products yet: the key works for nothing until you request one.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {app.products.map((p) => (
                <AppProductItem
                  key={p.api_product_id}
                  product={p}
                  canWithdraw={p.status !== 3 && !blocked}
                  withdrawing={withdraw.isPending}
                  onWithdraw={async () => {
                    if (
                      await confirm({
                        title: `Withdraw ${p.display_name}?`,
                        consequence:
                          p.status === 1
                            ? `"${app.name}" loses access to its ${p.endpoints.length} API(s) at once. You can request the product again later; products that need approval go back to the administrator.`
                            : `The request for ${p.display_name} is withdrawn. You can request it again later.`,
                        confirmLabel: "Withdraw",
                      })
                    ) {
                      withdraw.mutate(p.api_product_id);
                    }
                  }}
                />
              ))}
            </ul>
          )}
        </section>

        {/* ----------------------------------------------------------- keys */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Keys</h3>
            <Button
              variant="link"
              size="sm"
              onClick={() => issueKey.mutate()}
              loading={issueKey.isPending}
              disabled={!active || activeKeys.length >= MAX_ACTIVE_KEYS}
              title={
                pending
                  ? "Keys are issued when the app is approved"
                  : activeKeys.length >= MAX_ACTIVE_KEYS
                    ? "Revoke a key first"
                    : "Issue a second key to rotate without downtime"
              }
            >
              <KeyRound className="h-3.5 w-3.5" aria-hidden />
              New key
            </Button>
          </div>
          {activeKeys.length === 0 ? (
            <p className="rounded-lg bg-surface-soft p-3 text-sm text-subtle">
              {pending
                ? "Your API key and secret are issued when an administrator approves the app."
                : active
                  ? "No active key. Issue one to call the APIs."
                  : "No active key."}
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {activeKeys.map((c) => (
                <li key={c.credential_id} className="rounded-lg border border-hairline p-3">
                  <div className="flex flex-col gap-2">
                    {c.api_key ? <SecretField label="API key" value={c.api_key} masked /> : null}
                    {c.api_secret ? (
                      <SecretField label="Secret" value={c.api_secret} masked />
                    ) : (
                      <span className="text-xs text-subtle">Secret {c.api_secret_hint}</span>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-subtle">
                    <span>Issued {formatDateTime(c.issued_date)}</span>
                    {c.last_used_date ? <span>Used in try-it {formatDateTime(c.last_used_date)}</span> : null}
                    <button
                      type="button"
                      className="ml-auto font-medium text-red-700 hover:underline"
                      onClick={async () => {
                        if (
                          await confirm({
                            title: "Revoke this key?",
                            consequence: `Calls with ${c.api_key_prefix}… are refused from now on.`,
                            confirmLabel: "Revoke",
                          })
                        ) {
                          revokeKey.mutate(c.credential_id);
                        }
                      }}
                    >
                      Revoke
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {app.credentials.length > activeKeys.length ? (
            <p className="mt-2 text-xs text-subtle">{app.credentials.length - activeKeys.length} revoked key(s) kept for the record.</p>
          ) : null}
        </section>
      </div>

      {editing ? <EditAppDialog app={app} onClose={() => setEditing(false)} onSaved={(next) => { setEditing(false); refreshWith(next); }} /> : null}
      {adding ? (
        <RequestProductsDialog
          app={app}
          products={requestable}
          onClose={() => setAdding(false)}
          onSaved={(next) => {
            setAdding(false);
            refreshWith(next);
          }}
        />
      ) : null}
      {dialog}
    </li>
  );
}

/** One API product on an app: status, limits, its APIs (expandable) and Withdraw. */
function AppProductItem({
  product: p,
  canWithdraw,
  withdrawing,
  onWithdraw,
}: {
  product: AppSubscription;
  canWithdraw: boolean;
  withdrawing: boolean;
  onWithdraw: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <li className="rounded-lg border border-hairline px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{p.display_name}</span>
        <SubscriptionBadge status={p.status} label={p.status_label} />
        {p.rate_limit_per_minute || p.quota_per_day ? (
          <span className="text-xs text-subtle">{limitText(p.rate_limit_per_minute, p.quota_per_day)}</span>
        ) : null}
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-medium text-brand-bright hover:underline"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {p.endpoints.length} API{p.endpoints.length === 1 ? "" : "s"}
          {open ? <ChevronUp className="h-3 w-3" aria-hidden /> : <ChevronDown className="h-3 w-3" aria-hidden />}
        </button>
        {canWithdraw ? (
          <button
            type="button"
            className="ml-auto text-xs text-subtle hover:text-red-700"
            onClick={onWithdraw}
            disabled={withdrawing}
            title="Take this product off the app: its key stops working for these APIs"
          >
            Withdraw
          </button>
        ) : null}
      </div>
      {p.remarks && p.status !== 1 ? <p className="mt-1 text-xs text-subtle">{p.remarks}</p> : null}
      {open ? (
        p.endpoints.length === 0 ? (
          <p className="mt-2 text-xs text-subtle">This product has no APIs yet.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1 border-t border-hairline pt-2">
            {p.endpoints.map((e) => (
              <li key={e.endpoint_id} className="flex flex-wrap items-center gap-2 text-xs">
                <MethodBadge method={e.method} />
                <span className="font-medium text-ink">{e.display_name || e.endpoint_url}</span>
                <code className="truncate font-mono text-subtle">{e.endpoint_url}</code>
                {e.product_name ? <span className="ml-auto text-subtle">{e.product_name}</span> : null}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </li>
  );
}

/** Checkbox list of API products, each expandable to its endpoints. */
function ProductPicker({
  products,
  selected,
  onChange,
}: {
  products: AvailableApiProduct[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const [open, setOpen] = React.useState<number | null>(null);
  if (products.length === 0) {
    return <p className="rounded-lg bg-surface-soft p-3 text-sm text-subtle">No API products are available to request.</p>;
  }
  return (
    <ul className="flex max-h-72 flex-col gap-2 overflow-auto">
      {products.map((p) => {
        const checked = selected.includes(p.api_product_id);
        return (
          <li key={p.api_product_id} className={cn("rounded-lg border px-3 py-2", checked ? "border-brand-600 bg-[#f3faf4]" : "border-hairline")}>
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) =>
                  onChange(event.target.checked ? [...selected, p.api_product_id] : selected.filter((id) => id !== p.api_product_id))
                }
                className="mt-1 h-4 w-4 accent-brand-600"
              />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {p.display_name}
                  <Badge variant={p.approval_type === "AUTO" ? "info" : "warning"}>
                    {p.approval_type === "AUTO" ? "Instant access" : "Needs approval"}
                  </Badge>
                </span>
                {p.description ? <span className="mt-0.5 block text-xs text-subtle">{p.description}</span> : null}
                {p.rate_limit_per_minute || p.quota_per_day ? (
                  <span className="mt-0.5 block text-xs text-subtle">
                    Rate limit: {limitText(p.rate_limit_per_minute, p.quota_per_day)}
                  </span>
                ) : null}
              </span>
            </label>
            <button
              type="button"
              className="mt-1 ml-7 text-xs font-medium text-brand-bright hover:underline"
              onClick={() => setOpen(open === p.api_product_id ? null : p.api_product_id)}
              aria-expanded={open === p.api_product_id}
            >
              {open === p.api_product_id ? "Hide" : "Show"} {p.endpoints.length} endpoint(s)
            </button>
            {open === p.api_product_id ? (
              <ul className="mt-2 ml-7 flex flex-col gap-1">
                {p.endpoints.map((e) => (
                  <li key={e.endpoint_id} className="flex items-center gap-2 text-xs">
                    <MethodBadge method={e.method} />
                    <code className="truncate font-mono">{e.endpoint_url}</code>
                  </li>
                ))}
              </ul>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

/** Optional IP whitelist: one IP or CIDR per line; empty = calls from any address. */
function IpWhitelistField({
  id,
  value,
  onChange,
  className,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <Label htmlFor={id}>Allowed IP addresses (optional)</Label>
      <Textarea
        id={id}
        rows={2}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={"203.0.113.10\n198.51.100.0/24"}
        className="font-mono text-sm"
      />
      <p className="text-xs text-subtle">
        One IP or CIDR range per line, e.g. your servers&apos; public addresses. Calls with this app&apos;s keys from any
        other address get 403. Leave empty to allow any address.
      </p>
    </div>
  );
}

function CreateAppDialog({
  products,
  loadingProducts,
  onClose,
  onCreated,
}: {
  products: AvailableApiProduct[];
  loadingProducts: boolean;
  onClose: () => void;
  onCreated: (app: ParticipantApp, credential: IssuedCredential | null) => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [form, setForm] = React.useState({ name: "", description: "", callback_url: "", allowed_ips: "" });
  const [selected, setSelected] = React.useState<number[]>([]);

  const create = useMutation({
    mutationFn: () =>
      appsApi.create({
        name: form.name.trim(),
        description: form.description.trim() || null,
        callback_url: form.callback_url.trim() || null,
        allowed_ips: parseIpList(form.allowed_ips),
        api_product_ids: selected,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: APPS_KEY });
      onCreated(created.app, created.credential);
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create app</DialogTitle>
          <DialogDescription>
            Name the system that will call the APIs and choose what it needs. An administrator reviews the app; its API
            key and secret are issued on approval.
          </DialogDescription>
        </DialogHeader>
        <form
          id="create-app-form"
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="app-name" required>
                App name
              </Label>
              <Input
                id="app-name"
                required
                minLength={2}
                maxLength={100}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Field Survey App"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="app-callback">Callback URL</Label>
              <Input
                id="app-callback"
                type="url"
                maxLength={1000}
                value={form.callback_url}
                onChange={(event) => setForm({ ...form, callback_url: event.target.value })}
                placeholder="https://example.org/oan/callback"
              />
            </div>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label htmlFor="app-description">Description</Label>
              <Textarea
                id="app-description"
                rows={2}
                maxLength={1000}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </div>
            <IpWhitelistField
              id="app-ips"
              className="sm:col-span-2"
              value={form.allowed_ips}
              onChange={(allowed_ips) => setForm({ ...form, allowed_ips })}
            />
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">API products</legend>
            {loadingProducts ? (
              <p className="text-sm text-subtle">Loading…</p>
            ) : (
              <ProductPicker products={products} selected={selected} onChange={setSelected} />
            )}
          </fieldset>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-app-form" loading={create.isPending}>
            Submit for approval
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EditAppDialog({ app, onClose, onSaved }: { app: ParticipantApp; onClose: () => void; onSaved: (app: ParticipantApp) => void }) {
  const { notify } = useToast();
  const [form, setForm] = React.useState({
    name: app.name,
    description: app.description ?? "",
    callback_url: app.callback_url ?? "",
    allowed_ips: app.allowed_ips.join("\n"),
  });
  const save = useMutation({
    mutationFn: () =>
      appsApi.update(app.app_id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        callback_url: form.callback_url.trim() || null,
        allowed_ips: parseIpList(form.allowed_ips),
      }),
    onSuccess: (next) => {
      notify("App updated.", "success");
      onSaved(next);
    },
    onError: (error: Error) => notify(error.message, "error"),
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit app</DialogTitle>
          <DialogDescription>Keys and API products stay as they are. A new IP whitelist applies at once.</DialogDescription>
        </DialogHeader>
        <form
          id="edit-app-form"
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-app-name" required>
              App name
            </Label>
            <Input id="edit-app-name" required minLength={2} maxLength={100} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-app-callback">Callback URL</Label>
            <Input id="edit-app-callback" type="url" maxLength={1000} value={form.callback_url} onChange={(event) => setForm({ ...form, callback_url: event.target.value })} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="edit-app-description">Description</Label>
            <Textarea id="edit-app-description" rows={3} maxLength={1000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </div>
          <IpWhitelistField
            id="edit-app-ips"
            value={form.allowed_ips}
            onChange={(allowed_ips) => setForm({ ...form, allowed_ips })}
          />
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="edit-app-form" loading={save.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RequestProductsDialog({
  app,
  products,
  onClose,
  onSaved,
}: {
  app: ParticipantApp;
  products: AvailableApiProduct[];
  onClose: () => void;
  onSaved: (app: ParticipantApp) => void;
}) {
  const { notify } = useToast();
  const [selected, setSelected] = React.useState<number[]>([]);
  const request = useMutation({
    mutationFn: () => appsApi.requestProducts(app.app_id, selected),
    onSuccess: (next) => {
      notify("Requested. Instant-access products work now; the others wait for approval.", "success");
      onSaved(next);
    },
    onError: (error: Error) => notify(error.message, "error"),
  });
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Request API products</DialogTitle>
          <DialogDescription>For app &quot;{app.name}&quot;. Its existing keys get the new access.</DialogDescription>
        </DialogHeader>
        <ProductPicker products={products} selected={selected} onChange={setSelected} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => request.mutate()} loading={request.isPending} disabled={selected.length === 0}>
            Request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

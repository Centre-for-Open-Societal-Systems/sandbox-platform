"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";

import { limitText } from "@/components/apps/app-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { MethodBadge, PublishedBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { adminAppsApi } from "@/lib/services/apps";
import { formatDateTime } from "@/lib/utils";
import type { ApiProduct, ApiProductPayload, ApprovalType } from "@/types/api";

const EMPTY_FORM: ApiProductPayload = {
  name: "",
  display_name: "",
  description: null,
  approval_type: "MANUAL",
  is_published: false,
  sort_order: 0,
  endpoint_ids: [],
  rate_limit_per_minute: null,
  quota_per_day: null,
};

/** Empty input = no limit. */
function limitValue(text: string): number | null {
  const value = Math.floor(Number(text));
  return text.trim() && value > 0 ? value : null;
}

/** "Farmer Registry - Read" -> "farmer-registry-read". */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 100);
}

export default function ApiProductsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { confirm, dialog } = useConfirm();
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });
  const [editing, setEditing] = React.useState<ApiProduct | "new" | null>(null);

  const productsQuery = useQuery({
    queryKey: ["admin", "api-products", list.query],
    queryFn: () => adminAppsApi.listProducts(list.query),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "api-products"] });

  const publish = useMutation({
    mutationFn: ({ id, value }: { id: number; value: boolean }) => adminAppsApi.publishProduct(id, value),
    onSuccess: (product) => {
      notify(product.is_published ? "API product published." : "API product unpublished.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => adminAppsApi.deleteProduct(id),
    onSuccess: () => {
      notify("API product deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<ApiProduct>[] = [
    {
      key: "display_name",
      header: "API Product",
      sortable: true,
      render: (row) => (
        <div>
          <p className="font-medium">{row.display_name}</p>
          <p className="font-mono text-xs text-subtle">{row.name}</p>
        </div>
      ),
    },
    {
      key: "approval_type",
      header: "Approval",
      render: (row) => (
        <Badge variant={row.approval_type === "AUTO" ? "info" : "warning"}>
          {row.approval_type === "AUTO" ? "Automatic" : "Admin approval"}
        </Badge>
      ),
    },
    { key: "endpoint_count", header: "Endpoints", render: (row) => row.endpoint_count },
    {
      key: "rate_limit_per_minute",
      header: "Rate limit",
      render: (row) => (
        <span className="whitespace-nowrap text-sm">{limitText(row.rate_limit_per_minute, row.quota_per_day)}</span>
      ),
    },
    { key: "app_count", header: "Apps with access", render: (row) => row.app_count },
    { key: "is_published", header: "Status", render: (row) => <PublishedBadge published={row.is_published} /> },
    {
      key: "modify_date",
      header: "Updated",
      sortable: true,
      render: (row) => <span className="whitespace-nowrap">{formatDateTime(row.modify_date)}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`API product ${row.display_name}`}
          onEdit={() => setEditing(row)}
          onDelete={async () => {
            const ok = await confirm({
              title: "Delete API product?",
              consequence: `"${row.display_name}" is removed. Apps keep no access through it.`,
              confirmLabel: "Delete",
            });
            if (ok) remove.mutate(row.api_product_id);
          }}
          canDelete={row.app_count === 0}
          deleteBlockedReason="Apps still have access - revoke it first"
          status={{
            checked: row.is_published,
            onChange: (value) => publish.mutate({ id: row.api_product_id, value }),
            disabled: publish.isPending,
          }}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="API Products"
        description="Bundles of catalogue endpoints that participant apps can be granted. An app's API key works at the gateway only for the endpoints of its approved API products."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Catalogue" }, { label: "API Products" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "Name or description" }}
        actions={
          <Button onClick={() => setEditing("new")}>
            <Plus className="h-4 w-4" aria-hidden />
            New API product
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="Status" htmlFor="api-product-published">
          <Select
            id="api-product-published"
            value={list.filters.is_published === undefined ? "" : String(list.filters.is_published)}
            onChange={(event) =>
              list.setFilter("is_published", event.target.value === "" ? undefined : event.target.value === "true")
            }
          >
            <option value="">All</option>
            <option value="true">Published</option>
            <option value="false">Draft</option>
          </Select>
        </FilterField>
        <Button variant="ghost" onClick={list.resetFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={productsQuery.data?.api_products ?? []}
        rowKey={(row) => row.api_product_id}
        pagination={productsQuery.data?.pagination}
        loading={productsQuery.isLoading}
        noun="API products"
        emptyMessage="No API products yet. Create one and pick the endpoints it grants."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {editing !== null ? (
        <ApiProductDialog
          productId={editing === "new" ? null : editing.api_product_id}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            invalidate();
          }}
        />
      ) : null}
      {dialog}
    </>
  );
}

function ApiProductDialog({
  productId,
  onClose,
  onSaved,
}: {
  productId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { notify } = useToast();
  const [form, setForm] = React.useState<ApiProductPayload>(EMPTY_FORM);
  const [nameTouched, setNameTouched] = React.useState(false);
  const [filter, setFilter] = React.useState("");
  const [selectedOnly, setSelectedOnly] = React.useState(false);
  const [expanded, setExpanded] = React.useState<Set<number>>(new Set());
  const [loaded, setLoaded] = React.useState(productId === null);

  const detailQuery = useQuery({
    queryKey: ["admin", "api-products", "detail", productId],
    queryFn: () => adminAppsApi.getProduct(productId!),
    enabled: productId !== null,
  });
  const optionsQuery = useQuery({
    queryKey: ["admin", "api-products", "endpoint-options"],
    queryFn: () => adminAppsApi.endpointOptions(),
  });

  if (!loaded && detailQuery.data) {
    const detail = detailQuery.data;
    setLoaded(true);
    setNameTouched(true);
    setForm({
      name: detail.name,
      display_name: detail.display_name,
      description: detail.description,
      approval_type: detail.approval_type,
      is_published: detail.is_published,
      sort_order: detail.sort_order,
      endpoint_ids: detail.endpoints.map((e) => e.endpoint_id),
      rate_limit_per_minute: detail.rate_limit_per_minute,
      quota_per_day: detail.quota_per_day,
    });
  }

  const save = useMutation({
    mutationFn: () =>
      productId === null ? adminAppsApi.createProduct(form) : adminAppsApi.updateProduct(productId, form),
    onSuccess: () => {
      notify(productId === null ? "API product created." : "API product saved. Apps with access were re-synced.", "success");
      onSaved();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const selected = new Set(form.endpoint_ids);
  const term = filter.trim().toLowerCase();
  // Searching or "selected only" shows every match, so all groups open.
  const forceOpen = Boolean(term) || selectedOnly;
  const groups = (optionsQuery.data ?? [])
    .map((group) => ({
      ...group,
      endpoints: group.endpoints.filter(
        (e) =>
          (!selectedOnly || selected.has(e.endpoint_id)) &&
          (!term ||
            `${group.product_name} ${e.display_name ?? ""} ${e.endpoint_url ?? ""} ${e.method ?? ""}`
              .toLowerCase()
              .includes(term)),
      ),
    }))
    .filter((group) => group.endpoints.length > 0);

  function toggleExpanded(id: number) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setExpanded(next);
  }

  function toggle(ids: number[], on: boolean) {
    const next = new Set(form.endpoint_ids);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    setForm({ ...form, endpoint_ids: [...next] });
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>{productId === null ? "New API Product" : "Edit API Product"}</DialogTitle>
          <DialogDescription>
            Pick the endpoints this product grants. The same endpoint can be in several products (e.g. a read-only and a
            full-access product).
          </DialogDescription>
        </DialogHeader>
        {!loaded ? (
          <p className="py-8 text-center text-sm text-subtle">Loading…</p>
        ) : (
          <form
            id="api-product-form"
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              save.mutate();
            }}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-display" required>
                  Display name
                </Label>
                <Input
                  id="ap-display"
                  value={form.display_name}
                  maxLength={250}
                  required
                  placeholder="Farmer Registry - Read"
                  onChange={(event) =>
                    setForm({
                      ...form,
                      display_name: event.target.value,
                      name: nameTouched ? form.name : slugify(event.target.value),
                    })
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-name" required>
                  Name (id)
                </Label>
                <Input
                  id="ap-name"
                  value={form.name}
                  maxLength={100}
                  required
                  pattern="[a-z0-9][a-z0-9-]{1,98}[a-z0-9]"
                  title="Lower-case letters, digits and hyphens"
                  className="font-mono"
                  onChange={(event) => {
                    setNameTouched(true);
                    setForm({ ...form, name: event.target.value.toLowerCase() });
                  }}
                />
              </div>
              <div className="flex flex-col gap-2 sm:col-span-2">
                <Label htmlFor="ap-description">Description</Label>
                <Textarea
                  id="ap-description"
                  rows={2}
                  maxLength={4000}
                  value={form.description ?? ""}
                  onChange={(event) => setForm({ ...form, description: event.target.value || null })}
                  placeholder="What an app can do with this product. Shown to participants."
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-approval">Approval</Label>
                <Select
                  id="ap-approval"
                  value={form.approval_type}
                  onChange={(event) => setForm({ ...form, approval_type: event.target.value as ApprovalType })}
                >
                  <option value="MANUAL">Admin approves each request</option>
                  <option value="AUTO">Granted automatically</option>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-rate-minute">Calls per minute, per app</Label>
                <Input
                  id="ap-rate-minute"
                  type="number"
                  min={1}
                  inputMode="numeric"
                  placeholder="No limit"
                  value={form.rate_limit_per_minute ?? ""}
                  onChange={(event) => setForm({ ...form, rate_limit_per_minute: limitValue(event.target.value) })}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-quota-day">Calls per day, per app</Label>
                <Input
                  id="ap-quota-day"
                  type="number"
                  min={1}
                  inputMode="numeric"
                  placeholder="No limit"
                  value={form.quota_per_day ?? ""}
                  onChange={(event) => setForm({ ...form, quota_per_day: limitValue(event.target.value) })}
                />
              </div>
              <p className="-mt-2 text-xs text-subtle sm:col-span-2">
                Enforced by the gateway (answer 429) when rate limits are switched on. An app with several products
                gets the highest of their limits; an empty field means no limit.
              </p>
              <div className="flex flex-col gap-2">
                <Label htmlFor="ap-order">Sort order</Label>
                <Input
                  id="ap-order"
                  type="number"
                  value={form.sort_order}
                  onChange={(event) => setForm({ ...form, sort_order: Number(event.target.value) || 0 })}
                />
              </div>
              <label className="flex items-start gap-2 text-sm sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.is_published}
                  onChange={(event) => setForm({ ...form, is_published: event.target.checked })}
                  className="mt-0.5 h-4 w-4 accent-brand-600"
                />
                <span>
                  Published
                  <span className="block text-xs text-subtle">Participants can request it for their apps.</span>
                </span>
              </label>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="ap-filter">
                  Endpoints <span className="text-subtle">({form.endpoint_ids.length} selected)</span>
                </Label>
                <Input
                  id="ap-filter"
                  className="max-w-xs"
                  placeholder="Filter endpoints"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedOnly}
                    onChange={(event) => setSelectedOnly(event.target.checked)}
                    className="h-4 w-4 accent-brand-600"
                  />
                  Selected only
                </label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    className="text-brand-600 hover:underline disabled:opacity-50"
                    disabled={forceOpen}
                    onClick={() => setExpanded(new Set(groups.map((g) => g.product_id)))}
                  >
                    Expand all
                  </button>
                  <button
                    type="button"
                    className="text-brand-600 hover:underline disabled:opacity-50"
                    disabled={forceOpen}
                    onClick={() => setExpanded(new Set())}
                  >
                    Collapse all
                  </button>
                </div>
              </div>
              {/* relative: contains the sr-only (absolute) legends so they don't stretch the dialog's scroll area */}
              <div className="relative max-h-96 overflow-auto rounded-lg border border-hairline">
                {optionsQuery.isLoading ? (
                  <p className="p-4 text-sm text-subtle">Loading endpoints…</p>
                ) : groups.length === 0 ? (
                  <p className="p-4 text-sm text-subtle">
                    {selectedOnly && !term ? "No endpoints selected yet." : "No endpoints match."}
                  </p>
                ) : (
                  groups.map((group) => {
                    const ids = group.endpoints.map((e) => e.endpoint_id);
                    const count = ids.filter((id) => selected.has(id)).length;
                    const open = forceOpen || expanded.has(group.product_id);
                    const panelId = `ap-group-${group.product_id}`;
                    return (
                      <fieldset key={group.product_id} className="border-b border-hairline last:border-b-0">
                        <legend className="sr-only">{group.product_name}</legend>
                        <div className="sticky top-0 z-10 flex items-center gap-2 bg-surface-soft px-3 py-2 text-sm">
                          <input
                            type="checkbox"
                            aria-label={`Select all endpoints of ${group.product_name}`}
                            checked={count > 0 && count === ids.length}
                            ref={(el) => {
                              if (el) el.indeterminate = count > 0 && count < ids.length;
                            }}
                            onChange={(event) => toggle(ids, event.target.checked)}
                            className="h-4 w-4 shrink-0 accent-brand-600"
                          />
                          <button
                            type="button"
                            aria-expanded={open}
                            aria-controls={panelId}
                            disabled={forceOpen}
                            onClick={() => toggleExpanded(group.product_id)}
                            className="flex min-w-0 flex-1 items-center gap-2 text-left font-semibold"
                          >
                            <ChevronRight
                              className={`h-4 w-4 shrink-0 text-subtle transition-transform ${open ? "rotate-90" : ""}`}
                              aria-hidden
                            />
                            <span className="truncate">{group.product_name}</span>
                            <span className="ml-auto shrink-0 text-xs font-normal text-subtle">
                              {count} / {ids.length} selected
                            </span>
                          </button>
                          {!group.is_gateway_published ? (
                            <Badge variant="warning" className="shrink-0">
                              Not on gateway
                            </Badge>
                          ) : null}
                        </div>
                        {open ? (
                          <ul id={panelId}>
                            {group.endpoints.map((endpoint) => (
                              <li key={endpoint.endpoint_id}>
                                <label className="flex items-center gap-3 px-3 py-1.5 pl-9 text-sm hover:bg-surface-soft">
                                  <input
                                    type="checkbox"
                                    checked={selected.has(endpoint.endpoint_id)}
                                    onChange={(event) => toggle([endpoint.endpoint_id], event.target.checked)}
                                    className="h-4 w-4 shrink-0 accent-brand-600"
                                  />
                                  <MethodBadge method={endpoint.method} />
                                  <span className="flex min-w-0 flex-1 flex-col">
                                    {endpoint.display_name ? (
                                      <span className="truncate text-sm">{endpoint.display_name}</span>
                                    ) : null}
                                    <code
                                      className="truncate font-mono text-xs text-subtle"
                                      title={endpoint.endpoint_url ?? ""}
                                    >
                                      {endpoint.endpoint_url}
                                    </code>
                                  </span>
                                  {!endpoint.is_published ? <Badge variant="neutral">Draft</Badge> : null}
                                </label>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </fieldset>
                    );
                  })
                )}
              </div>
            </div>
          </form>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="api-product-form" loading={save.isPending} disabled={!loaded}>
            {productId === null ? "Create" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

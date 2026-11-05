"use client";

import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CloudDownload, FileUp, Network, Plus } from "lucide-react";

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
import { Input, Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { MethodBadge, PublishedBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { catalogApi } from "@/lib/services/catalog";
import { formatDate } from "@/lib/utils";
import type { GatewaySyncReport, GatewaySyncRow, Product } from "@/types/api";

const GATEWAY_NAMES = { apisix: "APISIX", kong: "Kong" } as const;

interface ProductForm {
  product_id?: number;
  product_name: string;
  display_name: string;
  description: string;
  category_id: string;
  is_gateway_published: boolean;
}

const EMPTY_PRODUCT: ProductForm = {
  product_name: "",
  display_name: "",
  description: "",
  category_id: "",
  is_gateway_published: false,
};

export default function ProductsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });

  const [form, setForm] = React.useState<ProductForm | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [importTarget, setImportTarget] = React.useState<Product | null>(null);
  const [specText, setSpecText] = React.useState("");
  const [replaceExisting, setReplaceExisting] = React.useState(false);
  const [syncReport, setSyncReport] = React.useState<GatewaySyncReport | null>(null);

  // GATEWAY_SYNC_ENABLED on the API decides whether "Pull from gateway" is offered.
  const gatewayQuery = useQuery({
    queryKey: ["admin", "gateway-status"],
    queryFn: () => catalogApi.gatewayStatus(),
    staleTime: CATALOG_STALE_MS,
  });
  const gatewayStatus = gatewayQuery.data;
  const gatewayName = gatewayStatus ? GATEWAY_NAMES[gatewayStatus.gateway_type] : "gateway";

  const productsQuery = useQuery({
    queryKey: ["admin", "products", list.query],
    queryFn: () => catalogApi.listProducts(list.query),
  });

  const categoriesQuery = useQuery({
    queryKey: ["admin", "product-categories"],
    queryFn: () => catalogApi.listProductCategories(),
    staleTime: CATALOG_STALE_MS,
    enabled: form !== null,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
  }

  const save = useMutation({
    mutationFn: (values: ProductForm) => {
      const payload = {
        product_name: values.product_name,
        display_name: values.display_name || null,
        description: values.description || null,
        category_id: values.category_id ? Number(values.category_id) : null,
        is_gateway_published: values.is_gateway_published,
      };
      return values.product_id
        ? catalogApi.updateProduct({ ...payload, product_id: values.product_id })
        : catalogApi.createProduct(payload);
    },
    onSuccess: (_data, values) => {
      notify(values.product_id ? "Product updated." : "Product created.", "success");
      setForm(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const publish = useMutation({
    mutationFn: (product: Product) =>
      catalogApi.publishProduct(product.product_id, !product.is_published),
    onSuccess: () => {
      notify("Publication status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (product: Product) => catalogApi.deleteProduct(product.product_id),
    onSuccess: () => {
      notify("Product deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const importSpec = useMutation({
    mutationFn: (product: Product) =>
      catalogApi.importSpec(product.product_id, specText, replaceExisting),
    onSuccess: (result) => {
      notify(
        `Imported ${result.total} operations — ${result.created} created, ${result.updated} updated.`,
        "success",
      );
      setImportTarget(null);
      setSpecText("");
      setReplaceExisting(false);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  // Preview first (dry run), then apply from the dialog.
  const gatewaySync = useMutation({
    mutationFn: (dryRun: boolean) => catalogApi.gatewaySync(dryRun),
    onSuccess: (report) => {
      setSyncReport(report);
      if (!report.dry_run) {
        notify(
          `Pulled from ${GATEWAY_NAMES[report.gateway_type]}: ${report.created_count} created, ${report.updated_count} updated.`,
          "success",
        );
        invalidate();
      }
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<Product>[] = [
    {
      key: "product_name",
      header: "Product",
      sortable: true,
      render: (row) => (
        <div className="max-w-md">
          <Link href={`/admin/products/${row.product_id}`} className="font-medium hover:text-brand-bright">
            {row.display_name ?? row.product_name}
          </Link>
          <p className="line-clamp-1 text-xs text-subtle">{row.description ?? "—"}</p>
          {row.is_gateway_published ? (
            <Badge variant="info" className="mt-1 gap-1" title="Called through the API gateway">
              <Network className="h-3 w-3" aria-hidden />
              Via API gateway
            </Badge>
          ) : null}
        </div>
      ),
    },
    { key: "category_name", header: "Category", render: (row) => row.category_name ?? "—" },
    { key: "endpoint_count", header: "End-Points", render: (row) => row.endpoint_count },
    {
      key: "api_doc_version",
      header: "Version",
      render: (row) => (row.api_doc_version ? `v${row.api_doc_version}` : "—"),
    },
    {
      key: "is_published",
      header: "Status",
      render: (row) => <PublishedBadge published={row.is_published} />,
    },
    {
      key: "modify_date",
      header: "Updated Date",
      sortable: true,
      render: (row) => formatDate(row.modify_date),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => {
        const name = row.display_name ?? row.product_name;
        return (
          <RowActions
            recordLabel={`product ${name}`}
            viewHref={`/admin/products/${row.product_id}`}
            onEdit={() =>
              setForm({
                product_id: row.product_id,
                product_name: row.product_name,
                display_name: row.display_name ?? "",
                description: row.description ?? "",
                category_id: row.category_id ? String(row.category_id) : "",
                is_gateway_published: row.is_gateway_published,
              })
            }
            extra={[{ icon: FileUp, label: `Import OpenAPI spec into ${name}`, onClick: () => setImportTarget(row) }]}
            onDelete={async () => {
              const ok = await confirm({
                title: "Delete Product?",
                consequence: `${name} and its end-points will be removed from the catalogue.`,
                confirmLabel: "Delete",
              });
              if (ok) {
                remove.mutate(row);
              }
            }}
            canDelete={!row.is_published}
            deleteBlockedReason="Unpublish the product before deleting it"
            status={{
              checked: row.is_published,
              onChange: async (next) => {
                if (!next) {
                  const ok = await confirm({
                    title: "Unpublish Product?",
                    consequence: `${name} will disappear from the public catalogue and the participant portal.`,
                    confirmLabel: "Unpublish",
                    tone: "warning",
                  });
                  if (!ok) {
                    return;
                  }
                }
                publish.mutate(row);
              },
            }}
          />
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        title="API Catalogue"
        description="Products bundle related end-points. Import an OpenAPI document to create end-points and their samples in one step. The switch publishes a product."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "API Catalogue" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "Search products" }}
        actions={
          <Button onClick={() => setForm({ ...EMPTY_PRODUCT })}>
            <Plus className="h-4 w-4" aria-hidden />
            Add Product
          </Button>
        }
      />

      {gatewayStatus?.enabled ? (
        <div className="mb-6 flex flex-col gap-4 rounded-xl border border-hairline bg-surface-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white text-brand-bright ring-1 ring-hairline">
              <Network className="h-4.5 w-4.5" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">
                API gateway: {gatewayName}
                {gatewayStatus.admin_url_configured ? null : (
                  <Badge variant="warning" className="ml-2 align-middle">
                    Not connected
                  </Badge>
                )}
              </p>
              <p className="mt-0.5 text-sm text-subtle">
                {gatewayStatus.admin_url_configured
                  ? "Add new routes and update changed ones from the gateway. You see a preview before anything is saved."
                  : "Set GATEWAY_ADMIN_URL (and GATEWAY_ADMIN_TOKEN) on the API to pull routes from the gateway."}
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            className="shrink-0"
            loading={gatewaySync.isPending && syncReport === null}
            disabled={!gatewayStatus.admin_url_configured}
            onClick={() => gatewaySync.mutate(true)}
          >
            <CloudDownload className="h-4 w-4" aria-hidden />
            Pull from {gatewayName}
          </Button>
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={productsQuery.data?.products ?? []}
        rowKey={(row) => row.product_id}
        pagination={productsQuery.data?.pagination}
        loading={productsQuery.isLoading}
        noun="products"
        emptyMessage="No products have been created yet."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {confirmDialog}

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{form?.product_id ? "Edit product" : "Add product"}</DialogTitle>
            <DialogDescription>
              A product groups the endpoints of one service, such as the farmer registry.
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="product_name" required>
                  Product name
                </Label>
                <Input
                  id="product_name"
                  value={form.product_name}
                  onChange={(event) => setForm({ ...form, product_name: event.target.value })}
                  required
                  minLength={2}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="display_name">Display name</Label>
                <Input
                  id="display_name"
                  value={form.display_name}
                  onChange={(event) => setForm({ ...form, display_name: event.target.value })}
                  placeholder="Shown in the catalogue if set"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="category_id">Category</Label>
                <Select
                  id="category_id"
                  value={form.category_id}
                  onChange={(event) => setForm({ ...form, category_id: event.target.value })}
                >
                  <option value="">No category</option>
                  {(categoriesQuery.data ?? []).map((category) => (
                    <option key={category.category_id} value={category.category_id}>
                      {category.category_name}
                    </option>
                  ))}
                </Select>
              </div>

              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.is_gateway_published}
                  onChange={(event) => setForm({ ...form, is_gateway_published: event.target.checked })}
                  className="mt-0.5 h-4 w-4 accent-brand-600"
                />
                <span>
                  Served through the API gateway
                  <span className="block text-xs text-subtle">
                    Try-it calls go to the gateway URL configured for each environment, unless an
                    end-point has its own upstream URL.
                  </span>
                </span>
              </label>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  {form.product_id ? "Save changes" : "Create product"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={importTarget !== null} onOpenChange={(open) => !open && setImportTarget(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Import OpenAPI specification</DialogTitle>
            <DialogDescription>
              Paste a JSON or YAML document. Endpoints are matched on method and path, so
              re-importing updates rather than duplicates them.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="spec">Specification</Label>
              <Textarea
                id="spec"
                className="min-h-64 font-mono text-xs"
                value={specText}
                onChange={(event) => setSpecText(event.target.value)}
                placeholder="openapi: 3.0.3"
              />
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={replaceExisting}
                onChange={(event) => setReplaceExisting(event.target.checked)}
                className="h-4 w-4 accent-brand-600"
              />
              Remove endpoints that are not in this specification
            </label>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportTarget(null)}>
              Cancel
            </Button>
            <Button
              loading={importSpec.isPending}
              disabled={specText.trim().length === 0}
              onClick={() => importTarget && importSpec.mutate(importTarget)}
            >
              <FileUp className="h-4 w-4" aria-hidden />
              Import
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={syncReport !== null} onOpenChange={(open) => !open && setSyncReport(null)}>
        <DialogContent className="max-w-3xl">
          {syncReport ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  {syncReport.dry_run
                    ? `Pull from ${GATEWAY_NAMES[syncReport.gateway_type]}: preview`
                    : `Pulled from ${GATEWAY_NAMES[syncReport.gateway_type]}`}
                </DialogTitle>
                <DialogDescription>
                  {syncReport.routes} routes in {syncReport.services} services, {syncReport.operations} operations.
                  New end-points are added unpublished, next to their service&apos;s existing end-points (or in a
                  new product for the service). Existing ones keep their imported details; only what they lack
                  is filled in. Nothing is deleted.
                </DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SyncCount label="New" value={syncReport.created_count} tone="text-[#2E7D32]" />
                <SyncCount label="Updated" value={syncReport.updated_count} tone="text-[#1A5FA8]" />
                <SyncCount label="Unchanged" value={syncReport.unchanged} />
                <SyncCount label="Not on gateway" value={syncReport.missing_count} tone="text-[#B26A00]" />
              </div>

              <div className="mt-2 max-h-[50vh] space-y-5 overflow-y-auto pr-1">
                {syncReport.dry_run && pendingChanges(syncReport) === 0 ? (
                  <p className="flex items-center gap-2 rounded-xl border border-hairline bg-surface-soft px-4 py-3 text-sm text-ink">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-[#2E7D32]" aria-hidden />
                    The catalogue is up to date with {GATEWAY_NAMES[syncReport.gateway_type]}. Nothing to pull.
                  </p>
                ) : null}
                {syncReport.products_created.length ? (
                  <SyncSection title="New products">
                    {syncReport.products_created.map((product) => (
                      <li key={product.product_name} className="text-sm">
                        {product.product_name}
                      </li>
                    ))}
                  </SyncSection>
                ) : null}
                <SyncRows title="New end-points" rows={syncReport.created} total={syncReport.created_count} />
                <SyncRows title="Updated end-points" rows={syncReport.updated} total={syncReport.updated_count} />
                <SyncRows
                  title="In the catalogue, not on the gateway (kept)"
                  rows={syncReport.missing}
                  total={syncReport.missing_count}
                />
                {syncReport.skipped.length ? (
                  <details className="group rounded-xl border border-hairline px-4 py-3">
                    <summary className="cursor-pointer text-sm font-semibold text-ink marker:text-subtle">
                      Skipped routes ({syncReport.skipped_count})
                      <span className="ml-2 font-normal text-subtle">wildcards and CORS / realtime routes</span>
                    </summary>
                    <ul className="mt-3 space-y-2">
                      {syncReport.skipped.map((row) => (
                        <li key={`${row.route}-${row.path}`} className="text-sm">
                          <code className="font-mono text-xs break-all">{row.path}</code>
                          <span className="block text-xs text-subtle">
                            {row.route} · {row.reason}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setSyncReport(null)}>
                  {syncReport.dry_run && pendingChanges(syncReport) > 0 ? "Cancel" : "Close"}
                </Button>
                {syncReport.dry_run && pendingChanges(syncReport) > 0 ? (
                  <Button
                    loading={gatewaySync.isPending}
                    onClick={() => gatewaySync.mutate(false)}
                  >
                    <CloudDownload className="h-4 w-4" aria-hidden />
                    Apply pull
                  </Button>
                ) : null}
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function pendingChanges(report: GatewaySyncReport): number {
  return report.created_count + report.updated_count;
}

/** One count tile; ``tone`` colours a non-zero value. */
function SyncCount({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-xl bg-surface-soft px-3 py-2.5">
      <p className="text-xs text-subtle">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${value > 0 && tone ? tone : "text-ink"}`}>{value}</p>
    </div>
  );
}

function SyncSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold text-ink">{title}</h3>
      <ul className="space-y-1.5">{children}</ul>
    </section>
  );
}

function SyncRows({ title, rows, total }: { title: string; rows: GatewaySyncRow[]; total: number }) {
  if (!total) return null;
  return (
    <SyncSection title={`${title} (${total})`}>
      {rows.map((row) => (
        <li key={`${row.method}-${row.path}`} className="flex flex-wrap items-center gap-2 text-sm">
          <MethodBadge method={row.method} />
          <code className="font-mono text-xs">{row.path}</code>
          <span className="text-xs text-subtle">
            {row.product_name}
            {row.changes?.length ? ` · adds ${row.changes.join(", ")}` : null}
          </span>
        </li>
      ))}
      {total > rows.length ? (
        <li className="text-xs text-subtle">…and {total - rows.length} more</li>
      ) : null}
    </SyncSection>
  );
}

"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileJson, Plus } from "lucide-react";

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
import { catalogApi } from "@/lib/services/catalog";
import { formatDate } from "@/lib/utils";
import type { Endpoint, EndpointDetail } from "@/types/api";

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;
const API_TYPES = ["NATIONAL", "REGIONAL", "IAM", "PARTNER"] as const;

interface EndpointForm {
  endpoint_id?: number;
  display_name: string;
  endpoint_url: string;
  method: string;
  api_type: string;
  description: string;
  sandbox_api_url: string;
  uat_api_url: string;
  prod_api_url: string;
  sort_order: string;
  api_keywords: string;
  area_scoped: boolean;
  is_gateway_published: boolean;
}

const EMPTY_ENDPOINT: EndpointForm = {
  display_name: "",
  endpoint_url: "",
  method: "POST",
  api_type: "NATIONAL",
  description: "",
  sandbox_api_url: "",
  uat_api_url: "",
  prod_api_url: "",
  sort_order: "0",
  api_keywords: "",
  area_scoped: false,
  is_gateway_published: false,
};

function toForm(endpoint: EndpointDetail): EndpointForm {
  return {
    endpoint_id: endpoint.endpoint_id,
    display_name: endpoint.display_name ?? "",
    endpoint_url: endpoint.endpoint_url ?? "",
    method: endpoint.method ?? "POST",
    api_type: endpoint.api_type ?? "NATIONAL",
    description: endpoint.description ?? "",
    sandbox_api_url: endpoint.sandbox_api_url ?? "",
    uat_api_url: endpoint.uat_api_url ?? "",
    prod_api_url: endpoint.prod_api_url ?? "",
    sort_order: String(endpoint.sort_order ?? 0),
    api_keywords: (endpoint.api_keywords ?? []).join(", "),
    area_scoped: endpoint.area_scoped,
    is_gateway_published: endpoint.is_gateway_published,
  };
}

export default function ProductDetailsPage() {
  const params = useParams<{ productId: string }>();
  const productId = Number(params.productId);
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [form, setForm] = React.useState<EndpointForm | null>(null);
  const [search, setSearch] = React.useState("");
  const { confirm, dialog: confirmDialog } = useConfirm();

  const productQuery = useQuery({
    queryKey: ["admin", "product", productId],
    queryFn: () => catalogApi.getProduct(productId),
    enabled: Number.isFinite(productId),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "product", productId] });
    queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
  }

  const save = useMutation({
    mutationFn: (values: EndpointForm) => {
      const payload = {
        display_name: values.display_name,
        endpoint_url: values.endpoint_url,
        method: values.method,
        api_type: values.api_type,
        description: values.description || null,
        sandbox_api_url: values.sandbox_api_url || null,
        uat_api_url: values.uat_api_url || null,
        prod_api_url: values.prod_api_url || null,
        sort_order: Number(values.sort_order) || 0,
        api_keywords: values.api_keywords
          .split(",")
          .map((keyword) => keyword.trim())
          .filter(Boolean),
        area_scoped: values.area_scoped,
        is_gateway_published: values.is_gateway_published,
      };
      return values.endpoint_id
        ? catalogApi.updateEndpoint({ ...payload, endpoint_id: values.endpoint_id })
        : catalogApi.createEndpoint({ ...payload, product_id: productId });
    },
    onSuccess: (_data, values) => {
      notify(values.endpoint_id ? "Endpoint updated." : "Endpoint added.", "success");
      setForm(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const edit = useMutation({
    mutationFn: (endpoint: Endpoint) => catalogApi.getEndpoint(endpoint.endpoint_id),
    onSuccess: (detail) => setForm(toForm(detail)),
    onError: (error: Error) => notify(error.message, "error"),
  });

  const publish = useMutation({
    mutationFn: (endpoint: Endpoint) =>
      catalogApi.publishEndpoint(endpoint.endpoint_id, !endpoint.is_published),
    onSuccess: () => {
      notify("Publication status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (endpoint: Endpoint) => catalogApi.deleteEndpoint(endpoint.endpoint_id),
    onSuccess: () => {
      notify("Endpoint deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const product = productQuery.data;
  const term = search.trim().toLowerCase();
  const endpoints = (product?.endpoints ?? []).filter(
    (endpoint) =>
      !term ||
      (endpoint.endpoint_url ?? "").toLowerCase().includes(term) ||
      (endpoint.display_name ?? "").toLowerCase().includes(term),
  );

  const columns: Column<Endpoint>[] = [
    {
      key: "endpoint_url",
      header: "End-Point",
      render: (row) => (
        <div className="flex items-center gap-2">
          <MethodBadge method={row.method} />
          <span className="font-mono text-xs">{row.endpoint_url}</span>
        </div>
      ),
    },
    { key: "display_name", header: "Display Name", render: (row) => row.display_name ?? "—" },
    { key: "api_type", header: "API Type", render: (row) => row.api_type ?? "—" },
    {
      key: "routing",
      header: "Upstream",
      render: (row) =>
        row.is_gateway_published || product?.is_gateway_published ? (
          <Badge variant="info" title="Called through the API gateway unless the end-point has its own URL">
            API gateway
          </Badge>
        ) : (
          <Badge title="Own upstream URL, or answered from samples in the sandbox">Direct / mock</Badge>
        ),
    },
    { key: "sort_order", header: "Order By", render: (row) => row.sort_order },
    {
      key: "is_published",
      header: "Status",
      render: (row) => <PublishedBadge published={row.is_published} />,
    },
    { key: "added_date", header: "Added Date", render: (row) => formatDate(row.added_date) },
    {
      key: "actions",
      header: "Actions",
      render: (row) => {
        const name = row.display_name ?? row.endpoint_url ?? "end-point";
        return (
          <RowActions
            recordLabel={`end-point ${name}`}
            onEdit={() => edit.mutate(row)}
            extra={[
              {
                icon: FileJson,
                label: `Proxy info and samples for ${name}`,
                href: `/admin/products/${productId}/endpoints/${row.endpoint_id}`,
              },
            ]}
            onDelete={async () => {
              const ok = await confirm({
                title: "Delete End-Point?",
                consequence: `${row.method} ${row.endpoint_url} and its samples will be removed.`,
                confirmLabel: "Delete",
              });
              if (ok) {
                remove.mutate(row);
              }
            }}
            canDelete={!row.is_published}
            deleteBlockedReason="Unpublish the end-point before deleting it"
            status={{
              checked: row.is_published,
              onChange: async (next) => {
                if (!next) {
                  const ok = await confirm({
                    title: "Unpublish End-Point?",
                    consequence: "Participants will no longer see or call this end-point.",
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
        title={product ? (product.display_name ?? product.product_name) : "Product Details"}
        description={product?.description ?? undefined}
        breadcrumbs={[
          { label: "Home", href: "/admin/dashboard" },
          { label: "API Catalogue", href: "/admin/products" },
          { label: "Product Details" },
        ]}
        search={{ value: search, onChange: setSearch, placeholder: "Search end-points" }}
        actions={
          <Button
            onClick={() =>
              setForm({ ...EMPTY_ENDPOINT, is_gateway_published: product?.is_gateway_published ?? false })
            }
            disabled={!product}
          >
            <Plus className="h-4 w-4" aria-hidden />
            Add End-Point
          </Button>
        }
      />

      <DataTable
        columns={columns}
        rows={endpoints}
        rowKey={(row) => row.endpoint_id}
        loading={productQuery.isLoading}
        noun="end-points"
        emptyMessage="No end-points yet. Add one, or import an OpenAPI specification from the catalogue."
      />

      {confirmDialog}

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{form?.endpoint_id ? "Edit Endpoint" : "Add Endpoint"}</DialogTitle>
            <DialogDescription>
              The end-point path is appended to the upstream URL of the environment the
              participant calls. Request and response samples are managed under Proxy Info.
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="grid gap-4 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="display_name" required>
                  Display name
                </Label>
                <Input
                  id="display_name"
                  value={form.display_name}
                  onChange={(event) => setForm({ ...form, display_name: event.target.value })}
                  required
                  minLength={2}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="api_type">API type</Label>
                <Select
                  id="api_type"
                  value={form.api_type}
                  onChange={(event) => setForm({ ...form, api_type: event.target.value })}
                >
                  {API_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="method">Method</Label>
                <Select
                  id="method"
                  value={form.method}
                  onChange={(event) => setForm({ ...form, method: event.target.value })}
                >
                  {METHODS.map((method) => (
                    <option key={method} value={method}>
                      {method}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="endpoint_url" required>
                  End-point path
                </Label>
                <Input
                  id="endpoint_url"
                  className="font-mono text-xs"
                  value={form.endpoint_url}
                  onChange={(event) => setForm({ ...form, endpoint_url: event.target.value })}
                  placeholder="/beneficiary_portal/get_register"
                  required
                />
              </div>

              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="sandbox_api_url">Sandbox URL</Label>
                <Input
                  id="sandbox_api_url"
                  className="font-mono text-xs"
                  value={form.sandbox_api_url}
                  onChange={(event) => setForm({ ...form, sandbox_api_url: event.target.value })}
                  placeholder="Base URL, e.g. http://localhost:8000 (blank = API gateway or mock)"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="uat_api_url">UAT URL</Label>
                <Input
                  id="uat_api_url"
                  className="font-mono text-xs"
                  value={form.uat_api_url}
                  onChange={(event) => setForm({ ...form, uat_api_url: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="prod_api_url">Prod URL</Label>
                <Input
                  id="prod_api_url"
                  className="font-mono text-xs"
                  value={form.prod_api_url}
                  onChange={(event) => setForm({ ...form, prod_api_url: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="sort_order">Order by</Label>
                <Input
                  id="sort_order"
                  type="number"
                  min={0}
                  value={form.sort_order}
                  onChange={(event) => setForm({ ...form, sort_order: event.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="api_keywords">Keywords</Label>
                <Input
                  id="api_keywords"
                  value={form.api_keywords}
                  onChange={(event) => setForm({ ...form, api_keywords: event.target.value })}
                  placeholder="Comma separated"
                />
              </div>

              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="description">Note</Label>
                <Textarea
                  id="description"
                  value={form.description}
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </div>

              <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.area_scoped}
                  onChange={(event) => setForm({ ...form, area_scoped: event.target.checked })}
                  className="h-4 w-4 accent-brand-600"
                />
                Region required (the caller must pick a region)
              </label>

              <label className="flex items-start gap-2 text-sm sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.is_gateway_published || Boolean(product?.is_gateway_published)}
                  disabled={Boolean(product?.is_gateway_published)}
                  onChange={(event) => setForm({ ...form, is_gateway_published: event.target.checked })}
                  className="mt-0.5 h-4 w-4 accent-brand-600"
                />
                <span>
                  Call through the API gateway when no URL is set above
                  {product?.is_gateway_published ? (
                    <span className="block text-xs text-subtle">
                      Set for the whole product. Change it on the product.
                    </span>
                  ) : null}
                </span>
              </label>

              <DialogFooter className="sm:col-span-2">
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  {form.endpoint_id ? "Save changes" : "Add endpoint"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

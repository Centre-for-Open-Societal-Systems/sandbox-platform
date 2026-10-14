"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { MethodBadge, PublishedBadge, StatusCodeBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { catalogApi } from "@/lib/services/catalog";
import type { EndpointSchema } from "@/types/api";

const STATUS_CODES = ["200", "201", "204", "400", "401", "403", "404", "409", "422", "429", "500", "502", "503"];

type ParamKind = "path" | "header";

interface ParamRow {
  name: string;
  value: string;
  required: boolean;
}

interface SampleForm {
  schema_id?: number;
  status_code: string;
  req_schema: string;
  req_json: string;
  res_schema: string;
  res_json: string;
}

const EMPTY_SAMPLE: SampleForm = {
  status_code: "200",
  req_schema: "",
  req_json: "",
  res_schema: "",
  res_json: "",
};

function pretty(value: unknown): string {
  return value === null || value === undefined ? "" : JSON.stringify(value, null, 2);
}

/** Parse an optional JSON object field; throws with the field name on bad input. */
function parseObject(text: string, field: string): Record<string, unknown> | null {
  if (!text.trim()) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${field} is not valid JSON.`);
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${field} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

function toRows(params: Record<string, unknown> | null): ParamRow[] {
  return Object.entries(params ?? {}).map(([name, spec]) => {
    const entry = (spec && typeof spec === "object" ? spec : { value: spec }) as Record<string, unknown>;
    const value = entry.value ?? entry.example ?? "";
    return { name, value: String(value ?? ""), required: Boolean(entry.required) };
  });
}

function fromRows(rows: ParamRow[], previous: Record<string, unknown> | null): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) {
      continue;
    }
    // Keep anything an imported spec stored (schema, description) alongside our fields.
    const earlier = previous?.[name];
    const base = earlier && typeof earlier === "object" ? (earlier as Record<string, unknown>) : {};
    out[name] = { ...base, value: row.value, required: row.required };
  }
  return out;
}

export default function ProxyInfoPage() {
  const params = useParams<{ productId: string; endpointId: string }>();
  const productId = Number(params.productId);
  const endpointId = Number(params.endpointId);
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [pathOpen, setPathOpen] = React.useState(false);
  const [pathValue, setPathValue] = React.useState("");
  const [paramKind, setParamKind] = React.useState<ParamKind | null>(null);
  const [paramRows, setParamRows] = React.useState<ParamRow[]>([]);
  const [sample, setSample] = React.useState<SampleForm | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const endpointQuery = useQuery({
    queryKey: ["admin", "endpoint", endpointId],
    queryFn: () => catalogApi.getEndpoint(endpointId),
    enabled: Number.isFinite(endpointId),
  });

  const endpoint = endpointQuery.data;
  // The end-point detail already carries its response samples.
  const schemas = [...(endpoint?.schemas ?? [])].sort((a, b) =>
    a.status_code.localeCompare(b.status_code),
  );

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "endpoint", endpointId] });
    queryClient.invalidateQueries({ queryKey: ["admin", "product", productId] });
  }

  const updateEndpoint = useMutation({
    mutationFn: (changes: Record<string, unknown>) =>
      catalogApi.updateEndpoint({ endpoint_id: endpointId, ...changes }),
    onSuccess: () => {
      notify("Endpoint updated.", "success");
      setPathOpen(false);
      setParamKind(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const saveSample = useMutation({
    mutationFn: (form: SampleForm) => {
      const payload = {
        status_code: form.status_code,
        req_schema: parseObject(form.req_schema, "Request schema"),
        req_json: parseObject(form.req_json, "Request JSON"),
        res_schema: parseObject(form.res_schema, "Response schema"),
        res_json: parseObject(form.res_json, "Response JSON"),
      };
      return form.schema_id
        ? catalogApi.updateSchema({ ...payload, schema_id: form.schema_id })
        : catalogApi.createSchema({ ...payload, endpoint_id: endpointId });
    },
    onSuccess: (_data, form) => {
      notify(form.schema_id ? "Response sample updated." : "Response sample added.", "success");
      setSample(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const removeSample = useMutation({
    mutationFn: (row: EndpointSchema) => catalogApi.deleteSchema(row.schema_id),
    onSuccess: () => {
      notify("Response sample deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const convert = useMutation({
    mutationFn: async ({ source }: { source: "req" | "res" }) => {
      if (!sample) {
        return null;
      }
      const text = source === "req" ? sample.req_json : sample.res_json;
      const parsed = parseObject(text, source === "req" ? "Request JSON" : "Response JSON");
      if (!parsed) {
        throw new Error("Enter the JSON first, then convert it to a schema.");
      }
      return { source, schema: await catalogApi.generateSchema(parsed) };
    },
    onSuccess: (result) => {
      if (!result || !sample) {
        return;
      }
      setSample(
        result.source === "req"
          ? { ...sample, req_schema: pretty(result.schema) }
          : { ...sample, res_schema: pretty(result.schema) },
      );
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function openParams(kind: ParamKind) {
    const current = kind === "path" ? endpoint?.path_params : endpoint?.header_params;
    const rows = toRows(current ?? null);
    setParamRows(rows.length ? rows : [{ name: "", value: "", required: false }]);
    setParamKind(kind);
  }

  function saveParams() {
    if (!paramKind || !endpoint) {
      return;
    }
    const previous = paramKind === "path" ? endpoint.path_params : endpoint.header_params;
    const value = fromRows(paramRows, previous);
    updateEndpoint.mutate(paramKind === "path" ? { path_params: value } : { header_params: value });
  }

  function editSample(row: EndpointSchema) {
    setSample({
      schema_id: row.schema_id,
      status_code: row.status_code,
      req_schema: pretty(row.req_schema),
      req_json: pretty(row.req_json),
      res_schema: pretty(row.res_schema),
      res_json: pretty(row.res_json),
    });
  }

  function addSample() {
    // Start from the endpoint's request sample so only the response needs writing.
    setSample({
      ...EMPTY_SAMPLE,
      req_schema: pretty(endpoint?.request_schema),
      req_json: pretty(endpoint?.request_sample),
    });
  }

  const pathRows = toRows(endpoint?.path_params ?? null);
  const headerRows = toRows(endpoint?.header_params ?? null);

  return (
    <>
      <PageHeader
        title={endpoint?.display_name ?? "Proxy Info"}
        breadcrumbs={[
          { label: "Home", href: "/admin/dashboard" },
          { label: "API Catalogue", href: "/admin/products" },
          { label: endpoint?.product_name ?? "Product Details", href: `/admin/products/${productId}` },
          { label: "Proxy Info" },
        ]}
        actions={endpoint ? <PublishedBadge published={endpoint.is_published} /> : null}
      />

      <div className="space-y-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle>Api Endpoint Path</CardTitle>
            <Button
              size="sm"
              variant="outline"
              disabled={!endpoint}
              onClick={() => {
                setPathValue(endpoint?.endpoint_url ?? "");
                setPathOpen(true);
              }}
            >
              <Pencil className="h-4 w-4" aria-hidden />
              Edit
            </Button>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <MethodBadge method={endpoint?.method ?? null} />
              <code className="text-sm">{endpoint?.endpoint_url ?? "…"}</code>
            </div>
            {endpoint?.resolved_upstreams ? (
              <dl className="mt-3 grid gap-1 text-xs text-muted-foreground sm:grid-cols-[7rem_1fr]">
                {Object.entries(endpoint.resolved_upstreams).map(([environment, base]) => (
                  <React.Fragment key={environment}>
                    <dt className="font-semibold">{environment}</dt>
                    <dd>
                      {base ? (
                        <code>
                          {base.replace(/\/$/, "")}
                          {endpoint.endpoint_url}
                        </code>
                      ) : environment === "SANDBOX" ? (
                        "Answered from the response samples (mock)"
                      ) : (
                        "Not configured"
                      )}
                    </dd>
                  </React.Fragment>
                ))}
              </dl>
            ) : null}
          </CardContent>
        </Card>

        {(
          [
            ["path", "Path Parameters", pathRows],
            ["header", "Header Parameters", headerRows],
          ] as const
        ).map(([kind, title, rows]) => (
          <Card key={kind}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle>{title}</CardTitle>
              <Button size="sm" variant="outline" disabled={!endpoint} onClick={() => openParams(kind)}>
                <Pencil className="h-4 w-4" aria-hidden />
                Edit
              </Button>
            </CardHeader>
            <CardContent>
              <ParamTable rows={rows} />
            </CardContent>
          </Card>
        ))}

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle>Response Sample</CardTitle>
            <Button size="sm" disabled={!endpoint} onClick={addSample}>
              <Plus className="h-4 w-4" aria-hidden />
              Add
            </Button>
          </CardHeader>
          <CardContent>
            {schemas.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No samples yet. Add one per status code — the portal shows them in the API reference
                and pre-fills the try-it console from the 200 sample.
              </p>
            ) : (
              <div className="table-scroll rounded-xl border border-table-head">
                <table className="w-full min-w-max text-left text-sm text-ink">
                  <thead className="bg-table-head">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Sr. No.</th>
                      <th className="px-5 py-3 font-semibold">Status Code</th>
                      <th className="px-5 py-3 font-semibold">Request JSON</th>
                      <th className="px-5 py-3 font-semibold">Response JSON</th>
                      <th className="px-5 py-3 font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schemas.map((row, index) => (
                      <tr key={row.schema_id} className="odd:bg-white even:bg-[#fafafa]">
                        <td className="px-5 py-3.5">{index + 1}.</td>
                        <td className="px-5 py-3.5">
                          <StatusCodeBadge code={Number(row.status_code)} />
                        </td>
                        <td className="px-5 py-3.5">
                          <code className="line-clamp-1 max-w-64 text-xs">
                            {row.req_json ? JSON.stringify(row.req_json) : "—"}
                          </code>
                        </td>
                        <td className="px-5 py-3.5">
                          <code className="line-clamp-1 max-w-64 text-xs">
                            {row.res_json ? JSON.stringify(row.res_json) : "—"}
                          </code>
                        </td>
                        <td className="px-5 py-3.5">
                          <RowActions
                            recordLabel={`${row.status_code} sample`}
                            onEdit={() => editSample(row)}
                            onDelete={async () => {
                              const ok = await confirm({
                                title: "Delete Sample?",
                                consequence: `The ${row.status_code} request/response sample will be removed.`,
                                confirmLabel: "Delete",
                              });
                              if (ok) {
                                removeSample.mutate(row);
                              }
                            }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {confirmDialog}

      {/* ---------------------------------------------------------- path dialog */}
      <Dialog open={pathOpen} onOpenChange={setPathOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Update Endpoint Path</DialogTitle>
            <DialogDescription>
              Use <code>{"{name}"}</code> for path parameters, e.g. <code>/farmers/{"{farmer_id}"}</code>.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="url_path">Enter Url Path</Label>
            <Input
              id="url_path"
              className="font-mono text-xs"
              value={pathValue}
              onChange={(event) => setPathValue(event.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPathOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={updateEndpoint.isPending}
              disabled={!pathValue.trim()}
              onClick={() => updateEndpoint.mutate({ endpoint_url: pathValue.trim() })}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* -------------------------------------------------------- params dialog */}
      <Dialog open={paramKind !== null} onOpenChange={(open) => !open && setParamKind(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{paramKind === "path" ? "Path Parameters" : "Header Parameters"}</DialogTitle>
            <DialogDescription>
              The value is the sample shown to participants in the try-it console.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <div className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2 text-xs font-medium text-muted-foreground">
              <span>Name (Key)</span>
              <span>Value</span>
              <span>Required</span>
              <span className="sr-only">Remove</span>
            </div>
            {paramRows.map((row, index) => (
              <div key={index} className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-2">
                <Input
                  aria-label="Name"
                  value={row.name}
                  onChange={(event) =>
                    setParamRows(paramRows.map((r, i) => (i === index ? { ...r, name: event.target.value } : r)))
                  }
                />
                <Input
                  aria-label="Value"
                  value={row.value}
                  onChange={(event) =>
                    setParamRows(paramRows.map((r, i) => (i === index ? { ...r, value: event.target.value } : r)))
                  }
                />
                <input
                  type="checkbox"
                  aria-label="Required"
                  className="mx-3 h-4 w-4 accent-brand-600"
                  checked={row.required}
                  onChange={(event) =>
                    setParamRows(
                      paramRows.map((r, i) => (i === index ? { ...r, required: event.target.checked } : r)),
                    )
                  }
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setParamRows(paramRows.filter((_, i) => i !== index))}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                  <span className="sr-only">Remove</span>
                </Button>
              </div>
            ))}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setParamRows([...paramRows, { name: "", value: "", required: false }])}
            >
              <Plus className="h-4 w-4" aria-hidden />
              Add
            </Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setParamKind(null)}>
              Cancel
            </Button>
            <Button loading={updateEndpoint.isPending} onClick={saveParams}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* -------------------------------------------------------- sample dialog */}
      <Dialog open={sample !== null} onOpenChange={(open) => !open && setSample(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{sample?.schema_id ? "Edit Response Sample" : "Add Response Sample"}</DialogTitle>
            <DialogDescription>
              One sample per status code. &quot;Convert to Schema&quot; derives the JSON Schema from the
              JSON beside it.
            </DialogDescription>
          </DialogHeader>

          {sample ? (
            <div className="grid max-h-[65vh] gap-4 overflow-y-auto pr-1 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="status_code">Status Code</Label>
                <Select
                  id="status_code"
                  className="max-w-40"
                  value={sample.status_code}
                  onChange={(event) => setSample({ ...sample, status_code: event.target.value })}
                >
                  {Array.from(new Set([...STATUS_CODES, sample.status_code])).map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </Select>
              </div>

              <JsonField
                id="req_json"
                label="Request JSON"
                value={sample.req_json}
                onChange={(value) => setSample({ ...sample, req_json: value })}
              />
              <JsonField
                id="req_schema"
                label="Request Schema"
                value={sample.req_schema}
                onChange={(value) => setSample({ ...sample, req_schema: value })}
                onConvert={() => convert.mutate({ source: "req" })}
              />
              <JsonField
                id="res_json"
                label="Response JSON"
                value={sample.res_json}
                onChange={(value) => setSample({ ...sample, res_json: value })}
              />
              <JsonField
                id="res_schema"
                label="Response Schema"
                value={sample.res_schema}
                onChange={(value) => setSample({ ...sample, res_schema: value })}
                onConvert={() => convert.mutate({ source: "res" })}
              />
            </div>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSample(null)}>
              Cancel
            </Button>
            <Button loading={saveSample.isPending} onClick={() => sample && saveSample.mutate(sample)}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ParamTable({ rows }: { rows: ParamRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">None.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-4 font-medium">Name (Key)</th>
          <th className="py-2 pr-4 font-medium">Value</th>
          <th className="py-2 font-medium">Required</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name} className="border-b last:border-0">
            <td className="py-2 pr-4 font-mono text-xs">{row.name}</td>
            <td className="py-2 pr-4 font-mono text-xs">{row.value || "—"}</td>
            <td className="py-2">{row.required ? "Yes" : "No"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function JsonField({
  id,
  label,
  value,
  onChange,
  onConvert,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  onConvert?: () => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        {onConvert ? (
          <Button type="button" size="sm" variant="ghost" onClick={onConvert}>
            <Wand2 className="h-4 w-4" aria-hidden />
            Convert to Schema
          </Button>
        ) : null}
      </div>
      <Textarea
        id={id}
        className="min-h-56 font-mono text-xs"
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Loader2 } from "lucide-react";

import { ApiExplorerNav } from "@/components/portal/api-explorer-nav";
import { CodeBlock, LanguagePicker, grammarFor } from "@/components/portal/code-block";
import { ApiBanner, CopyButton, Panel, Tabs } from "@/components/portal/console-ui";
import { ParamFields, SchemaFields } from "@/components/portal/schema-fields";
import { MethodBadge } from "@/components/ui/status-badge";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { catalogApi } from "@/lib/services/catalog";
import { prettyJson } from "@/lib/utils";

/**
 * API documentation, as the reference sandbox's API reference page: what the
 * admin published for an end-point (parameters, body and response fields,
 * request and response samples per status code, code samples) and a
 * "Test in Sandbox" button that opens the sandbox test page.
 */
export default function EndpointDocsPage() {
  const params = useParams<{ productId: string; endpointId: string }>();
  const productId = Number(params.productId);
  const endpointId = Number(params.endpointId);

  // Keyed by end-point so switching APIs resets the selected sample.
  return <EndpointDocs key={endpointId} productId={productId} endpointId={endpointId} />;
}

function EndpointDocs({ productId, endpointId }: { productId: number; endpointId: number }) {
  const [status, setStatus] = React.useState<string | null>(null);
  const [language, setLanguage] = React.useState("curl");

  const endpointQuery = useQuery({
    queryKey: ["participant", "endpoint", endpointId],
    queryFn: () => catalogApi.portalEndpoint(endpointId),
    enabled: Number.isFinite(endpointId),
    staleTime: CATALOG_STALE_MS,
  });
  const codeQuery = useQuery({
    queryKey: ["participant", "endpoint", endpointId, "code", language, "SANDBOX"],
    queryFn: () => catalogApi.codeSample(endpointId, language, "SANDBOX"),
    enabled: Number.isFinite(endpointId),
    staleTime: CATALOG_STALE_MS,
  });

  const endpoint = endpointQuery.data;
  if (endpointQuery.isLoading) {
    return (
      <p className="flex items-center gap-2 py-16 text-sm text-subtle">
        <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
        Loading API…
      </p>
    );
  }
  if (!endpoint) {
    return <p className="py-16 text-center text-sm text-subtle">This API is not available.</p>;
  }

  const schemas = [...endpoint.schemas]
    .filter((row) => row.is_enabled)
    .sort((a, b) => a.status_code.localeCompare(b.status_code));
  const active =
    schemas.find((row) => row.status_code === status) ??
    schemas.find((row) => row.status_code === "200") ??
    schemas[0] ??
    null;
  const requestSample = active?.req_json ?? endpoint.request_sample;
  const requestSchema = endpoint.request_schema ?? active?.req_schema;
  const hasParams =
    Object.keys(endpoint.path_params ?? {}).length +
      Object.keys(endpoint.query_params ?? {}).length +
      Object.keys(endpoint.header_params ?? {}).length >
    0;
  const testHref = `/participant/product/${productId}/${endpointId}`;

  return (
    <>
      <ApiBanner eyebrow="API Reference" title={endpoint.display_name ?? endpoint.endpoint_url}>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-sm">
          {endpoint.api_type ? (
            <span className="rounded-full bg-brand-gold px-3 py-0.5 font-semibold text-[#0b2a1a]">
              {endpoint.api_type}
            </span>
          ) : null}
          <span className="rounded-full bg-white/15 px-3 py-0.5">{endpoint.product_name}</span>
        </div>
        {endpoint.description ? (
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-white/85">{endpoint.description}</p>
        ) : null}
      </ApiBanner>

      {/* API menu | reference | samples, as the reference sandbox's API page. */}
      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1.15fr)_minmax(0,1fr)]">
        <ApiExplorerNav
          activeEndpointId={endpointId}
          activeProductId={productId}
          back={{ href: `/participant/our-product/${productId}`, label: endpoint.product_name ?? "Back" }}
        />

        {/* ---------------------------------------------------- reference */}
        <div className="flex min-w-0 flex-col gap-6">
          {/* URL bar + primary action */}
          <div className="flex flex-col gap-3 rounded-2xl border border-hairline bg-white p-3 shadow-sm md:flex-row md:items-center">
            <div className="flex min-w-0 flex-1 items-center gap-3 rounded-xl bg-surface-soft px-3 py-2.5">
              <MethodBadge method={endpoint.method} />
              <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink" title={endpoint.endpoint_url ?? ""}>
                {endpoint.endpoint_url}
              </code>
              <CopyButton text={endpoint.endpoint_url ?? undefined} />
            </div>
            <Link
              href={testHref}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-linear-to-b from-brand-bright to-brand-deep px-5 py-3 text-sm font-semibold text-white shadow-sm transition-[filter] hover:brightness-110"
            >
              <FlaskConical className="h-4 w-4" aria-hidden />
              Test in Sandbox
            </Link>
          </div>

          {hasParams ? (
            <Panel title="Parameters">
              <div className="flex flex-col gap-5">
                <ParamSection title="Path parameters" params={endpoint.path_params} />
                <ParamSection title="Query parameters" params={endpoint.query_params} />
                <ParamSection title="Header parameters" params={endpoint.header_params} />
              </div>
            </Panel>
          ) : null}

          {endpoint.method !== "GET" ? (
            <Panel title="Request body">
              <SchemaFields schema={requestSchema} empty="This end-point takes no documented body fields." />
            </Panel>
          ) : null}

          <Panel
            title="Response"
            tabs={
              schemas.length > 0 ? (
                <Tabs
                  value={active?.status_code ?? ""}
                  onChange={setStatus}
                  items={schemas.map((row) => ({ id: row.status_code, label: row.status_code }))}
                />
              ) : null
            }
          >
            <SchemaFields key={active?.status_code ?? "none"} schema={active?.res_schema} empty="No response fields documented for this status." />
          </Panel>
        </div>

        {/* ------------------------------------------------------ samples */}
        <div className="flex min-w-0 flex-col gap-6 lg:col-start-2 xl:col-start-auto">
          <Panel title="Code sample" action={<CopyButton text={codeQuery.data?.code} />}>
            <LanguagePicker value={language} onChange={setLanguage} />
            <CodeBlock
              className="mt-4 max-h-80 min-h-40"
              language={grammarFor(language)}
              wrap
              code={codeQuery.isLoading ? "Loading…" : (codeQuery.data?.code ?? "No sample available.")}
            />
          </Panel>

          {endpoint.method !== "GET" ? (
            <Panel title="Request sample" action={<CopyButton text={prettyJson(requestSample)} />}>
              <CodeBlock className="max-h-96 min-h-32" language="json" code={prettyJson(requestSample) || "(no body)"} />
            </Panel>
          ) : null}

          <Panel
            title={
              <span className="flex items-center gap-2">
                Response sample
                {active ? (
                  <label className="sr-only" htmlFor="sample-status">
                    Status code
                  </label>
                ) : null}
              </span>
            }
            action={
              <div className="flex items-center gap-2">
                {schemas.length > 0 ? (
                  <select
                    id="sample-status"
                    value={active?.status_code ?? ""}
                    onChange={(event) => setStatus(event.target.value)}
                    className="rounded-lg border border-hairline bg-white px-2 py-1 text-xs font-semibold text-ink focus:border-brand-bright focus:outline-none"
                  >
                    {schemas.map((row) => (
                      <option key={row.status_code} value={row.status_code}>
                        {row.status_code}
                      </option>
                    ))}
                  </select>
                ) : null}
                <CopyButton text={prettyJson(active?.res_json)} />
              </div>
            }
          >
            {active ? (
              <CodeBlock className="max-h-96 min-h-32" language="json" code={prettyJson(active.res_json) || "(no body)"} />
            ) : (
              <p className="py-8 text-center text-sm text-subtle">No response samples have been published.</p>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function ParamSection({ title, params }: { title: string; params: Record<string, unknown> | null }) {
  if (!params || Object.keys(params).length === 0) {
    return null;
  }
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-subtle uppercase">{title}</h3>
      <ParamFields params={params} />
    </div>
  );
}

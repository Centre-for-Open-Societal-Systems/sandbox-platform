"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, KeyRound, Loader2, Play, Plus, RotateCcw, Send, Trash2, Wand2 } from "lucide-react";

import { ApiExplorerNav } from "@/components/portal/api-explorer-nav";
import { CodeBlock, LanguagePicker, grammarFor } from "@/components/portal/code-block";
import {
  ApiBanner,
  CODE_BLOCK,
  CopyButton,
  FIELD,
  Panel,
  Tabs,
  formatBytes,
  stripEmpty,
} from "@/components/portal/console-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MethodBadge, StatusCodeBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useEnvironments } from "@/hooks/use-environments";
import { ENVIRONMENTS, type Environment } from "@/lib/config";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { appsApi } from "@/lib/services/apps";
import { catalogApi } from "@/lib/services/catalog";
import { cn, parseJsonOrNull, prettyJson } from "@/lib/utils";
import type { AppToken, CodeSampleForm, GatewayAuth, TryItResult } from "@/types/api";

type RequestTab = "body" | "headers" | "params";

/** Header the gateway reads an app's API key from (GATEWAY_APP_KEY_HEADER). */
const APP_KEY_HEADER = "apikey";

/** `rows` with the header `name` present (added if missing) and set to `value`. */
function withHeader(rows: HeaderRow[], name: string, value: string): HeaderRow[] {
  const index = rows.findIndex((row) => row.key.trim().toLowerCase() === name.toLowerCase());
  if (index === -1) {
    return [...rows, { key: name, value, enabled: true }];
  }
  return rows.map((row, i) => (i === index ? { ...row, value, enabled: true } : row));
}

/** `rows` without the header `name`. */
function withoutHeader(rows: HeaderRow[], name: string): HeaderRow[] {
  return rows.filter((row) => row.key.trim().toLowerCase() !== name.toLowerCase());
}

/** The header that identifies the caller: the app's API key, or (OAuth) the app token header. */
function withCaller(rows: HeaderRow[], auth: GatewayAuth | undefined, key: string, token: string): HeaderRow[] {
  if (auth?.mode === "oauth") {
    return withHeader(withoutHeader(rows, auth.app_key_header), auth.token_header, token);
  }
  return withHeader(rows, auth?.app_key_header ?? APP_KEY_HEADER, key);
}

interface HeaderRow {
  key: string;
  value: string;
  enabled: boolean;
}

/**
 * Sandbox test page, as the reference sandbox's "Test in Sandbox" screen: the
 * request is pre-filled with the sample the admin published; the participant
 * edits it and runs the API. Tokens come from a token API the admin publishes
 * in the catalogue, and go in the headers like any other value.
 */
export default function SandboxTestPage() {
  const params = useParams<{ productId: string; endpointId: string }>();
  const productId = Number(params.productId);
  const endpointId = Number(params.endpointId);

  // Keyed by end-point so switching APIs starts from that API's sample.
  return <SandboxConsole key={endpointId} productId={productId} endpointId={endpointId} />;
}

function SandboxConsole({ productId, endpointId }: { productId: number; endpointId: number }) {
  const { notify } = useToast();
  const available = useEnvironments();

  const [environment, setEnvironment] = React.useState<Environment>(available[0] ?? "UAT");
  /** Call as one of the participant's apps: the sandbox sends its API key. */
  const [appId, setAppId] = React.useState("");
  const [pathParams, setPathParams] = React.useState<Record<string, string>>({});
  const [queryParams, setQueryParams] = React.useState<Record<string, string>>({});
  const [headers, setHeaders] = React.useState<HeaderRow[]>([]);
  const [revealed, setRevealed] = React.useState<Set<number>>(new Set());
  const [bodyText, setBodyText] = React.useState("");
  const [requestTab, setRequestTab] = React.useState<RequestTab>("body");
  const [language, setLanguage] = React.useState("curl");
  const [result, setResult] = React.useState<TryItResult | null>(null);

  // Documentation and the try-it pre-fill come in one response, shared (same
  // key) with the documentation page, so opening "Test in Sandbox" is instant.
  const endpointQuery = useQuery({
    queryKey: ["participant", "endpoint", endpointId],
    queryFn: () => catalogApi.portalEndpoint(endpointId),
    enabled: Number.isFinite(endpointId),
    staleTime: CATALOG_STALE_MS,
  });
  const sampleData = endpointQuery.data?.sample;
  const appsQuery = useQuery({ queryKey: ["participant", "apps"], queryFn: () => appsApi.list() });
  const authQuery = useQuery({
    queryKey: ["participant", "gateway-auth"],
    queryFn: () => appsApi.gatewayAuth(),
    staleTime: CATALOG_STALE_MS,
  });
  const gatewayAuth = authQuery.data;
  /** OAuth: the gateway takes the app's access token, not its key ("Get token" below). */
  const oauth = gatewayAuth?.mode === "oauth";
  const [appToken, setAppToken] = React.useState<AppToken | null>(null);
  const [seeded, setSeeded] = React.useState(false);
  const callableApps = (appsQuery.data ?? []).filter(
    (app) => app.status === 1 && app.credentials.some((c) => c.status === 1),
  );
  /** The app's newest active key (the one the server sends), or blank. */
  function appKeyOf(id: string): string {
    const app = callableApps.find((item) => item.app_id === id);
    return app?.credentials.find((c) => c.status === 1 && c.api_key)?.api_key ?? "";
  }

  /** The app's newest active secret (only its owner gets it), or blank. */
  function appSecretOf(id: string): string {
    const app = callableApps.find((item) => item.app_id === id);
    return app?.credentials.find((c) => c.status === 1 && c.api_key)?.api_secret ?? "";
  }

  function selectApp(id: string) {
    setAppId(id);
    setAppToken(null); // a token belongs to one app
    setHeaders((rows) => withCaller(rows, gatewayAuth, appKeyOf(id), ""));
  }

  // OAuth 2.0 client credentials, as the partner does it: the sandbox sends the
  // app's API key + secret to the token endpoint (the secret stays on the server)
  // and the token goes into the token header, where the partner sees it.
  const getToken = useMutation({
    mutationFn: () => appsApi.token(appId),
    onSuccess: (token) => {
      setAppToken(token);
      setHeaders((rows) => withHeader(rows, token.header, token.access_token));
      notify(`Token added to the ${token.header} header.`, "success");
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  // Seeded before the gateway's sign-in was known: put the right caller header in.
  const [authApplied, setAuthApplied] = React.useState<string | null>(null);
  if (gatewayAuth && seeded && authApplied !== gatewayAuth.mode) {
    setAuthApplied(gatewayAuth.mode);
    setHeaders((rows) => withCaller(rows, gatewayAuth, appKeyOf(appId), appToken?.access_token ?? ""));
  }
  // The code sample follows the form: rebuilt shortly after the last edit, so
  // what is copied into Postman is exactly what Run would send.
  const [codeForm, setCodeForm] = React.useState<CodeSampleForm | null>(null);
  const codeQuery = useQuery({
    queryKey: ["participant", "endpoint", endpointId, "code", language, environment, codeForm],
    queryFn: () => catalogApi.codeSample(endpointId, language, environment, codeForm),
    enabled: Number.isFinite(endpointId),
    staleTime: CATALOG_STALE_MS,
    placeholderData: keepPreviousData,
  });

  function resetToSample() {
    const sample = sampleData;
    if (!sample) {
      return;
    }
    setPathParams(Object.fromEntries(Object.keys(sample.path_params ?? {}).map((key) => [key, ""])));
    setQueryParams(Object.fromEntries(Object.keys(sample.query_params ?? {}).map((key) => [key, ""])));
    const sampleHeaders = Object.entries(sample.headers ?? {}).map(([key, value]) => ({
      key,
      value: String(value ?? ""),
      enabled: true,
    }));
    // The caller header is always listed: blank until an app (and, OAuth, its token) is chosen.
    setHeaders(withCaller(sampleHeaders, gatewayAuth, appKeyOf(appId), appToken?.access_token ?? ""));
    setBodyText(prettyJson(sample.body));
    setResult(null);
  }

  // Seed from the published sample once it arrives.
  if (!seeded && sampleData) {
    setSeeded(true);
    resetToSample();
  }

  const methodHasBody = endpointQuery.data?.method !== "GET";
  React.useEffect(() => {
    if (!seeded) {
      return;
    }
    const body = bodyText.trim() ? parseJsonOrNull(bodyText) : null;
    if (bodyText.trim() && body === null) {
      return; // Half-typed JSON: keep the last good snippet.
    }
    const timer = setTimeout(
      () =>
        setCodeForm({
          path_params: pathParams,
          query_params: stripEmpty(queryParams),
          headers: Object.fromEntries(
            headers.filter((row) => row.enabled && row.key.trim()).map((row) => [row.key.trim(), row.value]),
          ),
          has_body: methodHasBody && Boolean(bodyText.trim()),
          body,
          app_id: appId || null,
        }),
      400,
    );
    return () => clearTimeout(timer);
  }, [seeded, bodyText, pathParams, queryParams, headers, appId, methodHasBody]);

  const execute = useMutation({
    mutationFn: () => {
      const body = bodyText.trim() ? parseJsonOrNull(bodyText) : null;
      if (bodyText.trim() && body === null) {
        setRequestTab("body");
        throw new Error("The request body must be valid JSON.");
      }
      return catalogApi.tryIt({
        endpoint_id: endpointId,
        environment,
        path_params: stripEmpty(pathParams),
        query_params: stripEmpty(queryParams),
        headers: Object.fromEntries(
          headers.filter((row) => row.enabled && row.key.trim()).map((row) => [row.key.trim(), row.value]),
        ),
        body,
        app_id: appId || null,
      });
    },
    onSuccess: setResult,
    onError: (error: Error) => notify(error.message, "error"),
  });

  const endpoint = endpointQuery.data;
  const hasBody = endpoint?.method !== "GET";
  const paramCount = Object.keys(pathParams).length + Object.keys(queryParams).length;
  const responseText = result ? prettyJson(result.body) : "";
  const isMock = result?.headers?.["x-sandbox-mock"] === "true";

  function formatBody() {
    const parsed = parseJsonOrNull(bodyText);
    if (parsed === null) {
      notify("The request body is not valid JSON.", "error");
      return;
    }
    setBodyText(prettyJson(parsed));
  }

  function updateHeader(index: number, patch: Partial<HeaderRow>) {
    setHeaders((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  return (
    <>
      <ApiBanner eyebrow="Sandbox" title={endpoint?.display_name ?? "Test API"}>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-sm">
          {endpoint?.api_type ? (
            <span className="rounded-full bg-brand-gold px-3 py-0.5 font-semibold text-[#0b2a1a]">
              {endpoint.api_type}
            </span>
          ) : null}
          {endpoint?.product_name ? (
            <span className="rounded-full bg-white/15 px-3 py-0.5">{endpoint.product_name}</span>
          ) : null}
        </div>
      </ApiBanner>

      {/* API menu | request | code + response, as the reference sandbox page. */}
      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_minmax(0,1fr)]">
        <ApiExplorerNav
          activeEndpointId={endpointId}
          activeProductId={productId}
          hrefFor={(product, endpoint) => `/participant/product/${product}/${endpoint}`}
          back={{ href: `/participant/product/${productId}/endpoint/${endpointId}`, label: "API documentation" }}
        />

        {/* ------------------------------------------------------- request */}
        <div className="flex min-w-0 flex-col gap-6">
          {/* URL bar on top, labelled controls below: one row was too narrow in the 3-column layout. */}
          <form
            className="flex flex-col gap-3 rounded-2xl border border-hairline bg-white p-4 shadow-sm"
            onSubmit={(event) => {
              event.preventDefault();
              execute.mutate();
            }}
          >
            <div className="flex min-w-0 items-center gap-3 rounded-xl bg-surface-soft px-3 py-2.5">
              <MethodBadge method={endpoint?.method ?? null} />
              <code className="min-w-0 flex-1 truncate font-mono text-sm text-ink" title={endpoint?.endpoint_url ?? ""}>
                {endpoint?.endpoint_url ?? "…"}
              </code>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] sm:items-end">
              <div className="flex min-w-0 flex-col gap-1">
                <label htmlFor="environment" className="text-xs font-semibold text-subtle">
                  Environment
                </label>
                <select
                  id="environment"
                  value={environment}
                  onChange={(event) => setEnvironment(event.target.value as Environment)}
                  className="h-11 w-full rounded-[10px] border border-hairline bg-white px-3 text-sm font-semibold text-ink focus:border-brand-bright focus:outline-none"
                >
                  {ENVIRONMENTS.map((item) => (
                    <option key={item} value={item} disabled={!available.includes(item)}>
                      {item}
                      {available.includes(item) ? "" : " (not approved)"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <label htmlFor="call-as-app" className="text-xs font-semibold text-subtle">
                  Call as app
                </label>
                <select
                  id="call-as-app"
                  value={appId}
                  onChange={(event) => selectApp(event.target.value)}
                  title={
                    oauth
                      ? "The app whose access token the call sends (Get token below)"
                      : "The app whose API key the call sends (apikey header)"
                  }
                  className="h-11 w-full truncate rounded-[10px] border border-hairline bg-white px-3 text-sm text-ink focus:border-brand-bright focus:outline-none"
                >
                  <option value="">{callableApps.length ? (oauth ? "No app" : "No app key") : "No apps yet"}</option>
                  {callableApps.map((app) => (
                    <option key={app.app_id} value={app.app_id}>
                      {app.name}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" size="lg" loading={execute.isPending} className="w-full sm:w-auto sm:min-w-28">
                {!execute.isPending ? <Play className="h-4 w-4" aria-hidden /> : null}
                Run
              </Button>
            </div>
            {!appId ? (
              <p className="text-xs text-subtle">
                {callableApps.length
                  ? oauth
                    ? `Pick an app and get its token, or paste a token in the ${gatewayAuth?.token_header} header: the gateway answers 401 without one.`
                    : "Pick an app: the gateway answers 401 to calls without an app key."
                  : "The gateway needs an app. Create an app with this API's product in "}
                {callableApps.length ? null : (
                  <Link href="/participant/apps" className="font-semibold text-brand-bright hover:underline">
                    My Apps
                  </Link>
                )}
                {callableApps.length ? null : "."}
              </p>
            ) : null}
          </form>

          {oauth && gatewayAuth ? (
            <AppTokenPanel
              auth={gatewayAuth}
              clientId={appKeyOf(appId)}
              clientSecret={appSecretOf(appId)}
              hasApp={Boolean(appId)}
              token={appToken}
              loading={getToken.isPending}
              onGet={() => getToken.mutate()}
            />
          ) : null}

          <Panel
            title="Request"
            tabs={
              <Tabs
                value={requestTab}
                onChange={(value) => setRequestTab(value as RequestTab)}
                items={[
                  ...(hasBody ? [{ id: "body", label: "Body" }] : []),
                  { id: "headers", label: "Headers", count: headers.filter((row) => row.enabled).length },
                  { id: "params", label: "Params", count: paramCount },
                ]}
              />
            }
            action={
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={resetToSample}
                title="Reset to the published sample"
              >
                <RotateCcw className="h-4 w-4" aria-hidden />
                Reset
              </Button>
            }
          >
            {requestTab === "body" && hasBody ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-subtle">JSON · pre-filled with the published sample</span>
                  <button
                    type="button"
                    onClick={formatBody}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-brand-bright hover:underline"
                  >
                    <Wand2 className="h-3.5 w-3.5" aria-hidden />
                    Format
                  </button>
                </div>
                <textarea
                  aria-label="Request body"
                  spellCheck={false}
                  value={bodyText}
                  onChange={(event) => setBodyText(event.target.value)}
                  placeholder="{}"
                  className={cn(
                    CODE_BLOCK,
                    "min-h-80 w-full resize-y border-0 focus:ring-2 focus:ring-brand-bright focus:outline-none",
                  )}
                />
              </div>
            ) : null}

            {requestTab === "headers" || (requestTab === "body" && !hasBody) ? (
              <div className="flex flex-col gap-2">
                {headers.map((row, index) => {
                  const secret = /authorization|token|key|secret/i.test(row.key);
                  const shown = revealed.has(index);
                  return (
                    <div key={index} className="grid grid-cols-[auto_1fr_1.4fr_auto] items-center gap-2">
                      <input
                        type="checkbox"
                        aria-label={`Send header ${row.key || index + 1}`}
                        checked={row.enabled}
                        onChange={(event) => updateHeader(index, { enabled: event.target.checked })}
                        className="h-4 w-4"
                      />
                      <input
                        aria-label="Header name"
                        value={row.key}
                        onChange={(event) => updateHeader(index, { key: event.target.value })}
                        placeholder="Header"
                        className={FIELD}
                      />
                      <div className="relative">
                        <input
                          aria-label="Header value"
                          type={secret && !shown ? "password" : "text"}
                          value={row.value}
                          onChange={(event) => updateHeader(index, { value: event.target.value })}
                          placeholder="Value"
                          className={cn(FIELD, secret && "pr-8")}
                        />
                        {secret ? (
                          <button
                            type="button"
                            aria-label={shown ? "Hide value" : "Show value"}
                            onClick={() =>
                              setRevealed((current) => {
                                const next = new Set(current);
                                if (next.has(index)) {
                                  next.delete(index);
                                } else {
                                  next.add(index);
                                }
                                return next;
                              })
                            }
                            className="absolute top-1/2 right-2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                          >
                            {shown ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                          </button>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        aria-label="Remove header"
                        onClick={() => setHeaders(headers.filter((_, i) => i !== index))}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-subtle hover:bg-red-50 hover:text-red-600"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </button>
                    </div>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setHeaders([...headers, { key: "", value: "", enabled: true }])}
                  className="mt-1 inline-flex items-center gap-1.5 self-start rounded-lg px-2 py-1.5 text-sm font-semibold text-brand-bright hover:bg-surface-soft"
                >
                  <Plus className="h-4 w-4" aria-hidden />
                  Add header
                </button>
              </div>
            ) : null}

            {requestTab === "params" ? (
              paramCount === 0 ? (
                <p className="py-10 text-center text-sm text-subtle">
                  This end-point takes no path or query parameters.
                </p>
              ) : (
                <div className="flex flex-col gap-5">
                  <ParamGroup title="Path parameters" values={pathParams} onChange={setPathParams} />
                  <ParamGroup title="Query parameters" values={queryParams} onChange={setQueryParams} />
                </div>
              )
            ) : null}
          </Panel>
        </div>

        {/* ----------------------------------------------- code + response */}
        <div className="flex min-w-0 flex-col gap-6 lg:col-start-2 xl:col-start-auto">
          <Panel title="Code sample" action={<CopyButton text={codeQuery.data?.code} />}>
            <LanguagePicker value={language} onChange={setLanguage} />
            <CodeBlock
              className="mt-4 max-h-72 min-h-32"
              language={grammarFor(language)}
              wrap
              code={codeQuery.isLoading ? "Loading…" : (codeQuery.data?.code ?? "No sample available.")}
            />
          </Panel>

          <Panel title="Response" action={result ? <CopyButton text={responseText} /> : null}>
            {execute.isPending ? (
              <div className="flex min-h-80 flex-col items-center justify-center gap-2 text-sm text-subtle">
                <Loader2 className="h-6 w-6 animate-spin text-brand-bright" aria-hidden />
                Running…
              </div>
            ) : result ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-surface-soft px-3 py-2 text-xs text-slate-600">
                  <span className="flex items-center gap-1.5">
                    Status <StatusCodeBadge code={result.status_code} />
                  </span>
                  <span>
                    Time <strong className="text-ink">{Math.round(result.latency_ms)} ms</strong>
                  </span>
                  <span>
                    Size <strong className="text-ink">{formatBytes(new Blob([responseText]).size)}</strong>
                  </span>
                  {isMock ? <Badge variant="warning">Sample response</Badge> : null}
                  <span
                    className="ml-auto font-mono text-[0.7rem] text-subtle"
                    title="Transaction ID — find it in API History"
                  >
                    {result.transaction_id}
                  </span>
                </div>
                {result.error ? (
                  <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {result.error}
                  </p>
                ) : null}
                <CodeBlock className="max-h-[28rem] min-h-64" language="json" code={responseText || "(empty body)"} />
              </div>
            ) : (
              <div className="flex min-h-80 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-hairline text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-soft text-brand-bright">
                  <Send className="h-5 w-5" aria-hidden />
                </span>
                <p className="text-sm font-semibold text-ink">No response yet</p>
                <p className="max-w-xs text-sm text-subtle">
                  Press <strong>Run</strong> to call this API. The result appears here and in API History.
                </p>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

/** The token request as one curl command (imports into Postman as one request). */
function tokenCurl(url: string, grantType: string, clientId: string, clientSecret: string): string {
  return [
    `curl -X POST '${url}'`,
    "  -H 'Content-Type: application/x-www-form-urlencoded'",
    `  --data-urlencode 'grant_type=${grantType}'`,
    `  --data-urlencode 'client_id=${clientId}'`,
    `  --data-urlencode 'client_secret=${clientSecret}'`,
  ].join(" \\\n");
}

/**
 * Step 1 of an OAuth call (GATEWAY_PARTNER_AUTH=oauth), as a developer portal's
 * "Authorize": the app's token request (client credentials = its API key +
 * secret) as its own curl to copy into Postman, and "Get token", which fetches
 * a token and puts it in the token header of the request below.
 */
function AppTokenPanel({
  auth,
  clientId,
  clientSecret,
  hasApp,
  token,
  loading,
  onGet,
}: {
  auth: GatewayAuth;
  clientId: string;
  clientSecret: string;
  hasApp: boolean;
  token: AppToken | null;
  loading: boolean;
  onGet: () => void;
}) {
  const url = auth.token_url ?? "";
  const grant = auth.grant_type ?? "client_credentials";
  const id = clientId || "<API key>";
  // Shown with the secret masked; copied with it, so the command runs as-is.
  const shown = tokenCurl(url, grant, id, clientSecret ? "••••••••" : "<API secret>");
  const copied = tokenCurl(url, grant, id, clientSecret || "<API secret>");
  return (
    <Panel
      title={
        <span className="inline-flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-brand-bright" aria-hidden />
          App token
        </span>
      }
      action={
        <div className="flex items-center gap-2">
          <CopyButton text={copied} label="Copy curl" />
          <Button type="button" size="sm" onClick={onGet} loading={loading} disabled={!hasApp}>
            Get token
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <CodeBlock className="max-h-40" language={grammarFor("curl")} wrap code={shown} />
        {!hasApp ? <p className="text-xs text-subtle">Pick an app above to get its token.</p> : null}
        {token ? (
          <div className="flex items-center gap-2">
            <code
              className="min-w-0 flex-1 truncate rounded-lg bg-surface-soft px-3 py-2 font-mono text-[0.7rem] text-ink"
              title={token.access_token}
            >
              {token.access_token}
            </code>
            <CopyButton text={token.access_token} label="Copy token" />
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function ParamGroup({
  title,
  values,
  onChange,
}: {
  title: string;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}) {
  const keys = Object.keys(values);
  if (keys.length === 0) {
    return null;
  }
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-xs font-semibold tracking-wide text-subtle uppercase">{title}</legend>
      {keys.map((key) => (
        <div key={key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] items-center gap-3">
          <label htmlFor={`param-${title}-${key}`} className="truncate font-mono text-xs font-semibold text-ink">
            {key}
          </label>
          <input
            id={`param-${title}-${key}`}
            value={values[key] ?? ""}
            onChange={(event) => onChange({ ...values, [key]: event.target.value })}
            className={FIELD}
          />
        </div>
      ))}
    </fieldset>
  );
}

"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  Gauge,
  ListTree,
  ServerCrash,
  Timer,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import { Input, Select } from "@/components/ui/input";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { IconAction } from "@/components/ui/row-actions";
import { SearchableMultiSelect, type LookupItem } from "@/components/ui/searchable-multi-select";
import { MethodBadge, StatusCodeBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { saveBlob } from "@/lib/api-client";
import { ENVIRONMENTS, HTTP_METHODS } from "@/lib/config";
import { adminApi } from "@/lib/services/admin";
import { formatDateTime, formatNumber } from "@/lib/utils";
import type { ApiUsageGroup, ApiUsageRow } from "@/types/api";

const GROUPS: { id: ApiUsageGroup; label: string }[] = [
  { id: "participant", label: "By Partner" },
  { id: "participant_endpoint", label: "Partner × API" },
  { id: "endpoint", label: "By API" },
  { id: "app", label: "By App" },
  { id: "product", label: "By Product" },
  { id: "day", label: "By Day" },
  { id: "status", label: "By Status Code" },
];

const PERIODS = [
  { id: "this-month", label: "This month" },
  { id: "last-month", label: "Last month" },
  { id: "last-7", label: "Last 7 days" },
  { id: "last-30", label: "Last 30 days" },
  { id: "all", label: "All time" },
  { id: "custom", label: "Custom range" },
] as const;
type PeriodId = (typeof PERIODS)[number]["id"];

const CHART_GRID = "var(--color-hairline)";
const CHART_LINE = "var(--color-brand-500)";
const STATUS_COLORS = { success: "#2E7D32", client: "#B26A00", server: "#DA131A" };

/** Local calendar date as YYYY-MM-DD (not UTC, so "today" is the admin's today). */
function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function periodRange(period: PeriodId): { date_from?: string; date_to?: string } {
  const today = new Date();
  const daysAgo = (days: number) => new Date(today.getFullYear(), today.getMonth(), today.getDate() - days);
  switch (period) {
    case "this-month":
      return { date_from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), date_to: isoDay(today) };
    case "last-month":
      return {
        date_from: isoDay(new Date(today.getFullYear(), today.getMonth() - 1, 1)),
        date_to: isoDay(new Date(today.getFullYear(), today.getMonth(), 0)),
      };
    case "last-7":
      return { date_from: isoDay(daysAgo(6)), date_to: isoDay(today) };
    case "last-30":
      return { date_from: isoDay(daysAgo(29)), date_to: isoDay(today) };
    default:
      return {};
  }
}

const DEFAULT_FILTERS = { group_by: "participant", ...periodRange("this-month") };

function shortDay(label: string): string {
  const date = new Date(`${label}T00:00:00`);
  return Number.isNaN(date.getTime()) ? label : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

function SuccessRate({ rate }: { rate: number | null }) {
  if (rate === null) return <span className="text-subtle">—</span>;
  return <Badge variant={rate >= 95 ? "success" : rate >= 80 ? "warning" : "danger"}>{rate}%</Badge>;
}

function statusColor(label: string): string {
  const code = Number(label);
  if (code >= 200 && code < 400) return STATUS_COLORS.success;
  if (code >= 400 && code < 500) return STATUS_COLORS.client;
  return STATUS_COLORS.server;
}

function Count({ value, tone }: { value: number; tone?: "client" | "server" }) {
  const color = value > 0 && tone ? (tone === "client" ? "text-[#B26A00]" : "text-[#DA131A]") : "text-ink";
  return <span className={`tabular-nums ${color}`}>{formatNumber(value)}</span>;
}

function Tile({ label, value, icon: Icon, hint }: { label: string; value: string; icon: LucideIcon; hint?: string }) {
  return (
    <div className="flex h-full items-start justify-between gap-3 rounded-2xl border border-[#e4efe4] bg-surface-soft px-5 py-4">
      <div className="min-w-0">
        <p className="text-sm text-ink/70">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">{value}</p>
        {hint ? <p className="mt-1 truncate text-xs text-subtle">{hint}</p> : null}
      </div>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-brand-bright">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
    </div>
  );
}

export default function ApiUsagePage() {
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "total_calls", filters: DEFAULT_FILTERS });
  const [period, setPeriod] = React.useState<PeriodId>("this-month");
  const [exporting, setExporting] = React.useState<"xlsx" | "csv" | null>(null);
  const [partners, setPartners] = React.useState<LookupItem[]>([]);
  const [apps, setApps] = React.useState<LookupItem[]>([]);
  const partnerIds = React.useMemo(() => partners.map((item) => item.id), [partners]);

  const group = (list.filters.group_by as ApiUsageGroup) ?? "participant";
  const filterValue = (key: string) => (list.filters[key] as string | number | undefined) ?? "";
  // The report filters without paging / sorting / grouping: what the summary counts.
  const summaryFilters = React.useMemo(
    () => Object.fromEntries(Object.entries(list.filters).filter(([key]) => key !== "group_by")),
    [list.filters],
  );

  const usageQuery = useQuery({
    queryKey: ["admin", "logs", "api-usage", list.query],
    queryFn: () => adminApi.apiUsage(list.query),
  });
  const summaryQuery = useQuery({
    queryKey: ["admin", "logs", "api-usage", "summary", summaryFilters],
    queryFn: () => adminApi.apiUsageSummary(summaryFilters),
  });
  const optionsQuery = useQuery({
    queryKey: ["admin", "logs", "api-usage", "options"],
    queryFn: adminApi.apiUsageOptions,
    staleTime: 60_000,
  });

  const summary = summaryQuery.data;
  const options = optionsQuery.data;

  function choosePartners(items: LookupItem[]) {
    setPartners(items);
    list.setFilter("participant_ids", items.length ? items.map((item) => item.id) : undefined);
    // The app list depends on the partners: start the app choice again.
    setApps([]);
    list.setFilter("app_ids", undefined);
  }

  function chooseApps(items: LookupItem[]) {
    setApps(items);
    list.setFilter("app_ids", items.length ? items.map((item) => item.id) : undefined);
  }

  function choosePeriod(next: PeriodId) {
    setPeriod(next);
    if (next === "custom") return;
    const range = periodRange(next);
    list.setFilter("date_from", range.date_from);
    list.setFilter("date_to", range.date_to);
  }

  function setDate(key: "date_from" | "date_to", value: string) {
    setPeriod("custom");
    list.setFilter(key, value);
  }

  function clearFilters() {
    setPeriod("this-month");
    setPartners([]);
    setApps([]);
    list.resetFilters();
  }

  /** Open the per-API breakdown of one row (partner, app, product, day or status). */
  function drillDown(row: ApiUsageRow) {
    if (group === "participant" || group === "app") {
      if (row.participant_id !== null) {
        choosePartners([{ id: row.participant_id, label: row.participant_name ?? "Partner #" + row.participant_id }]);
      }
      if (group === "app" && row.app_id !== null) {
        chooseApps([{ id: row.app_id, label: row.app_name ?? "App #" + row.app_id }]);
      }
      list.setFilter("group_by", "participant_endpoint");
    } else if (group === "product") {
      list.setFilter("product_id", row.product_id ?? undefined);
      list.setFilter("group_by", "participant_endpoint");
    } else if (group === "day" && row.day) {
      setPeriod("custom");
      list.setFilter("date_from", row.day);
      list.setFilter("date_to", row.day);
      list.setFilter("group_by", "participant");
    } else if (group === "status" && row.status_code !== null) {
      list.setFilter("status_code", row.status_code);
      list.setFilter("group_by", "participant");
    }
  }

  async function handleExport(format: "xlsx" | "csv") {
    setExporting(format);
    try {
      const blob = await adminApi.exportApiUsage(list.query, format);
      const range = [list.filters.date_from, list.filters.date_to].filter(Boolean).join("_to_") || "all-time";
      saveBlob(blob, `api-usage-${group}-${range}.${format}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Export failed.", "error");
    } finally {
      setExporting(null);
    }
  }

  const partnerColumn: Column<ApiUsageRow> = {
    key: "participant_name",
    header: "Partner",
    sortable: true,
    render: (row) => (
      <div className="min-w-40">
        <p className="font-medium text-ink">{row.participant_name ?? "Unknown partner"}</p>
        {row.email_id ? <p className="text-xs text-subtle">{row.email_id}</p> : null}
      </div>
    ),
  };
  const endpointColumns: Column<ApiUsageRow>[] = [
    { key: "method", header: "Method", render: (row) => <MethodBadge method={row.method} /> },
    {
      key: "endpoint_url",
      header: "End-Point",
      sortable: true,
      render: (row) => <code className="font-mono text-xs">{row.endpoint_url ?? "—"}</code>,
    },
    { key: "product_name", header: "Product", render: (row) => row.product_name ?? "—" },
  ];
  const identityColumns: Record<ApiUsageGroup, Column<ApiUsageRow>[]> = {
    participant: [
      partnerColumn,
      { key: "country_code", header: "Country", render: (row) => row.country_code ?? "—" },
      { key: "apps_used", header: "Apps", render: (row) => formatNumber(row.apps_used) },
      { key: "endpoints_used", header: "APIs Used", render: (row) => formatNumber(row.endpoints_used) },
    ],
    participant_endpoint: [partnerColumn, ...endpointColumns],
    endpoint: endpointColumns,
    app: [
      { key: "app_name", header: "App", sortable: true, render: (row) => row.app_name ?? "Try-it (no app)" },
      partnerColumn,
      { key: "endpoints_used", header: "APIs Used", render: (row) => formatNumber(row.endpoints_used) },
    ],
    product: [
      { key: "product_name", header: "Product", sortable: true, render: (row) => row.product_name ?? "—" },
      { key: "endpoints_used", header: "APIs Used", render: (row) => formatNumber(row.endpoints_used) },
    ],
    day: [{ key: "day", header: "Date", sortable: true, render: (row) => row.day ?? "—" }],
    status: [
      { key: "status_code", header: "Status Code", sortable: true, render: (row) => <StatusCodeBadge code={row.status_code} /> },
    ],
  };
  const canDrill = group !== "participant_endpoint" && group !== "endpoint";
  const columns: Column<ApiUsageRow>[] = [
    ...identityColumns[group],
    { key: "total_calls", header: "Total Calls", sortable: true, render: (row) => <Count value={row.total_calls} /> },
    { key: "success_calls", header: "Success", sortable: true, render: (row) => <Count value={row.success_calls} /> },
    { key: "client_errors", header: "4xx", sortable: true, render: (row) => <Count value={row.client_errors} tone="client" /> },
    { key: "server_errors", header: "5xx", sortable: true, render: (row) => <Count value={row.server_errors} tone="server" /> },
    { key: "success_rate", header: "Success Rate", render: (row) => <SuccessRate rate={row.success_rate} /> },
    { key: "avg_latency_ms", header: "Avg Latency", sortable: true, render: (row) => formatLatency(row.avg_latency_ms) },
    { key: "last_call", header: "Last Call", sortable: true, render: (row) => formatDateTime(row.last_call) },
    ...(canDrill
      ? [
          {
            key: "actions",
            header: "Actions",
            render: (row: ApiUsageRow) => (
              <IconAction icon={ListTree} label="Show the API-wise breakdown" onClick={() => drillDown(row)} />
            ),
          },
        ]
      : []),
  ];

  const loadingValue = (value: string) => (summaryQuery.isLoading ? "—" : value);

  return (
    <>
      <PageHeader
        title="API Usage & Billing"
        description="How many calls each partner made, to which APIs, and with what result — for billing and monitoring. Successful = HTTP 2xx/3xx; 5xx includes calls that got no answer."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Audit Logs" }, { label: "API Usage & Billing" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "Partner, app or end-point" }}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => handleExport("xlsx")} loading={exporting === "xlsx"}>
              <Download className="h-4 w-4" aria-hidden />
              Excel
            </Button>
            <Button variant="outline" onClick={() => handleExport("csv")} loading={exporting === "csv"}>
              <Download className="h-4 w-4" aria-hidden />
              CSV
            </Button>
          </div>
        }
      />

      <FilterBar>
        <FilterField label="Period" htmlFor="period">
          <Select id="period" value={period} onChange={(event) => choosePeriod(event.target.value as PeriodId)}>
            {PERIODS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="From" htmlFor="date-from">
          <Input id="date-from" type="date" value={filterValue("date_from")} onChange={(event) => setDate("date_from", event.target.value)} />
        </FilterField>
        <FilterField label="To" htmlFor="date-to">
          <Input id="date-to" type="date" value={filterValue("date_to")} onChange={(event) => setDate("date_to", event.target.value)} />
        </FilterField>
        <FilterField label="Partner" htmlFor="partner">
          <SearchableMultiSelect
            id="partner"
            queryKey={["admin", "logs", "api-usage", "lookup", "partners"]}
            fetchPage={adminApi.lookupUsagePartners}
            value={partners}
            onChange={choosePartners}
            placeholder="All partners"
            noun="partners"
            searchPlaceholder="Search name or email"
          />
        </FilterField>
        <FilterField label="App" htmlFor="app">
          <SearchableMultiSelect
            id="app"
            queryKey={["admin", "logs", "api-usage", "lookup", "apps", partnerIds]}
            fetchPage={(search, page) => adminApi.lookupUsageApps(search, page, partnerIds)}
            value={apps}
            onChange={chooseApps}
            placeholder="All apps"
            noun="apps"
            searchPlaceholder="Search app or partner"
          />
        </FilterField>
        <FilterField label="Product" htmlFor="product">
          <Select id="product" value={filterValue("product_id")} onChange={(event) => list.setFilter("product_id", event.target.value)}>
            <option value="">All products</option>
            {(options?.products ?? []).map((product) => (
              <option key={product.product_id} value={product.product_id}>
                {product.name}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="Result" htmlFor="status-class">
          <Select
            id="status-class"
            value={filterValue("status_class")}
            onChange={(event) => {
              list.setFilter("status_code", undefined);
              list.setFilter("status_class", event.target.value);
            }}
          >
            <option value="">All results</option>
            <option value="2xx">Success (2xx)</option>
            <option value="3xx">Redirect (3xx)</option>
            <option value="4xx">Client error (4xx)</option>
            <option value="5xx">Server error / no answer (5xx)</option>
          </Select>
        </FilterField>
        <FilterField label="Source" htmlFor="source">
          <Select id="source" value={filterValue("source")} onChange={(event) => list.setFilter("source", event.target.value)}>
            <option value="">All</option>
            <option value="TRYIT">Try-it</option>
            <option value="DIRECT">Direct (app key)</option>
          </Select>
        </FilterField>
        <FilterField label="Environment" htmlFor="environment">
          <Select id="environment" value={filterValue("environment")} onChange={(event) => list.setFilter("environment", event.target.value)}>
            <option value="">All</option>
            {ENVIRONMENTS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </FilterField>
        <FilterField label="Method" htmlFor="method">
          <Select id="method" value={filterValue("method")} onChange={(event) => list.setFilter("method", event.target.value)}>
            <option value="">All</option>
            {HTTP_METHODS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </FilterField>
        {list.filters.status_code ? (
          <FilterField label="Status code">
            <Button variant="outline" onClick={() => list.setFilter("status_code", undefined)}>
              {String(list.filters.status_code)} ✕
            </Button>
          </FilterField>
        ) : null}
        <Button variant="ghost" onClick={clearFilters}>
          Clear
        </Button>
      </FilterBar>

      {summaryQuery.isError ? (
        <p className="mb-6 text-sm text-destructive">
          {summaryQuery.error instanceof Error ? summaryQuery.error.message : "The usage summary could not be loaded."}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Total Calls" icon={Activity} value={loadingValue(formatNumber(summary?.total_calls))}
          hint={summary?.last_call ? `Last call ${formatDateTime(summary.last_call)}` : undefined} />
        <Tile label="Successful (2xx/3xx)" icon={CheckCircle2} value={loadingValue(formatNumber(summary?.success_calls))}
          hint={summary?.success_rate !== null && summary?.success_rate !== undefined ? `${summary.success_rate}% success rate` : undefined} />
        <Tile label="Client Errors (4xx)" icon={AlertTriangle} value={loadingValue(formatNumber(summary?.client_errors))} />
        <Tile label="Server Errors (5xx)" icon={ServerCrash} value={loadingValue(formatNumber(summary?.server_errors))} />
        <Tile label="Active Partners" icon={UsersRound} value={loadingValue(formatNumber(summary?.partners))}
          hint={summary ? `${formatNumber(summary.apps)} apps` : undefined} />
        <Tile label="APIs Called" icon={Gauge} value={loadingValue(formatNumber(summary?.endpoints))} />
        <Tile label="Avg Latency" icon={Timer} value={loadingValue(formatLatency(summary?.avg_latency_ms))} />
        <Tile label="Direct / Try-it" icon={Activity}
          value={loadingValue(
            `${formatNumber(summary?.by_source.find((item) => item.label === "DIRECT")?.value ?? 0)} / ${formatNumber(
              summary?.by_source.find((item) => item.label === "TRYIT")?.value ?? 0,
            )}`,
          )} />
      </div>

      <div className="mt-6 mb-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Calls per day</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={summary?.by_day ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} tickFormatter={shortDay} minTickGap={24} />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip labelFormatter={(label) => shortDay(String(label))} />
                  <Line type="monotone" dataKey="value" stroke={CHART_LINE} strokeWidth={2} dot={false} name="Calls" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Calls by status code</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary?.by_status_code ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="value" name="Calls" radius={[4, 4, 0, 0]}>
                    {(summary?.by_status_code ?? []).map((item) => (
                      <Cell key={item.label} fill={statusColor(item.label)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mb-4 flex flex-wrap gap-1 border-b border-hairline" role="tablist" aria-label="Group the report">
        {GROUPS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={group === item.id}
            onClick={() => list.setFilter("group_by", item.id)}
            className={
              group === item.id
                ? "-mb-px border-b-2 border-nav-active px-4 py-2.5 text-sm font-semibold text-nav-active"
                : "-mb-px border-b-2 border-transparent px-4 py-2.5 text-sm text-subtle hover:text-ink"
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        rows={usageQuery.data?.rows ?? []}
        rowKey={(row) =>
          [row.participant_id, row.app_id, row.product_id, row.method, row.endpoint_url, row.day, row.status_code].join("|")
        }
        pagination={usageQuery.data?.pagination}
        loading={usageQuery.isLoading}
        noun="rows"
        emptyMessage={usageQuery.isError ? "The usage report could not be loaded." : "No API calls match these filters."}
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />
    </>
  );
}

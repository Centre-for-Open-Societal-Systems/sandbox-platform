"use client";

import * as React from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  Clock,
  Hourglass,
  Layers,
  Rocket,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { MethodBadge } from "@/components/ui/status-badge";
import { adminApi } from "@/lib/services/admin";
import { cn, formatNumber } from "@/lib/utils";
import type { DashboardApiHealth, DashboardCounters, DashboardPeriod } from "@/types/api";

/** What a colour means on this page; a tile, chart or bar about the same thing shares it. */
type Tone = "people" | "calls" | "pending" | "catalogue" | "danger";

const TONE_CHIP: Record<Tone, string> = {
  people: "bg-tone-people-soft text-tone-people",
  calls: "bg-tone-calls-soft text-tone-calls",
  pending: "bg-tone-pending-soft text-tone-pending",
  catalogue: "bg-tone-catalogue-soft text-tone-catalogue",
  danger: "bg-tone-danger-soft text-tone-danger",
};

/** Counter tiles: the soft tone fills the box; text stays in ink so the numbers read cleanly. */
const TONE_TILE: Record<Tone, string> = {
  people: "border-tone-people/20 bg-tone-people-soft hover:border-tone-people",
  calls: "border-tone-calls/20 bg-tone-calls-soft hover:border-tone-calls",
  pending: "border-tone-pending/20 bg-tone-pending-soft hover:border-tone-pending",
  catalogue: "border-tone-catalogue/20 bg-tone-catalogue-soft hover:border-tone-catalogue",
  danger: "border-tone-danger/20 bg-tone-danger-soft hover:border-tone-danger",
};

const TONE_ICON: Record<Tone, string> = {
  people: "text-tone-people",
  calls: "text-tone-calls",
  pending: "text-tone-pending",
  catalogue: "text-tone-catalogue",
  danger: "text-tone-danger",
};

const COUNTER_TILES: {
  key: "total_participants" | "uat_pending" | "prod_pending" | "prod_participants" | "published_products" | "api_calls_month";
  label: string;
  icon: LucideIcon;
  href: string;
  tone: Tone;
}[] = [
  { key: "total_participants", label: "Total Participants", icon: UsersRound, href: "/admin/participants", tone: "people" },
  { key: "uat_pending", label: "UAT Approval Pending", icon: Hourglass, href: "/admin/participants?tab=uat-pending", tone: "pending" },
  { key: "prod_pending", label: "Prod Approval Pending", icon: Clock, href: "/admin/participants?tab=prod-pending", tone: "pending" },
  { key: "prod_participants", label: "Prod Participants", icon: Rocket, href: "/admin/participants?tab=prod", tone: "people" },
  { key: "published_products", label: "Published Products", icon: Layers, href: "/admin/products", tone: "catalogue" },
  { key: "api_calls_month", label: "API Calls This Month", icon: Activity, href: "/admin/logs/api-history", tone: "calls" },
];

const PERIODS: { id: DashboardPeriod; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "week", label: "This week" },
  { id: "month", label: "This month" },
];

const CHART_GRID = "var(--color-hairline)";
const CHART_TICK = { fontSize: 11, fill: "var(--color-subtle)" };
const CHART_LINE = "var(--color-tone-calls)";
const CHART_BAR = "var(--color-tone-people)";

/** "2026-10-16" -> "16 Oct" for the daily traffic axis. */
function shortDay(label: string): string {
  const date = new Date(`${label}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? label
    : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

function rateVariant(rate: number): "success" | "warning" | "danger" {
  if (rate >= 95) return "success";
  if (rate >= 80) return "warning";
  return "danger";
}

const RATE_TONE: Record<ReturnType<typeof rateVariant>, Tone> = {
  success: "people",
  warning: "pending",
  danger: "danger",
};

function SuccessBadge({ rate }: { rate: number | null }) {
  if (rate === null) return <span className="text-subtle">—</span>;
  return <Badge variant={rateVariant(rate)}>{rate}%</Badge>;
}

export default function DashboardPage() {
  const [period, setPeriod] = React.useState<DashboardPeriod>("month");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "dashboard", period],
    queryFn: () => adminApi.dashboard(period),
    // The tiles and the other charts stay on screen while the new period loads.
    placeholderData: keepPreviousData,
  });
  const periodLabel = PERIODS.find((item) => item.id === period)?.label ?? "";
  const trend = data?.api_usage_trend ?? [];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Network activity across participants, the API catalogue and sandbox traffic."
        breadcrumbs={[{ label: "Home" }, { label: "Dashboard" }]}
      />

      {isError ? (
        <Card>
          <CardContent className="flex items-center gap-3 py-8 text-sm text-subtle">
            <AlertCircle className="h-5 w-5 text-destructive" aria-hidden />
            {error instanceof Error ? error.message : "The dashboard could not be loaded."}
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {COUNTER_TILES.map((tile) => (
              <Link
                key={tile.key}
                href={tile.href}
                className={`flex h-full items-start justify-between gap-3 rounded-2xl border px-5 py-4 shadow-sm transition-colors ${TONE_TILE[tile.tone]}`}
              >
                <div>
                  <p className="text-sm text-ink/70">{tile.label}</p>
                  <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">
                    {isLoading ? "—" : formatNumber(data?.counters[tile.key])}
                  </p>
                </div>
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white ${TONE_ICON[tile.tone]}`}>
                  <tile.icon className="h-5 w-5" aria-hidden />
                </span>
              </Link>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-ink">API activity</h2>
              <p className="text-xs text-subtle">Times and days are in UTC.</p>
            </div>
            <div className="inline-flex rounded-lg border border-hairline bg-white p-1" role="group" aria-label="Period">
              {PERIODS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={period === item.id}
                  onClick={() => setPeriod(item.id)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                    period === item.id ? "bg-action text-white" : "text-ink/70 hover:bg-muted",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Sandbox traffic ({periodLabel})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={CHART_TICK}
                        tickLine={false}
                        tickFormatter={shortDay}
                        minTickGap={24}
                      />
                      <YAxis tick={CHART_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip labelFormatter={(label) => shortDay(String(label))} />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={CHART_LINE}
                        strokeWidth={2}
                        dot={trend.length === 1}
                        name="Calls"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Response health ({periodLabel})</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponseHealth health={data?.api_health} loading={isLoading} />
              </CardContent>
            </Card>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Onboarding pipeline</CardTitle>
              </CardHeader>
              <CardContent>
                <OnboardingPipeline counters={data?.counters} loading={isLoading} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Registrations by month</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data?.registrations_trend ?? []}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                      <XAxis dataKey="label" tick={CHART_TICK} tickLine={false} />
                      <YAxis tick={CHART_TICK} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="value" fill={CHART_BAR} radius={[4, 4, 0, 0]} name="Registrations" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-6">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <CardTitle>Most-called end-points ({periodLabel})</CardTitle>
              <Link href="/admin/logs/api-history" className="text-sm font-medium text-brand-bright hover:underline">
                View API history
              </Link>
            </CardHeader>
            <CardContent>
              {data?.top_endpoints?.length ? (
                <div className="table-scroll rounded-xl border border-table-head">
                  <table className="w-full min-w-max text-left text-sm text-ink">
                    <thead className="bg-table-head">
                      <tr>
                        <th className="px-5 py-3 font-semibold">Sr. No.</th>
                        <th className="px-5 py-3 font-semibold">Method</th>
                        <th className="px-5 py-3 font-semibold">End-Point</th>
                        <th className="px-5 py-3 font-semibold">Product</th>
                        <th className="px-5 py-3 text-right font-semibold">Calls</th>
                        <th className="px-5 py-3 text-right font-semibold">Success</th>
                        <th className="px-5 py-3 text-right font-semibold">Avg. Latency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_endpoints.map((item, index) => (
                        <tr key={`${item.method}-${item.endpoint_url}`} className="odd:bg-white even:bg-[#fafafa]">
                          <td className="px-5 py-3.5">{index + 1}.</td>
                          <td className="px-5 py-3.5">
                            <MethodBadge method={item.method} />
                          </td>
                          <td className="px-5 py-3.5">
                            <code className="font-mono text-xs">{item.endpoint_url}</code>
                          </td>
                          <td className="px-5 py-3.5 text-subtle">{item.product_name ?? "—"}</td>
                          <td className="px-5 py-3.5 text-right font-semibold tabular-nums">
                            {formatNumber(item.calls)}
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <SuccessBadge rate={item.success_rate} />
                          </td>
                          <td className="px-5 py-3.5 text-right tabular-nums">{formatLatency(item.avg_latency_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-subtle">
                  {isLoading ? "Loading…" : `No sandbox traffic ${periodLabel.toLowerCase()}.`}
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );
}

/** Success rate, latency and a 2xx / 4xx / 5xx split of sandbox calls. */
function ResponseHealth({ health, loading }: { health?: DashboardApiHealth; loading: boolean }) {
  if (loading) return <p className="text-sm text-subtle">Loading…</p>;
  if (!health?.total_calls) {
    return <p className="text-sm text-subtle">No sandbox calls in this period.</p>;
  }

  const rows = [
    { label: "Successful (2xx/3xx)", value: health.success, bar: "bg-tone-people" },
    { label: "Client errors (4xx)", value: health.client_errors, bar: "bg-tone-pending" },
    { label: "Server errors / no response", value: health.server_errors, bar: "bg-tone-danger" },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-3">
        <Metric label="Calls" value={formatNumber(health.total_calls)} tone="calls" />
        <Metric
          label="Success rate"
          value={health.success_rate === null ? "—" : `${health.success_rate}%`}
          tone={health.success_rate === null ? undefined : RATE_TONE[rateVariant(health.success_rate)]}
        />
        <Metric label="Avg. latency" value={formatLatency(health.avg_latency_ms)} />
      </div>
      <ul className="space-y-3">
        {rows.map((row) => {
          const share = (100 * row.value) / health.total_calls;
          return (
            <li key={row.label} className="text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink/80">{row.label}</span>
                <span className="font-medium tabular-nums">{formatNumber(row.value)}</span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-hairline">
                <div className={`h-full rounded-full ${row.bar}`} style={{ width: `${share}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className={`rounded-xl px-3 py-2.5 ${tone ? TONE_CHIP[tone] : "bg-muted text-subtle"}`}>
      <p className="text-xs">{label}</p>
      <p className="mt-1 text-lg font-semibold text-ink tabular-nums">{value}</p>
    </div>
  );
}

/** How far registered participants have progressed towards production. */
function OnboardingPipeline({ counters, loading }: { counters?: DashboardCounters; loading: boolean }) {
  if (loading || !counters) return <p className="text-sm text-subtle">Loading…</p>;

  const total = counters.total_participants;
  const stages = [
    { label: "Registered", value: total, href: "/admin/participants", bar: "bg-brand-400" },
    { label: "Email verified", value: total - counters.unverified_participants, href: "/admin/participants", bar: "bg-brand-500" },
    { label: "UAT pending", value: counters.uat_pending, href: "/admin/participants?tab=uat-pending", bar: "bg-tone-pending" },
    { label: "UAT approved", value: counters.uat_participants, href: "/admin/participants?tab=uat", bar: "bg-brand-600" },
    { label: "Production approved", value: counters.prod_participants, href: "/admin/participants?tab=prod", bar: "bg-brand-700" },
  ];

  return (
    <div className="space-y-5">
      <ul className="space-y-3">
        {stages.map((stage) => {
          const share = total ? (100 * stage.value) / total : 0;
          return (
            <li key={stage.label} className="text-sm">
              <Link href={stage.href} className="flex items-center justify-between gap-3 hover:text-brand-bright">
                <span className="text-ink/80">{stage.label}</span>
                <span className="font-medium tabular-nums">
                  {formatNumber(stage.value)}
                  <span className="ml-2 text-xs font-normal text-subtle">{Math.round(share)}%</span>
                </span>
              </Link>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-hairline">
                <div className={`h-full rounded-full ${stage.bar}`} style={{ width: `${share}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-2 border-t border-hairline pt-4 text-xs">
        <Badge variant="warning">UAT pending: {formatNumber(counters.uat_pending)}</Badge>
        <Badge variant="warning">Prod pending: {formatNumber(counters.prod_pending)}</Badge>
        <Badge variant="danger">Rejected: {formatNumber(counters.rejected_participants)}</Badge>
        <Badge variant="info">Open tickets: {formatNumber(counters.open_queries)}</Badge>
      </div>
    </div>
  );
}

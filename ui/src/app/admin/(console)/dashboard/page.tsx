"use client";

import { useQuery } from "@tanstack/react-query";
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
import { formatNumber } from "@/lib/utils";
import type { DashboardApiHealth, DashboardCounters } from "@/types/api";

const COUNTER_TILES: {
  key: "total_participants" | "uat_pending" | "prod_pending" | "prod_participants" | "published_products" | "api_calls_month";
  label: string;
  icon: LucideIcon;
  href: string;
}[] = [
  { key: "total_participants", label: "Total Participants", icon: UsersRound, href: "/admin/participants" },
  { key: "uat_pending", label: "UAT Approval Pending", icon: Hourglass, href: "/admin/participants?tab=uat-pending" },
  { key: "prod_pending", label: "Prod Approval Pending", icon: Clock, href: "/admin/participants?tab=prod-pending" },
  { key: "prod_participants", label: "Prod Participants", icon: Rocket, href: "/admin/participants?tab=prod" },
  { key: "published_products", label: "Published Products", icon: Layers, href: "/admin/products" },
  { key: "api_calls_month", label: "API Calls This Month", icon: Activity, href: "/admin/logs/api-history" },
];

const CHART_GRID = "var(--color-hairline)";
const CHART_LINE = "var(--color-brand-500)";
const CHART_BAR = "var(--color-brand-400)";

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

function SuccessBadge({ rate }: { rate: number | null }) {
  if (rate === null) return <span className="text-subtle">—</span>;
  return <Badge variant={rateVariant(rate)}>{rate}%</Badge>;
}

export default function DashboardPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: adminApi.dashboard,
  });
  const days = data?.trend_days ?? 30;

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
                className="flex h-full items-start justify-between gap-3 rounded-2xl border border-[#e4efe4] bg-surface-soft px-5 py-4 transition-colors hover:border-brand-bright"
              >
                <div>
                  <p className="text-sm text-ink/70">{tile.label}</p>
                  <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">
                    {isLoading ? "—" : formatNumber(data?.counters[tile.key])}
                  </p>
                </div>
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-brand-bright">
                  <tile.icon className="h-5 w-5" aria-hidden />
                </span>
              </Link>
            ))}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Sandbox traffic ({days} days)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data?.api_usage_trend ?? []}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={{ fontSize: 11 }}
                        tickLine={false}
                        tickFormatter={shortDay}
                        minTickGap={24}
                      />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip labelFormatter={(label) => shortDay(String(label))} />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={CHART_LINE}
                        strokeWidth={2}
                        dot={false}
                        name="Calls"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Response health ({days} days)</CardTitle>
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
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
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
              <CardTitle>Most-called end-points ({days} days)</CardTitle>
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
                  {isLoading ? "Loading…" : `No sandbox traffic in the last ${days} days.`}
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
    { label: "Successful (2xx/3xx)", value: health.success, bar: "bg-brand-500" },
    { label: "Client errors (4xx)", value: health.client_errors, bar: "bg-[#E0A53A]" },
    { label: "Server errors / no response", value: health.server_errors, bar: "bg-[#DA131A]" },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-3">
        <Metric label="Calls" value={formatNumber(health.total_calls)} />
        <Metric label="Success rate" value={health.success_rate === null ? "—" : `${health.success_rate}%`} />
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-surface-soft px-3 py-2.5">
      <p className="text-xs text-subtle">{label}</p>
      <p className="mt-1 text-lg font-semibold text-ink tabular-nums">{value}</p>
    </div>
  );
}

/** How far registered participants have progressed towards production. */
function OnboardingPipeline({ counters, loading }: { counters?: DashboardCounters; loading: boolean }) {
  if (loading || !counters) return <p className="text-sm text-subtle">Loading…</p>;

  const total = counters.total_participants;
  const stages = [
    { label: "Registered", value: total, href: "/admin/participants" },
    { label: "Email verified", value: total - counters.unverified_participants, href: "/admin/participants" },
    { label: "Sandbox access", value: counters.sandbox_participants, href: "/admin/participants" },
    { label: "UAT approved", value: counters.uat_participants, href: "/admin/participants?tab=uat" },
    { label: "Production approved", value: counters.prod_participants, href: "/admin/participants?tab=prod" },
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
                <div className="h-full rounded-full bg-brand-500" style={{ width: `${share}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-2 border-t border-hairline pt-4 text-xs">
        <Badge variant="warning">UAT pending: {formatNumber(counters.uat_pending)}</Badge>
        <Badge variant="warning">Prod pending: {formatNumber(counters.prod_pending)}</Badge>
        <Badge variant="danger">Rejected: {formatNumber(counters.rejected_participants)}</Badge>
        <Badge variant="info">Open queries: {formatNumber(counters.open_queries)}</Badge>
      </div>
    </div>
  );
}

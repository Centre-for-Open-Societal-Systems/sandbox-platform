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

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { adminApi } from "@/lib/services/admin";
import { formatNumber } from "@/lib/utils";

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

export default function DashboardPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: adminApi.dashboard,
  });

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

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sandbox traffic (30 days)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data?.api_usage_trend ?? []}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                      <Tooltip />
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

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Most-called endpoints</CardTitle>
              </CardHeader>
              <CardContent>
                {data?.top_endpoints?.length ? (
                  <ul className="space-y-3">
                    {data.top_endpoints.map((item) => (
                      <li key={item.label} className="flex items-center justify-between gap-4 text-sm">
                        <code className="truncate font-mono text-xs">{item.label}</code>
                        <span className="font-medium">{formatNumber(item.value)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-subtle">No sandbox traffic recorded yet.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Participants by region</CardTitle>
              </CardHeader>
              <CardContent>
                {data?.participants_by_area?.length ? (
                  <ul className="space-y-3">
                    {data.participants_by_area.map((item) => (
                      <li key={item.label} className="flex items-center justify-between gap-4 text-sm">
                        <span className="truncate">{item.label}</span>
                        <span className="font-medium">{formatNumber(item.value)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-subtle">
                    No participants have recorded a region yet.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

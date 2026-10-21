"use client";

import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  Check,
  CircleDot,
  Layers,
  Lock,
  ScrollText,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { ProductionRequestDialog } from "@/components/portal/production-request-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { participantApi } from "@/lib/services/participant";
import { participantSession } from "@/lib/session";
import { cn, formatDate, formatNumber } from "@/lib/utils";
import type { PromotionRequest } from "@/types/api";

const REQUEST_STATUS: Record<number, { label: string; variant: "warning" | "success" | "danger" }> = {
  0: { label: "Under review", variant: "warning" },
  1: { label: "Approved", variant: "success" },
  2: { label: "Rejected", variant: "danger" },
};

type AccessState = "active" | "pending" | "rejected" | "locked" | "available";

const ACCESS_BADGE: Record<AccessState, { label: string; variant: "success" | "warning" | "danger" | "neutral" | "info" }> = {
  active: { label: "Active", variant: "success" },
  pending: { label: "Under review", variant: "warning" },
  rejected: { label: "Rejected", variant: "danger" },
  locked: { label: "Locked", variant: "neutral" },
  available: { label: "Not requested", variant: "info" },
};

function latestRequest(requests: PromotionRequest[], environment: string) {
  return requests
    .filter((request) => request.target_environment === environment)
    .sort((a, b) => (b.added_date ?? "").localeCompare(a.added_date ?? ""))[0];
}

export default function ParticipantDashboard() {
  const queryClient = useQueryClient();
  const session = participantSession.get();
  const { notify } = useToast();

  const dashboardQuery = useQuery({ queryKey: ["participant", "dashboard"], queryFn: participantApi.dashboard });
  const requestsQuery = useQuery({ queryKey: ["user", "promotion-requests"], queryFn: participantApi.promotionRequests });

  const data = dashboardQuery.data;
  const requests = requestsQuery.data ?? [];
  const environments = data?.environments ?? session?.environments ?? [];
  const callsTotal = data?.api_calls_period ?? 0;
  const profileComplete = data?.is_profile_complete ?? Boolean(session?.is_profile_complete);

  function accessState(environment: "SANDBOX" | "UAT" | "PRODUCTION"): AccessState {
    if (environments.includes(environment)) {
      return "active";
    }
    const previous = environment === "PRODUCTION" ? "UAT" : "SANDBOX";
    if (!environments.includes(previous)) {
      return "locked";
    }
    const request = latestRequest(requests, environment);
    if (request?.status === 0) {
      return "pending";
    }
    if (request?.status === 2) {
      return "rejected";
    }
    return "available";
  }

  const [productionFormOpen, setProductionFormOpen] = React.useState(false);

  const requestPromotion = useMutation({
    /** UAT is one click; production sends the Move to Production form. */
    mutationFn: ({ formData }: { environment: string; formData: FormData }) =>
      participantApi.requestPromotion(formData),
    // A toast, not an inline notice: the button sits well below the top of the page.
    onSuccess: (_data, { environment }) => {
      notify(`${environment} access request submitted. You will be emailed once it is reviewed.`, "success");
      setProductionFormOpen(false);
      queryClient.invalidateQueries({ queryKey: ["user", "promotion-requests"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function requestAccess(environment: string) {
    if (environment === "PRODUCTION") {
      setProductionFormOpen(true);
      return;
    }
    const formData = new FormData();
    formData.append("target_environment", environment);
    requestPromotion.mutate({ environment, formData });
  }

  const steps = [
    { label: "Verify your email", done: true, href: undefined },
    { label: "Complete your organisation profile", done: Boolean(session?.is_profile_complete), href: "/participant/profile" },
    { label: "Make your first sandbox call", done: callsTotal > 0, href: "/participant/catalog" },
    { label: "Get UAT access", done: environments.includes("UAT"), href: undefined },
    { label: "Go live in production", done: environments.includes("PRODUCTION"), href: undefined },
  ];
  const completed = steps.filter((step) => step.done).length;
  const currentStep = steps.findIndex((step) => !step.done);

  return (
    <div className="flex flex-col gap-6">
      {/* ------------------------------------------------------------ welcome */}
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="Dashboard"
        title={`Welcome back, ${session?.display_name ?? "Developer"}`}
        description={`${session?.company_name ?? "Your organisation"} · ${environments.length ? environments.join(" · ") : "No environment yet"}`}
        image="/assets/home/hero-tea-farm.webp"
      >
        <Link
          href="/participant/catalog"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-gold px-5 py-2.5 text-sm font-semibold text-[#0b2a1a] shadow-lg transition hover:brightness-110"
        >
          <Layers className="h-4 w-4" aria-hidden />
          Explore APIs
        </Link>
        <Link
          href="/participant/api-history"
          className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-5 py-2.5 text-sm font-semibold text-white ring-1 ring-white/40 backdrop-blur transition hover:bg-white/20"
        >
          <ScrollText className="h-4 w-4" aria-hidden />
          API History
        </Link>
      </PageBanner>

      {/* -------------------------------------------------------------- stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={Activity} label="Calls today" value={formatNumber(data?.api_calls_today)} loading={dashboardQuery.isLoading} />
        <StatTile icon={CalendarDays} label="Calls this month" value={formatNumber(data?.api_calls_month)} loading={dashboardQuery.isLoading} />
        <StatTile icon={TrendingUp} label="Calls in 30 days" value={formatNumber(data?.api_calls_period)} loading={dashboardQuery.isLoading} />
        <StatTile icon={Layers} label="Environments" value={String(environments.length)} hint={environments.join(", ") || "None yet"} loading={false} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* ------------------------------------------------- getting started */}
        <Panel
          title="Getting started"
          action={<span className="text-sm text-subtle">{completed} of {steps.length} done</span>}
        >
          <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-soft">
            <div className="h-full rounded-full bg-nav-active transition-all" style={{ width: `${(completed / steps.length) * 100}%` }} />
          </div>
          <ol className="flex flex-col gap-1">
            {steps.map((step, index) => {
              const isCurrent = index === currentStep;
              return (
                <li
                  key={step.label}
                  className={cn("flex items-center gap-3 rounded-xl px-3 py-2.5", isCurrent && "bg-surface-soft")}
                >
                  <span
                    className={cn(
                      "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                      step.done ? "bg-nav-active text-white" : isCurrent ? "border-2 border-nav-active text-nav-active" : "border border-hairline text-subtle",
                    )}
                  >
                    {step.done ? <Check className="h-4 w-4" aria-hidden /> : index + 1}
                  </span>
                  <span className={cn("flex-1 text-sm", step.done ? "text-subtle line-through" : "font-medium text-ink")}>
                    {step.label}
                  </span>
                  {isCurrent && step.href ? (
                    <Link href={step.href} className="inline-flex items-center gap-1 text-sm font-semibold text-brand-bright hover:underline">
                      Start
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </Link>
                  ) : null}
                </li>
              );
            })}
          </ol>
        </Panel>

        {/* ------------------------------------------------ environment access */}
        <Panel title="Environment access">
          <ul className="flex flex-col gap-3">
            {(["SANDBOX", "UAT", "PRODUCTION"] as const).map((environment) => {
              const state = accessState(environment);
              const badge = ACCESS_BADGE[state];
              const request = latestRequest(requests, environment);
              return (
                <li key={environment} className="rounded-xl border border-hairline bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      {state === "locked" ? (
                        <Lock className="h-4 w-4 text-subtle" aria-hidden />
                      ) : (
                        <CircleDot className={cn("h-4 w-4", state === "active" ? "text-nav-active" : "text-subtle")} aria-hidden />
                      )}
                      <span className="font-semibold text-ink">{environment}</span>
                    </div>
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </div>
                  {state === "rejected" && request?.rejection_reason ? (
                    <p className="mt-2 text-xs text-red-700">Reason: {request.rejection_reason}</p>
                  ) : null}
                  {state === "locked" ? (
                    <p className="mt-2 text-xs text-subtle">
                      Available after {environment === "PRODUCTION" ? "UAT" : "sandbox"} access.
                    </p>
                  ) : null}
                  {(state === "available" || state === "rejected") && environment === "UAT" && !profileComplete ? (
                    <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
                      <p className="text-xs text-amber-800">Complete your organisation profile before requesting UAT access.</p>
                      <Link
                        href="/participant/profile"
                        className="mt-1.5 inline-flex items-center gap-1 text-sm font-semibold text-brand-bright hover:underline"
                      >
                        Complete profile
                        <ArrowRight className="h-4 w-4" aria-hidden />
                      </Link>
                    </div>
                  ) : state === "available" || state === "rejected" ? (
                    <Button
                      size="sm"
                      className="mt-3 w-full"
                      loading={requestPromotion.isPending && requestPromotion.variables?.environment === environment}
                      onClick={() => requestAccess(environment)}
                    >
                      {state === "rejected" ? "Re-apply" : `Request ${environment} access`}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* ---------------------------------------------------------- usage */}
        <Panel title="Your usage (last 30 days)">
          <div className="h-64">
            {callsTotal === 0 && !dashboardQuery.isLoading ? (
              <EmptyState
                text="No calls yet. Try an API from the catalogue and your traffic will show here."
                href="/participant/catalog"
                cta="Try an API"
              />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data?.usage_trend ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-hairline)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="var(--color-brand-bright)" strokeWidth={2} dot={false} name="Calls" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Panel>

        {/* ------------------------------------------------------- requests */}
        <Panel title="Access requests">
          {requests.length ? (
            <ul className="flex flex-col divide-y divide-hairline">
              {requests.map((request) => {
                const state = REQUEST_STATUS[request.status] ?? REQUEST_STATUS[0]!;
                return (
                  <li key={request.request_id} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
                    <div>
                      <p className="text-sm font-semibold text-ink">{request.target_environment}</p>
                      <p className="text-xs text-subtle">Requested {formatDate(request.added_date)}</p>
                    </div>
                    <Badge variant={state.variant}>{state.label}</Badge>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-subtle">No access requests raised yet.</p>
          )}
        </Panel>
      </div>

      {/* ------------------------------------------------------ top endpoints */}
      <Panel title="Most-called end-points">
        {data?.top_endpoints?.length ? (
          <div className="table-scroll rounded-xl border border-table-head">
            <table className="w-full min-w-max text-left text-sm text-ink">
              <thead className="bg-table-head">
                <tr>
                  <th className="px-5 py-3 font-semibold">Sr. No.</th>
                  <th className="px-5 py-3 font-semibold">End-Point</th>
                  <th className="px-5 py-3 text-right font-semibold">Calls</th>
                </tr>
              </thead>
              <tbody>
                {data.top_endpoints.map((item, index) => (
                  <tr key={item.label} className="odd:bg-white even:bg-[#fafafa]">
                    <td className="px-5 py-3.5">{index + 1}.</td>
                    <td className="px-5 py-3.5">
                      <code className="font-mono text-xs">{item.label}</code>
                    </td>
                    <td className="px-5 py-3.5 text-right font-semibold tabular-nums">{formatNumber(item.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-subtle">You have not called any end-points yet.</p>
        )}
      </Panel>

      <ProductionRequestDialog
        open={productionFormOpen}
        onOpenChange={setProductionFormOpen}
        submitting={requestPromotion.isPending}
        onSubmit={(formData) => requestPromotion.mutate({ environment: "PRODUCTION", formData })}
      />
    </div>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  hint,
  loading,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  loading: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-2xl border border-[#e4efe4] bg-white px-5 py-4">
      <div className="min-w-0">
        <p className="text-sm text-ink/70">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-ink tabular-nums">{loading ? "—" : value}</p>
        {hint ? <p className="mt-0.5 truncate text-xs text-subtle">{hint}</p> : null}
      </div>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface-soft text-brand-bright">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
    </div>
  );
}

function Panel({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-hairline bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-nav-active">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyState({ text, href, cta }: { text: string; href: string; cta: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-hairline text-center">
      <p className="max-w-sm text-sm text-subtle">{text}</p>
      <Button asChild size="sm" variant="outline">
        <Link href={href}>{cta}</Link>
      </Button>
    </div>
  );
}

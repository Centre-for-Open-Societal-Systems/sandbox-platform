import * as React from "react";
import Link from "next/link";
import { FlaskConical, Layers, Leaf, ShieldCheck } from "lucide-react";

import { config } from "@/lib/config";

const HIGHLIGHTS = [
  { Icon: Layers, label: "Open agriculture APIs" },
  { Icon: FlaskConical, label: "Safe sandbox testing" },
  { Icon: ShieldCheck, label: "Sandbox → UAT → Production" },
] as const;

/** Field styling mirrors the OAS registry login: hairline border, green focus ring. */
export const FIELD_BASE =
  "w-full rounded-lg border border-hairline bg-white py-2.5 text-sm text-ink transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none";
export const FIELD_LABEL = "text-sm font-semibold text-slate-700";
export const FIELD_ICON =
  "pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground";
export const SUBMIT_BUTTON =
  "mt-1 inline-flex items-center justify-center gap-2 rounded-lg bg-linear-to-b from-brand-bright to-brand-deep py-3.5 text-base font-semibold text-white transition-[filter] hover:brightness-110 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60";

/**
 * Two-panel layout of the sign-in screens, following the OAS registry portal
 * login: brand photo panel on the left, the card passed as children on the right.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-2">
      {/* ---------- Brand panel ---------- */}
      <aside className="relative flex min-h-90 flex-col overflow-hidden bg-[url('/assets/login-panel.png')] bg-cover bg-center p-9 text-white lg:p-11">
        <div
          aria-hidden
          className="absolute inset-0 bg-linear-to-b from-brand-deep/40 via-brand-deep/30 to-brand-deep/80"
        />

        <div className="relative z-10 flex h-full flex-col">
          <Link
            href="/"
            className="flex items-center gap-2 self-start rounded-xl bg-black/25 px-4 py-2 backdrop-blur-sm"
          >
            <Leaf className="h-6 w-6 text-brand-gold" aria-hidden />
            <span className="text-lg font-semibold">{config.siteName}</span>
          </Link>

          <div className="mt-auto">
            <h1 className="text-[clamp(2.2rem,4.4vw,3.6rem)] font-bold leading-[1.05] tracking-[-1px] [text-shadow:0_2px_12px_rgba(0,0,0,0.35)]">
              Empowering Agriculture, Digitally.
            </h1>
            <p className="mt-4 max-w-130 text-[1.02rem] leading-relaxed text-white/90">
              Build on the open agriculture network. Explore the API catalogue, try every
              end-point in the sandbox, then move to production.
            </p>

            <ul className="mt-8 flex list-none flex-wrap gap-3">
              {HIGHLIGHTS.map(({ Icon, label }) => (
                <li
                  key={label}
                  className="flex items-center gap-2 rounded-xl border border-white/15 bg-black/30 px-4 py-2.5 text-[0.8rem] font-medium backdrop-blur-sm"
                >
                  <Icon className="h-4 w-4 shrink-0 text-brand-gold" aria-hidden />
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </aside>

      {/* ---------- Form panel ---------- */}
      <main className="flex items-center justify-center bg-surface-soft p-6 sm:p-10">
        <div className="w-full max-w-110 rounded-2xl bg-white p-8 shadow-xl ring-1 ring-black/5 sm:p-10">
          {children}
        </div>
      </main>
    </div>
  );
}

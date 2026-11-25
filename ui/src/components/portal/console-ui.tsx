"use client";

import * as React from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

/** Building blocks shared by the API documentation page and the sandbox test page. */

export const CODE_BLOCK =
  "overflow-auto rounded-xl bg-[#282a36] p-4 font-mono text-xs leading-relaxed text-[#f8f8f2]";
export const FIELD =
  "w-full rounded-lg border border-hairline bg-white px-3 py-2 font-mono text-xs text-ink placeholder:text-slate-400 focus:border-brand-bright focus:outline-none";

export function Panel({
  title,
  tabs,
  action,
  children,
  className,
}: {
  title: React.ReactNode;
  tabs?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-2xl border border-hairline bg-white shadow-sm", className)}>
      <div className="border-b border-hairline px-5 pt-4">
        <div className={cn("flex items-center justify-between gap-3", tabs ? "pb-2" : "pb-4")}>
          <h2 className="text-base font-semibold text-nav-active">{title}</h2>
          {action}
        </div>
        {tabs ? <div className="min-w-0">{tabs}</div> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Tabs({
  value,
  onChange,
  items,
}: {
  value: string;
  onChange: (value: string) => void;
  items: { id: string; label: string; count?: number }[];
}) {
  return (
    <div className="scrollbar-none flex gap-1 overflow-x-auto" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={value === item.id}
          onClick={() => onChange(item.id)}
          className={cn(
            "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-2.5 pb-3 text-sm transition-colors",
            value === item.id
              ? "border-nav-active font-semibold text-nav-active"
              : "border-transparent text-slate-600 hover:text-ink",
          )}
        >
          {item.label}
          {item.count ? (
            <span className="rounded-full bg-surface-soft px-1.5 text-[0.7rem] font-semibold text-nav-active">
              {item.count}
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string | undefined; label?: string }) {
  const [copied, setCopied] = React.useState(false);

  async function copy() {
    if (!text) {
      return;
    }
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      type="button"
      onClick={copy}
      disabled={!text}
      className="inline-flex items-center gap-1.5 rounded-lg border border-hairline px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-surface-soft disabled:opacity-50"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-brand-bright" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
      {copied ? "Copied" : label}
    </button>
  );
}

/**
 * Full-width photo banner across the top of the product, documentation and
 * sandbox pages (the reference sandbox's green title band). The negative
 * margins cancel the portal's page padding so it runs edge to edge.
 */
export function ApiBanner({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="relative -mx-4 -mt-8 mb-8 overflow-hidden text-white sm:-mx-6 2xl:-mx-10">
      <div aria-hidden className="absolute inset-0 bg-[url('/assets/home/tea-rows.webp')] bg-cover bg-center" />
      <div aria-hidden className="absolute inset-0 bg-linear-to-b from-[#0b2a1a]/80 via-[#0b2a1a]/70 to-[#0b2a1a]/85" />
      <div className="relative mx-auto flex max-w-4xl flex-col items-center px-4 py-12 text-center sm:py-14">
        {eyebrow ? (
          <p className="text-xs font-semibold tracking-[0.2em] text-white/80 uppercase">{eyebrow}</p>
        ) : null}
        <h1 className="mt-2 text-3xl font-bold break-words text-brand-gold sm:text-[2.6rem] sm:leading-tight">{title}</h1>
        {children}
      </div>
    </div>
  );
}

export function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

/** Drop blank inputs so optional parameters are omitted rather than sent empty. */
export function stripEmpty(values: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim() !== ""));
}

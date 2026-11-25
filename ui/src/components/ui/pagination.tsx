"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

import { PAGE_SIZE_OPTIONS } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { Pagination as PaginationMeta } from "@/types/api";

const PAGER_BTN =
  "inline-flex h-9 min-w-9 items-center justify-center rounded-lg border border-hairline bg-white px-2 text-sm text-slate-600 transition-colors hover:bg-surface-soft disabled:opacity-40 disabled:hover:bg-white";
const PAGER_ACTIVE = "border-brand-deep bg-brand-deep font-semibold text-white hover:bg-brand-deep";
const PAGER_SELECT =
  "rounded-lg border border-hairline bg-white px-2 py-1.5 text-sm text-ink focus:border-brand-bright focus:outline-none";

/** Page numbers to show: first, last, and the neighbours of the current page. */
export function pageStrip(current: number, total: number): (number | "gap")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }
  const wanted = new Set([1, total]);
  for (let page = current - 1; page <= current + 1; page++) {
    if (page >= 1 && page <= total) {
      wanted.add(page);
    }
  }
  const out: (number | "gap")[] = [];
  let previous = 0;
  for (const page of [...wanted].sort((a, b) => a - b)) {
    if (previous && page - previous > 1) {
      out.push("gap");
    }
    out.push(page);
    previous = page;
  }
  return out;
}

interface PaginationProps {
  meta: PaginationMeta;
  /** Plural noun for the summary line, e.g. "participants". */
  noun?: string;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (limit: number) => void;
}

export function Pagination({ meta, noun = "records", onPageChange, onPageSizeChange }: PaginationProps) {
  const total = Math.max(meta.total_pages, 1);
  const current = Math.min(Math.max(meta.page, 1), total);
  const first = (current - 1) * meta.limit + 1;
  const last = Math.min(current * meta.limit, meta.total);

  function go(page: number) {
    if (page >= 1 && page <= total && page !== current) {
      onPageChange?.(page);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-subtle" aria-live="polite">
        {meta.total === 0
          ? `No ${noun} found`
          : `Showing ${first}–${last} of ${meta.total} ${noun} · page ${current} of ${total}`}
      </p>

      <div className="flex flex-col items-center gap-3 md:grid md:grid-cols-[1fr_auto_1fr]">
        <div className="justify-self-start">
          {onPageSizeChange ? (
            <label className="flex items-center gap-2 text-sm text-subtle">
              Rows
              <select
                className={PAGER_SELECT}
                value={meta.limit}
                onChange={(event) => onPageSizeChange(Number(event.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
        </div>

        <nav className="flex items-center gap-2" aria-label="Pagination">
          <button type="button" className={PAGER_BTN} disabled={current <= 1} onClick={() => go(1)} aria-label="First page">
            <ChevronsLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            className={PAGER_BTN}
            disabled={current <= 1}
            onClick={() => go(current - 1)}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          {pageStrip(current, total).map((page, index) =>
            page === "gap" ? (
              <span key={`gap-${index}`} className="px-1 text-subtle" aria-hidden>
                …
              </span>
            ) : (
              <button
                key={page}
                type="button"
                className={cn(PAGER_BTN, page === current && PAGER_ACTIVE)}
                aria-current={page === current ? "page" : undefined}
                onClick={() => go(page)}
              >
                {page}
              </button>
            ),
          )}
          <button
            type="button"
            className={PAGER_BTN}
            disabled={current >= total}
            onClick={() => go(current + 1)}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            className={PAGER_BTN}
            disabled={current >= total}
            onClick={() => go(total)}
            aria-label="Last page"
          >
            <ChevronsRight className="h-4 w-4" aria-hidden />
          </button>
        </nav>

        <label className="flex items-center gap-2 justify-self-end text-sm text-subtle">
          Page
          <select
            className={cn(PAGER_SELECT, "w-20")}
            value={current}
            onChange={(event) => go(Number(event.target.value))}
            aria-label="Jump to page"
          >
            {Array.from({ length: total }, (_, index) => index + 1).map((page) => (
              <option key={page} value={page}>
                {page}
              </option>
            ))}
          </select>
          of {total}
        </label>
      </div>
    </div>
  );
}

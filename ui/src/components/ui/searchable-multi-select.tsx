"use client";

import * as React from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Check, ChevronDown, Loader2, Search, X } from "lucide-react";

import { cn } from "@/lib/utils";

export interface LookupItem {
  id: number;
  label: string;
  /** Second line, e.g. the partner's email. */
  hint?: string | null;
}

export interface LookupPage {
  rows: LookupItem[];
  page: number;
  has_more: boolean;
}

interface SearchableMultiSelectProps {
  id?: string;
  /** Cache key for the options; include anything `fetchPage` depends on. */
  queryKey: readonly unknown[];
  /** One page of options for a search term; the server does search and paging. */
  fetchPage: (search: string, page: number) => Promise<LookupPage>;
  value: LookupItem[];
  onChange: (items: LookupItem[]) => void;
  /** Shown when nothing is chosen, e.g. "All partners". */
  placeholder: string;
  /** Plural noun for "3 partners selected". */
  noun: string;
  searchPlaceholder?: string;
  className?: string;
}

const SEARCH_DELAY_MS = 300;

/**
 * Multi-select dropdown for long lists (thousands of partners or apps).
 *
 * Nothing is loaded until it opens; then options come from the server one page
 * at a time, filtered by the search box, and the next page loads as the list
 * is scrolled to the end. Chosen items keep their labels in `value`, so they
 * display even when they are not on a loaded page.
 */
export function SearchableMultiSelect({
  id,
  queryKey,
  fetchPage,
  value,
  onChange,
  placeholder,
  noun,
  searchPlaceholder = "Type to search…",
  className,
}: SearchableMultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [searchInput, setSearchInput] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const listRef = React.useRef<HTMLUListElement>(null);
  const sentinelRef = React.useRef<HTMLLIElement>(null);
  const listboxId = `${id ?? "lookup"}-listbox`;

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setActiveIndex(-1);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const options = useInfiniteQuery({
    queryKey: [...queryKey, search],
    queryFn: ({ pageParam }) => fetchPage(search, pageParam),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    enabled: open,
    staleTime: 30_000,
  });
  const items = React.useMemo(() => options.data?.pages.flatMap((page) => page.rows) ?? [], [options.data]);
  const selectedIds = React.useMemo(() => new Set(value.map((item) => item.id)), [value]);

  // Close on a click outside.
  React.useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  // Load the next page when the end of the list scrolls into view.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = options;
  React.useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!open || !sentinel || !hasNextPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !isFetchingNextPage) void fetchNextPage();
      },
      { root: listRef.current, rootMargin: "80px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [open, hasNextPage, isFetchingNextPage, fetchNextPage, items.length]);

  function toggle(item: LookupItem) {
    onChange(selectedIds.has(item.id) ? value.filter((chosen) => chosen.id !== item.id) : [...value, item]);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) setOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next = Math.min(Math.max(activeIndex + step, 0), items.length - 1);
      setActiveIndex(next);
      listRef.current?.querySelector<HTMLElement>(`[data-index="${next}"]`)?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && open && items[activeIndex]) {
      event.preventDefault();
      toggle(items[activeIndex]);
    }
  }

  const summary =
    value.length === 0 ? placeholder : value.length === 1 ? value[0]!.label : `${value.length} ${noun} selected`;

  return (
    <div ref={rootRef} className={cn("relative w-full", className)} onKeyDown={onKeyDown}>
      <button
        id={id}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "flex h-10 w-full items-center gap-2 rounded-[10px] border border-hairline bg-white pl-4 text-left text-[0.92rem]",
          "focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none",
          value.length > 0 ? "pr-14" : "pr-8",
          open && "border-brand-bright",
        )}
      >
        <span className={cn("min-w-0 flex-1 truncate", value.length === 0 ? "text-ink/80" : "font-medium text-ink")}>
          {summary}
        </span>
      </button>
      <ChevronDown
        className={cn(
          "pointer-events-none absolute top-5 right-2.5 h-4 w-4 -translate-y-1/2 text-subtle transition-transform",
          open && "rotate-180",
        )}
        aria-hidden
      />
      {value.length > 0 ? (
        <button
          type="button"
          aria-label={`Clear selected ${noun}`}
          onClick={() => onChange([])}
          className="absolute top-5 right-8 -translate-y-1/2 rounded p-0.5 text-subtle hover:bg-slate-100 hover:text-ink"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      ) : null}

      {open ? (
        <div className="absolute top-full left-0 z-50 mt-1 w-full min-w-72 rounded-xl border border-hairline bg-white shadow-lg">
          <div className="relative border-b border-hairline p-2">
            <Search className="pointer-events-none absolute top-1/2 left-4.5 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
            <input
              autoFocus
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              aria-controls={listboxId}
              className="h-9 w-full rounded-lg border border-hairline pr-3 pl-8 text-sm focus:border-brand-bright focus:outline-none"
            />
          </div>

          {value.length > 0 ? (
            <div className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto border-b border-hairline p-2">
              {value.map((item) => (
                <span
                  key={item.id}
                  className="inline-flex max-w-full items-center gap-1 rounded-full bg-brand-100 py-0.5 pr-1 pl-2.5 text-xs font-medium text-brand-700"
                >
                  <span className="truncate">{item.label}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${item.label}`}
                    onClick={() => toggle(item)}
                    className="rounded-full p-0.5 hover:bg-brand-200"
                  >
                    <X className="h-3 w-3" aria-hidden />
                  </button>
                </span>
              ))}
            </div>
          ) : null}

          <ul
            ref={listRef}
            id={listboxId}
            role="listbox"
            aria-multiselectable
            className="max-h-64 overflow-y-auto py-1"
          >
            {items.map((item, index) => {
              const selected = selectedIds.has(item.id);
              return (
                <li
                  key={item.id}
                  role="option"
                  aria-selected={selected}
                  data-index={index}
                  onClick={() => toggle(item)}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={cn(
                    "flex cursor-pointer items-center gap-2.5 px-3 py-2 text-sm",
                    index === activeIndex ? "bg-surface-soft" : "hover:bg-surface-soft",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                      selected ? "border-brand-bright bg-brand-bright text-white" : "border-slate-300 bg-white",
                    )}
                    aria-hidden
                  >
                    {selected ? <Check className="h-3 w-3" /> : null}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-ink">{item.label}</span>
                    {item.hint ? <span className="block truncate text-xs text-subtle">{item.hint}</span> : null}
                  </span>
                </li>
              );
            })}
            {options.isLoading || isFetchingNextPage ? (
              <li className="flex items-center gap-2 px-3 py-2 text-sm text-subtle">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </li>
            ) : null}
            {options.isError ? (
              <li className="px-3 py-2 text-sm text-destructive">Could not load the list.</li>
            ) : null}
            {!options.isLoading && !options.isError && items.length === 0 ? (
              <li className="px-3 py-2 text-sm text-subtle">No {noun} found.</li>
            ) : null}
            {hasNextPage ? <li ref={sentinelRef} aria-hidden className="h-1" /> : null}
          </ul>

          <div className="flex items-center justify-between border-t border-hairline px-3 py-2 text-xs text-subtle">
            <span>{value.length} selected</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md px-2 py-1 font-semibold text-brand-bright hover:bg-surface-soft"
            >
              Done
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

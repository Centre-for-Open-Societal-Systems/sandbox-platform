"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, Layers, Loader2, Search } from "lucide-react";

import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { catalogApi } from "@/lib/services/catalog";
import { cn } from "@/lib/utils";

const METHOD_COLOURS: Record<string, string> = {
  GET: "text-[#1A5FA8]",
  POST: "text-[#2E7D32]",
  PUT: "text-[#B26A00]",
  PATCH: "text-[#B26A00]",
  DELETE: "text-[#DA131A]",
};

interface ApiExplorerNavProps {
  activeEndpointId: number;
  /** Product of the open end-point, so its group starts expanded. */
  activeProductId?: number | null;
  /** Where an end-point link goes (documentation page by default). */
  hrefFor?: (productId: number, endpointId: number) => string;
  /** "Back" link shown above the search, as in the reference sidebar. */
  back?: { href: string; label: string };
}

const DOCS_HREF = (productId: number, endpointId: number) =>
  `/participant/product/${productId}/endpoint/${endpointId}`;

/**
 * Left-hand API menu of the try-it console: every published product with its
 * end-points, so a participant can move between APIs without going back to
 * the catalogue (as the reference sandbox's API reference page does).
 */
export function ApiExplorerNav({ activeEndpointId, activeProductId, hrefFor = DOCS_HREF, back }: ApiExplorerNavProps) {
  const [search, setSearch] = React.useState("");
  // null = follow the open end-point; otherwise the user's own toggles.
  const [openGroups, setOpenGroups] = React.useState<Set<number> | null>(null);

  // One request for the whole menu instead of one per product; kept for five
  // minutes on the client and revalidated with an ETag after that.
  const menuQuery = useQuery({
    queryKey: ["participant", "catalog", "menu"],
    queryFn: catalogApi.portalMenu,
    staleTime: CATALOG_STALE_MS,
  });
  const products = menuQuery.data ?? [];

  const needle = search.trim().toLowerCase();
  const groups = products
    .map((product) => {
      const endpoints = product.endpoints.filter(
        (endpoint) =>
          !needle ||
          (endpoint.display_name ?? "").toLowerCase().includes(needle) ||
          (endpoint.endpoint_url ?? "").toLowerCase().includes(needle) ||
          (product.display_name ?? product.product_name).toLowerCase().includes(needle),
      );
      return { product, endpoints };
    })
    .filter((group) => !needle || group.endpoints.length > 0);

  const isOpen = (productId: number) =>
    needle ? true : openGroups ? openGroups.has(productId) : productId === activeProductId;

  function toggle(productId: number) {
    setOpenGroups((current) => {
      const base = current ?? new Set(activeProductId ? [activeProductId] : []);
      const next = new Set(base);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  }

  return (
    <aside className="flex flex-col self-start overflow-hidden rounded-2xl border border-hairline bg-white shadow-sm lg:sticky lg:top-24 lg:max-h-[calc(100dvh-8rem)]">
      <div className="border-b border-hairline p-3">
        {back ? (
          <Link
            href={back.href}
            className="mb-3 flex items-center gap-1.5 px-1 text-sm font-medium text-slate-600 hover:text-nav-active"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            {back.label}
          </Link>
        ) : null}
        <p className="mb-2 px-1 text-xs font-semibold tracking-wide text-nav-active uppercase">APIs</p>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search for APIs"
            aria-label="Search for APIs"
            className="w-full rounded-[10px] border border-hairline bg-white py-2 pr-3 pl-9 text-sm text-ink placeholder:text-subtle focus:border-brand-bright focus:outline-none"
          />
        </div>
      </div>

      <nav className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2" aria-label="API end-points">
        {menuQuery.isLoading ? (
          <p className="flex items-center gap-2 px-2 py-4 text-sm text-subtle">
            <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
            Loading APIs…
          </p>
        ) : groups.length === 0 ? (
          <p className="px-2 py-4 text-sm text-subtle">No APIs match.</p>
        ) : (
          groups.map(({ product, endpoints }) => {
            const open = isOpen(product.product_id);
            return (
              <div key={product.product_id} className="mb-1">
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => toggle(product.product_id)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left text-sm font-semibold transition-colors",
                    product.product_id === activeProductId ? "text-nav-active" : "text-ink",
                    "hover:bg-surface-soft",
                  )}
                >
                  <Layers className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                  <span className="min-w-0 flex-1 leading-snug">{product.display_name ?? product.product_name}</span>
                  <ChevronDown className={cn("mt-0.5 h-4 w-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
                </button>

                {open ? (
                  <ul className="mt-0.5 ml-3.5 flex flex-col gap-0.5 border-l border-[#d5e5d5] pl-2">
                    {endpoints.map((endpoint) => {
                      const active = endpoint.endpoint_id === activeEndpointId;
                      const method = (endpoint.method ?? "GET").toUpperCase();
                      return (
                        <li key={endpoint.endpoint_id}>
                          <Link
                            href={hrefFor(product.product_id, endpoint.endpoint_id)}
                            aria-current={active ? "page" : undefined}
                            className={cn(
                              "flex items-center gap-2 rounded-lg px-2 py-1.5 text-[0.85rem] transition-colors",
                              active ? "bg-[#dcebdc] font-semibold text-brand-deep" : "text-slate-600 hover:bg-surface-soft",
                            )}
                          >
                            <span
                              className={cn(
                                "w-12 shrink-0 font-mono text-[0.65rem] font-bold",
                                METHOD_COLOURS[method] ?? "text-subtle",
                              )}
                            >
                              {method}
                            </span>
                            <span className="min-w-0 flex-1 truncate">{endpoint.display_name ?? endpoint.endpoint_url}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
            );
          })
        )}
      </nav>
    </aside>
  );
}

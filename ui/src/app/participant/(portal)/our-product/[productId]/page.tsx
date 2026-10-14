"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Boxes, LayoutGrid, List, Loader2, Search } from "lucide-react";

import { ApiBanner } from "@/components/portal/console-ui";
import { MethodBadge } from "@/components/ui/status-badge";
import { catalogApi } from "@/lib/services/catalog";
import { cn } from "@/lib/utils";

const ALL = "ALL";

/**
 * One product's APIs, as the reference sandbox's "our product" page: banner with
 * the total, search by end-point URL, API-type filter on the left and the
 * end-points as a grid or a list. Each card opens the API documentation.
 */
export default function OurProductPage() {
  const params = useParams<{ productId: string }>();
  const productId = Number(params.productId);

  const [search, setSearch] = React.useState("");
  const [types, setTypes] = React.useState<string[]>([ALL]);
  const [grid, setGrid] = React.useState(true);

  const productQuery = useQuery({
    queryKey: ["participant", "catalog", "product", productId],
    queryFn: () => catalogApi.portalProduct(productId),
    enabled: Number.isFinite(productId),
  });

  const product = productQuery.data;
  const endpoints = product?.endpoints ?? [];
  const apiTypes = Array.from(new Set(endpoints.map((endpoint) => endpoint.api_type || "General"))).sort();

  const needle = search.trim().toLowerCase();
  const visible = endpoints.filter(
    (endpoint) =>
      (types.includes(ALL) || types.includes(endpoint.api_type || "General")) &&
      (!needle ||
        (endpoint.endpoint_url ?? "").toLowerCase().includes(needle) ||
        (endpoint.display_name ?? "").toLowerCase().includes(needle)),
  );

  function toggleType(type: string) {
    if (type === ALL) {
      setTypes([ALL]);
      return;
    }
    setTypes((current) => {
      const withoutAll = current.filter((item) => item !== ALL);
      const next = withoutAll.includes(type) ? withoutAll.filter((item) => item !== type) : [...withoutAll, type];
      return next.length === 0 ? [ALL] : next;
    });
  }

  if (productQuery.isLoading) {
    return (
      <p className="flex items-center gap-2 py-16 text-sm text-subtle">
        <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
        Loading product…
      </p>
    );
  }

  if (!product) {
    return (
      <div className="rounded-2xl border border-dashed border-hairline bg-white px-6 py-16 text-center">
        <Boxes className="mx-auto h-10 w-10 text-subtle" aria-hidden />
        <p className="mt-3 font-semibold text-ink">This product is not available</p>
        <Link
          href="/participant/catalog"
          className="mt-3 inline-block text-sm font-semibold text-brand-bright hover:underline"
        >
          Back to the API Catalogue
        </Link>
      </div>
    );
  }

  return (
    <>
      <ApiBanner eyebrow={product.category_name ?? "API Product"} title={product.display_name ?? product.product_name}>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-sm">
          <span className="text-white/85">Total APIs:</span>
          <span className="rounded-full bg-brand-gold px-3 py-0.5 font-semibold text-[#0b2a1a]">
            {endpoints.length} {endpoints.length === 1 ? "API" : "APIs"}
          </span>
          {product.api_doc_version ? (
            <span className="rounded-full bg-white/15 px-3 py-0.5 text-white">v{product.api_doc_version}</span>
          ) : null}
        </div>
        {product.description ? (
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-white/85">{product.description}</p>
        ) : null}
        <div className="relative mt-6 w-full max-w-xl">
          <Search
            className="pointer-events-none absolute top-1/2 left-4 h-4 w-4 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by end-point URL or name"
            aria-label="Search end-points"
            className="w-full rounded-full border-0 bg-white py-3.5 pr-5 pl-11 text-sm text-ink shadow-lg placeholder:text-slate-400 focus:ring-2 focus:ring-brand-gold focus:outline-none"
          />
        </div>
      </ApiBanner>

      <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="self-start lg:sticky lg:top-24">
          <Link
            href="/participant/catalog"
            className="mb-3 inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-nav-active"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            API Catalogue
          </Link>
          <div className="rounded-2xl border border-hairline bg-surface-soft p-5">
            <h2 className="text-sm font-bold tracking-wide text-nav-active uppercase">API Type</h2>
            <ul className="mt-3 flex flex-col gap-1">
              {[ALL, ...apiTypes].map((type) => (
                <li key={type}>
                  <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-2 py-2 text-sm font-medium text-ink hover:bg-white">
                    {type === ALL ? "All APIs" : type}
                    <input
                      type="checkbox"
                      checked={types.includes(type)}
                      onChange={() => toggleType(type)}
                      className="h-4 w-4 accent-brand-bright"
                    />
                  </label>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        <section className="min-w-0">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-nav-active">
              Available APIs <span className="font-normal text-subtle">({visible.length})</span>
            </h2>
            <div className="flex gap-1 rounded-lg border border-hairline bg-white p-1" role="group" aria-label="Layout">
              {[
                { id: true, icon: LayoutGrid, label: "Grid view" },
                { id: false, icon: List, label: "List view" },
              ].map((option) => (
                <button
                  key={option.label}
                  type="button"
                  aria-label={option.label}
                  aria-pressed={grid === option.id}
                  onClick={() => setGrid(option.id)}
                  className={cn(
                    "rounded-md p-1.5 transition-colors",
                    grid === option.id ? "bg-nav-active text-white" : "text-slate-500 hover:bg-surface-soft",
                  )}
                >
                  <option.icon className="h-4 w-4" aria-hidden />
                </button>
              ))}
            </div>
          </div>

          {visible.length === 0 ? (
            <p className="rounded-2xl border border-hairline bg-white px-6 py-12 text-center text-sm text-subtle">
              No end-points found.
            </p>
          ) : (
            <ul className={cn("grid gap-4", grid ? "sm:grid-cols-2 xl:grid-cols-3" : "grid-cols-1")}>
              {visible.map((endpoint) => (
                <li key={endpoint.endpoint_id}>
                  <Link
                    href={`/participant/product/${product.product_id}/endpoint/${endpoint.endpoint_id}`}
                    className={cn(
                      "group flex h-full gap-4 rounded-2xl border border-hairline bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-brand-bright hover:shadow-md",
                      grid ? "flex-col" : "flex-col sm:flex-row sm:items-center",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="font-semibold text-ink">{endpoint.display_name ?? endpoint.endpoint_url}</h3>
                        {endpoint.api_type ? (
                          <span className="shrink-0 rounded-full bg-surface-soft px-2 py-0.5 text-[0.7rem] font-semibold text-nav-active">
                            {endpoint.api_type}
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-2 flex min-w-0 items-center gap-2">
                        <MethodBadge method={endpoint.method} />
                        <code className="truncate font-mono text-xs text-slate-600">{endpoint.endpoint_url}</code>
                      </div>
                      <p className="mt-3 line-clamp-3 text-sm text-subtle">
                        {endpoint.description || "No description available."}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg border border-btn-outline px-3.5 py-2 text-sm font-semibold text-btn-outline transition-colors group-hover:bg-btn-outline group-hover:text-white",
                        grid ? "mt-auto" : "sm:self-center",
                      )}
                    >
                      View API
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";

import { iconFor } from "@/lib/category-icons";
import { cn } from "@/lib/utils";
import type { Product } from "@/types/api";

const ALL = "All";

function categoryOf(product: Product): string {
  return product.category_name ?? "Uncategorised";
}

export function CatalogBrowser({ products }: { products: Product[] }) {
  const [query, setQuery] = React.useState("");
  const [category, setCategory] = React.useState(ALL);

  const categories = React.useMemo(
    () => [ALL, ...Array.from(new Set(products.map(categoryOf)))],
    [products],
  );

  const term = query.trim().toLowerCase();
  const visible = products.filter((product) => {
    if (category !== ALL && categoryOf(product) !== category) {
      return false;
    }
    if (!term) {
      return true;
    }
    return [
      product.display_name,
      product.product_name,
      product.description,
      product.category_name,
      ...(product.product_keywords ?? []),
    ].some((value) => value?.toLowerCase().includes(term));
  });

  return (
    <div>
      {/* ---------- Search and category filter ---------- */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Filter by category" className="flex flex-wrap gap-2">
          {categories.map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={category === name}
              onClick={() => setCategory(name)}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition",
                category === name
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-white text-slate-600 ring-1 ring-[#ece8dc] hover:text-brand-700 hover:ring-brand-300",
              )}
            >
              {name}
            </button>
          ))}
        </div>
        <label className="relative block w-full lg:w-80">
          <span className="sr-only">Search APIs</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search APIs…"
            className="h-11 w-full rounded-lg border border-hairline bg-white pl-10 pr-3.5 text-sm text-ink transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none"
          />
        </label>
      </div>

      <p className="mt-6 text-sm text-slate-500" aria-live="polite">
        Showing {visible.length} of {products.length} products
      </p>

      {/* ---------- Product cards ---------- */}
      {visible.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-[#ddd8c8] bg-white py-16 text-center">
          <p className="font-medium text-ink">No products match your search</p>
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setCategory(ALL);
            }}
            className="mt-3 text-sm font-semibold text-brand-700 hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((product) => {
            const Icon = iconFor(categoryOf(product));
            return (
              <Link
                key={product.product_id}
                href={`/catalog/${product.product_id}`}
                className="group flex flex-col rounded-2xl border border-[#ece8dc] bg-white p-6 transition hover:-translate-y-1 hover:border-brand-300 hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-3">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-200 transition group-hover:bg-brand-600 group-hover:text-white">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="rounded-full bg-brand-gold/15 px-2.5 py-1 text-xs font-semibold text-[#8a5a12]">
                    {product.endpoint_count} {product.endpoint_count === 1 ? "API" : "APIs"}
                  </span>
                </div>
                <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-brand-700">
                  {categoryOf(product)}
                </p>
                <h3 className="mt-1 text-lg font-semibold text-ink">
                  {product.display_name ?? product.product_name}
                </h3>
                <p className="mt-2 line-clamp-3 flex-1 text-sm text-slate-600">
                  {product.description ?? "No description provided."}
                </p>
                <div className="mt-5 flex items-center justify-between border-t border-[#f0ece1] pt-4 text-sm">
                  <span className="font-mono text-xs text-slate-500">
                    {product.api_doc_version ? `v${product.api_doc_version}` : "Sandbox"}
                  </span>
                  <span className="inline-flex items-center gap-1 font-semibold text-brand-700">
                    Explore
                    <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" aria-hidden />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

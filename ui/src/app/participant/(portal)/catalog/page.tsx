"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Boxes, FlaskConical, Layers, Loader2, PlugZap, Search } from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { iconFor } from "@/lib/category-icons";
import { Badge } from "@/components/ui/badge";
import { MethodBadge } from "@/components/ui/status-badge";
import { catalogApi } from "@/lib/services/catalog";
import { cn } from "@/lib/utils";

const ALL = "__all";

export default function PortalCatalogPage() {
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState(ALL);
  const [selected, setSelected] = React.useState<number | null>(null);
  const [endpointSearch, setEndpointSearch] = React.useState("");

  const productsQuery = useQuery({
    queryKey: ["participant", "catalog", "products"],
    queryFn: catalogApi.portalProducts,
  });

  const allProducts = productsQuery.data ?? [];
  const categories = Array.from(
    new Set(allProducts.map((product) => product.category_name).filter((name): name is string => Boolean(name))),
  ).sort();

  const needle = search.trim().toLowerCase();
  const products = allProducts.filter(
    (product) =>
      (category === ALL || product.category_name === category) &&
      (!needle ||
        (product.display_name ?? product.product_name).toLowerCase().includes(needle) ||
        (product.description ?? "").toLowerCase().includes(needle)),
  );

  // Keep a product selected: the first one in view unless the user picked another.
  const activeId = products.some((product) => product.product_id === selected) ? selected : (products[0]?.product_id ?? null);
  const active = products.find((product) => product.product_id === activeId) ?? null;

  const detailQuery = useQuery({
    queryKey: ["participant", "catalog", "product", activeId],
    queryFn: () => catalogApi.portalProduct(activeId as number),
    enabled: activeId !== null,
  });

  const stats = [
    { icon: Boxes, value: allProducts.length, label: "Products" },
    { icon: PlugZap, value: allProducts.reduce((total, product) => total + product.endpoint_count, 0), label: "APIs" },
    { icon: Layers, value: categories.length, label: "Categories" },
    { icon: FlaskConical, value: "Sandbox", label: "synthetic data" },
  ];

  const endpointNeedle = endpointSearch.trim().toLowerCase();
  const endpoints = (detailQuery.data?.endpoints ?? []).filter(
    (endpoint) =>
      !endpointNeedle ||
      (endpoint.endpoint_url ?? "").toLowerCase().includes(endpointNeedle) ||
      (endpoint.display_name ?? "").toLowerCase().includes(endpointNeedle),
  );

  return (
    <div className="space-y-6">
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="API Catalogue"
        title="API Catalogue"
        description="Pick a product, read an API's documentation, then test it in the sandbox."
        image="/assets/home/rice-field-farmers.webp"
      >
        {productsQuery.isSuccess && allProducts.length > 0
          ? stats.map(({ icon: Icon, value, label }) => (
              <span
                key={label}
                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm text-white ring-1 ring-white/25 backdrop-blur"
              >
                <Icon className="h-4 w-4 text-brand-gold" aria-hidden />
                <span className="font-semibold">{value}</span>
                <span className="text-white/75">{label}</span>
              </span>
            ))
          : null}
      </PageBanner>

      {productsQuery.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-subtle">
          <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
          Loading catalogue…
        </p>
      ) : allProducts.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-hairline bg-white px-6 py-16 text-center">
          <Boxes className="mx-auto h-10 w-10 text-subtle" aria-hidden />
          <p className="mt-3 font-semibold text-ink">No API products are published yet</p>
          <p className="mt-1 text-sm text-subtle">Check back soon — the network operator publishes new APIs here.</p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          {/* ------------------------------------------------------ products */}
          <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search APIs"
                aria-label="Search APIs"
                className="w-full rounded-[10px] border border-hairline bg-white py-2.5 pr-3 pl-10 text-sm text-ink placeholder:text-subtle focus:border-brand-bright focus:outline-none"
              />
            </div>

            {categories.length > 0 ? (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by category">
                {[ALL, ...categories].map((name) => (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={category === name}
                    onClick={() => setCategory(name)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                      category === name
                        ? "border-nav-active bg-nav-active text-white"
                        : "border-hairline bg-white text-slate-600 hover:border-brand-bright",
                    )}
                  >
                    {name === ALL ? "All" : name}
                  </button>
                ))}
              </div>
            ) : null}

            <nav className="flex flex-col gap-2" aria-label="API products">
              {products.length === 0 ? (
                <p className="rounded-xl border border-hairline bg-white px-4 py-6 text-center text-sm text-subtle">
                  No products match.
                </p>
              ) : (
                products.map((product) => {
                  const isActive = product.product_id === activeId;
                  const Icon = iconFor(product.category_name ?? "");
                  return (
                    <button
                      key={product.product_id}
                      type="button"
                      aria-current={isActive ? "true" : undefined}
                      onClick={() => {
                        setSelected(product.product_id);
                        setEndpointSearch("");
                      }}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border p-3.5 text-left transition-colors",
                        isActive
                          ? "border-nav-active bg-surface-soft shadow-sm"
                          : "border-hairline bg-white hover:border-brand-bright",
                      )}
                    >
                      <span
                        className={cn(
                          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                          isActive ? "bg-nav-active text-white" : "bg-surface-soft text-brand-bright",
                        )}
                      >
                        <Icon className="h-4.5 w-4.5" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 text-sm font-semibold text-ink">
                          {product.display_name ?? product.product_name}
                        </span>
                        <span className="mt-1 flex items-center gap-2 text-xs text-subtle">
                          {product.endpoint_count} {product.endpoint_count === 1 ? "API" : "APIs"}
                          {product.api_doc_version ? <span>· v{product.api_doc_version}</span> : null}
                        </span>
                      </span>
                    </button>
                  );
                })
              )}
            </nav>
          </aside>

          {/* ----------------------------------------------------- end-points */}
          <section className="min-w-0 rounded-2xl border border-hairline bg-white p-5 shadow-sm sm:p-6">
            {active ? (
              <>
                <div className="flex flex-col gap-3 border-b border-hairline pb-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-xl font-semibold text-ink">{active.display_name ?? active.product_name}</h2>
                    {active.api_doc_version ? <Badge variant="info">v{active.api_doc_version}</Badge> : null}
                    {active.category_name ? <Badge variant="neutral">{active.category_name}</Badge> : null}
                    <Link
                      href={`/participant/our-product/${active.product_id}`}
                      className="ml-auto inline-flex items-center gap-1.5 text-sm font-semibold text-brand-bright hover:underline"
                    >
                      Open product
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </Link>
                  </div>
                  <p className="text-sm leading-relaxed text-subtle">
                    {active.description ?? "No description provided."}
                  </p>
                </div>

                <div className="mt-5 mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <h3 className="text-base font-semibold text-nav-active">
                    End-Points <span className="font-normal text-subtle">({endpoints.length})</span>
                  </h3>
                  <div className="relative sm:w-72">
                    <Search className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
                    <input
                      type="search"
                      value={endpointSearch}
                      onChange={(event) => setEndpointSearch(event.target.value)}
                      placeholder="Filter end-points"
                      aria-label="Filter end-points"
                      className="w-full rounded-[10px] border border-hairline bg-white py-2 pr-3 pl-10 text-sm text-ink placeholder:text-subtle focus:border-brand-bright focus:outline-none"
                    />
                  </div>
                </div>

                {detailQuery.isLoading ? (
                  <p className="flex items-center gap-2 py-8 text-sm text-subtle">
                    <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
                    Loading end-points…
                  </p>
                ) : endpoints.length === 0 ? (
                  <p className="py-8 text-center text-sm text-subtle">No end-points match.</p>
                ) : (
                  <ul className="flex flex-col gap-3">
                    {endpoints.map((endpoint) => (
                      <li key={endpoint.endpoint_id}>
                        <Link
                          href={`/participant/product/${active.product_id}/endpoint/${endpoint.endpoint_id}`}
                          className="group flex flex-col gap-3 rounded-xl border border-hairline p-4 transition-colors hover:border-brand-bright hover:bg-surface-soft sm:flex-row sm:items-center"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-ink">{endpoint.display_name ?? endpoint.endpoint_url}</p>
                            <div className="mt-1.5 flex min-w-0 items-center gap-2">
                              <MethodBadge method={endpoint.method} />
                              <code className="truncate font-mono text-xs text-slate-600">{endpoint.endpoint_url}</code>
                            </div>
                            {endpoint.description ? (
                              <p className="mt-2 line-clamp-2 text-sm text-subtle">{endpoint.description}</p>
                            ) : null}
                          </div>
                          <span className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-[10px] border border-btn-outline px-3.5 py-2 text-sm font-semibold text-btn-outline transition-colors group-hover:bg-btn-outline group-hover:text-white sm:self-center">
                            View API
                            <ArrowRight className="h-4 w-4" aria-hidden />
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="py-16 text-center text-sm text-subtle">Select a product to see its end-points.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

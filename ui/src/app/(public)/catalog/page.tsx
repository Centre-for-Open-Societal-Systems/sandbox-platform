import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Boxes, FlaskConical, Layers, PlugZap } from "lucide-react";

import { PAGE_CONTAINER, PageBanner } from "@/components/layout/page-banner";
import { CatalogBrowser } from "@/components/portal/catalog-browser";
import { serverFetch } from "@/lib/server-api";
import type { Product } from "@/types/api";

export const metadata: Metadata = {
  title: "API Catalogue",
  description: "Browse the API products published on the Open Agri Net network.",
};

async function loadProducts(): Promise<Product[]> {
  try {
    const response = await serverFetch("/catalog/products", 120);
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.data as Product[]) ?? [];
  } catch {
    return [];
  }
}

export default async function CatalogPage() {
  const products = await loadProducts();

  const categoryCount = new Set(products.map((product) => product.category_name ?? "Uncategorised")).size;
  const endpointCount = products.reduce((total, product) => total + product.endpoint_count, 0);

  const stats = [
    { icon: Boxes, value: products.length, label: "API products" },
    { icon: PlugZap, value: endpointCount, label: "Endpoints" },
    { icon: Layers, value: categoryCount, label: "Categories" },
    { icon: FlaskConical, value: "100%", label: "Synthetic sandbox data" },
  ];

  return (
    <div className="bg-[#fbfaf6]">
      <PageBanner
        crumb="API Catalogue"
        title="API Catalogue"
        description="Explore the agriculture APIs published on the network. Sign in to try any endpoint against synthetic sandbox data."
        image="/assets/home/rice-field-farmers.webp"
        overlap
      >
        <Link
          href="/participant/register"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-gold px-6 py-3 font-semibold text-[#0b2a1a] shadow-lg transition hover:brightness-110"
        >
          Get API access
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
        <Link
          href="/how-it-works"
          className="inline-flex items-center rounded-lg bg-white/10 px-6 py-3 font-semibold text-white ring-1 ring-white/40 backdrop-blur transition hover:bg-white/20"
        >
          How it works
        </Link>
      </PageBanner>

      {/* ---------- Stats strip, overlapping the banner ---------- */}
      <section className={`${PAGE_CONTAINER} relative -mt-14`}>
        <dl className="grid grid-cols-2 overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-black/5 lg:grid-cols-4">
          {stats.map(({ icon: Icon, value, label }, index) => (
            <div
              key={label}
              className={`flex items-center gap-4 p-5 sm:p-6 ${index > 0 ? "lg:border-l" : ""} ${index % 2 === 1 ? "border-l" : ""} ${index > 1 ? "border-t lg:border-t-0" : ""} border-[#f0ece1]`}
            >
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <div className="flex flex-col-reverse">
                <dt className="text-sm text-slate-500">{label}</dt>
                <dd className="text-2xl font-bold text-ink">{value}</dd>
              </div>
            </div>
          ))}
        </dl>
      </section>

      {/* ---------- Products ---------- */}
      <section className={`${PAGE_CONTAINER} py-14`}>
        {products.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[#ddd8c8] bg-white py-16 text-center">
            <p className="text-sm text-slate-500">No API products have been published yet. Check back shortly.</p>
          </div>
        ) : (
          <CatalogBrowser products={products} />
        )}
      </section>

      {/* ---------- Call to action ---------- */}
      <section className={`${PAGE_CONTAINER} pb-20`}>
        <div className="relative overflow-hidden rounded-3xl px-6 py-14 sm:px-14">
          <Image
            src="/assets/home/farmer-maize.webp"
            alt=""
            fill
            sizes="(min-width: 1320px) 1320px, 100vw"
            className="object-cover"
          />
          <div aria-hidden className="absolute inset-0 bg-linear-to-r from-[#0b2a1a]/95 to-[#0b2a1a]/60" />
          <div className="relative flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-center">
            <div className="max-w-2xl">
              <h2 className="text-3xl font-bold text-white sm:text-4xl">Ready to integrate?</h2>
              <p className="mt-3 text-white/80">
                Create a free sandbox account and make your first API call today.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/participant/register"
                className="inline-flex items-center gap-2 rounded-lg bg-brand-gold px-6 py-3.5 font-semibold text-[#0b2a1a] transition hover:brightness-110"
              >
                Create an account
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
              <Link
                href="/participant/login"
                className="inline-flex items-center rounded-lg px-6 py-3.5 font-semibold text-white ring-1 ring-white/50 transition hover:bg-white/10"
              >
                Sign in
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

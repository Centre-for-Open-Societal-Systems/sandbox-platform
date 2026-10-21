import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  FileDown,
  FlaskConical,
  Layers,
  Lock,
  PlugZap,
  Sparkles,
  Tag,
  type LucideIcon,
} from "lucide-react";

import { PAGE_CONTAINER, PageBanner } from "@/components/layout/page-banner";
import { MethodBadge } from "@/components/ui/status-badge";
import { CategoryIcon } from "@/lib/category-icons";
import { serverFetch } from "@/lib/server-api";
import type { ProductDetail } from "@/types/api";

interface PageProps {
  params: Promise<{ productId: string }>;
}

async function loadProduct(productId: string): Promise<ProductDetail | null> {
  try {
    const response = await serverFetch(`/catalog/products/${productId}`, 120);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return payload.data as ProductDetail;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { productId } = await params;
  const product = await loadProduct(productId);
  return {
    title: product?.display_name ?? product?.product_name ?? "API Product",
    description: product?.description ?? undefined,
  };
}

export default async function ProductPage({ params }: PageProps) {
  const { productId } = await params;
  const product = await loadProduct(productId);

  if (!product) {
    notFound();
  }

  const name = product.display_name ?? product.product_name;

  return (
    <div className="bg-[#fbfaf6]">
      <PageBanner
        parents={[{ label: "API Catalogue", href: "/catalog" }]}
        crumb={name}
        title={name}
        description={product.description ?? undefined}
        image="/assets/home/farmer-maize.webp"
        overlap
        eyebrow={
          product.category_name ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-gold/15 px-3 py-1 text-xs font-semibold tracking-wide text-brand-gold uppercase ring-1 ring-brand-gold/40">
              <CategoryIcon category={product.category_name} className="h-3.5 w-3.5" />
              {product.category_name}
            </span>
          ) : null
        }
      >
        <Link
          href="/participant/login"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-gold px-6 py-3 font-semibold text-[#0b2a1a] shadow-lg transition hover:brightness-110"
        >
          Try in sandbox
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
        {product.product_documentation_pdf ? (
          <a
            href={product.product_documentation_pdf}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-6 py-3 font-semibold text-white ring-1 ring-white/40 backdrop-blur transition hover:bg-white/20"
          >
            <FileDown className="h-4 w-4" aria-hidden />
            Documentation (PDF)
          </a>
        ) : null}
      </PageBanner>

      <div className={`${PAGE_CONTAINER} relative -mt-14 grid gap-6 pb-20 lg:grid-cols-[1fr_340px]`}>
        {/* ---------------------------------------------------------- main */}
        <div className="min-w-0 space-y-6">
          {product.key_features ? (
            <section className="rounded-2xl bg-white p-6 shadow-xl ring-1 ring-black/5 sm:p-8">
              <SectionTitle icon={Sparkles} title="Key features" />
              <div
                className="prose prose-sm mt-4 max-w-none text-slate-600"
                dangerouslySetInnerHTML={{ __html: product.key_features }}
              />
            </section>
          ) : null}

          <section
            className={`rounded-2xl bg-white p-6 ring-1 ring-black/5 sm:p-8 ${product.key_features ? "shadow-sm" : "shadow-xl"}`}
          >
            <div className="flex items-center justify-between gap-3">
              <SectionTitle icon={PlugZap} title="Endpoints" />
              <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700">
                {product.endpoints.length} {product.endpoints.length === 1 ? "API" : "APIs"}
              </span>
            </div>

            {product.endpoints.length === 0 ? (
              <p className="mt-6 rounded-xl border border-dashed border-[#ddd8c8] py-10 text-center text-sm text-slate-500">
                No endpoints have been published for this product yet.
              </p>
            ) : (
              <ul className="mt-6 space-y-3">
                {product.endpoints.map((endpoint) => (
                  <li
                    key={endpoint.endpoint_id}
                    className="group flex flex-col gap-3 rounded-xl border border-[#ece8dc] p-4 transition hover:border-brand-300 hover:bg-[#fbfaf6] sm:flex-row sm:items-center"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-ink">{endpoint.display_name ?? endpoint.endpoint_url}</p>
                      <div className="mt-1.5 flex min-w-0 items-center gap-2">
                        <MethodBadge method={endpoint.method} />
                        <code className="truncate font-mono text-xs text-slate-600">{endpoint.endpoint_url}</code>
                      </div>
                      {endpoint.description ? (
                        <p className="mt-2 line-clamp-2 text-sm text-slate-500">{endpoint.description}</p>
                      ) : null}
                    </div>
                    <Link
                      href="/participant/login"
                      className="inline-flex shrink-0 items-center gap-1.5 self-start rounded-lg px-3 py-2 text-sm font-semibold text-brand-700 ring-1 ring-brand-200 transition group-hover:bg-brand-600 group-hover:text-white group-hover:ring-brand-600 sm:self-center"
                    >
                      <Lock className="h-3.5 w-3.5" aria-hidden />
                      Sign in to try
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* ------------------------------------------------------- sidebar */}
        <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <section className="relative overflow-hidden rounded-2xl bg-[#0b2a1a] p-6 text-white shadow-xl">
            <div aria-hidden className="pointer-events-none absolute -top-12 -right-12 h-40 w-40 rounded-full bg-brand-gold/15" />
            <span className="relative flex h-11 w-11 items-center justify-center rounded-xl bg-brand-gold text-[#0b2a1a]">
              <FlaskConical className="h-5 w-5" aria-hidden />
            </span>
            <h2 className="relative mt-4 text-lg font-semibold">Try these endpoints</h2>
            <p className="relative mt-1.5 text-sm text-white/75">
              Sign in to call {name} against synthetic sandbox data — no real farmer records.
            </p>
            <div className="relative mt-5 flex flex-col gap-2.5">
              <Link
                href="/participant/login"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-gold px-5 py-2.5 font-semibold text-[#0b2a1a] transition hover:brightness-110"
              >
                Sign in
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
              <Link
                href="/participant/register"
                className="inline-flex items-center justify-center rounded-lg px-5 py-2.5 font-semibold text-white ring-1 ring-white/40 transition hover:bg-white/10"
              >
                Create an account
              </Link>
            </div>
          </section>

          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-black/5">
            <h2 className="text-base font-semibold text-ink">Product details</h2>
            <dl className="mt-4 divide-y divide-[#f0ece1] text-sm">
              <DetailRow icon={PlugZap} label="Endpoints" value={String(product.endpoints.length)} />
              {product.api_doc_version ? (
                <DetailRow icon={Tag} label="Version" value={`v${product.api_doc_version}`} mono />
              ) : null}
              {product.category_name ? (
                <DetailRow icon={Layers} label="Category" value={product.category_name} />
              ) : null}
              <DetailRow icon={FlaskConical} label="Environment" value="Sandbox" />
            </dl>
            {product.product_documentation_pdf ? (
              <a
                href={product.product_documentation_pdf}
                target="_blank"
                rel="noreferrer"
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-brand-700 ring-1 ring-brand-200 transition hover:bg-brand-50"
              >
                <FileDown className="h-4 w-4" aria-hidden />
                Download documentation
              </a>
            ) : null}
          </section>

          <Link
            href="/catalog"
            className="flex items-center justify-between rounded-2xl bg-white px-6 py-4 text-sm font-semibold text-brand-700 shadow-sm ring-1 ring-black/5 transition hover:ring-brand-300"
          >
            Browse all API products
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </aside>
      </div>
    </div>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <h2 className="flex items-center gap-2.5 text-lg font-semibold text-ink">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
        <Icon className="h-4.5 w-4.5" aria-hidden />
      </span>
      {title}
    </h2>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
  mono = false,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <dt className="flex items-center gap-2 text-slate-500">
        <Icon className="h-4 w-4" aria-hidden />
        {label}
      </dt>
      <dd className={`text-right font-medium text-ink ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

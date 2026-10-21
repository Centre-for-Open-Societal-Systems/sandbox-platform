import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BadgeCheck,
  Building2,
  CheckCircle2,
  ChevronDown,
  Code2,
  CloudSun,
  FileCheck2,
  FlaskConical,
  Handshake,
  Landmark,
  LifeBuoy,
  Map as MapIcon,
  Rocket,
  ShieldCheck,
  Sprout,
  UserPlus,
  Users,
  Wheat,
} from "lucide-react";

import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { config } from "@/lib/config";
import { serverFetch } from "@/lib/server-api";
import type { Faq, FaqGroup, PublicHome } from "@/types/api";

/**
 * Open Agri Net landing page. Rendered on the server; hero copy, featured products and
 * FAQs come from the CMS when available, and the page falls back to default copy when
 * the API is unreachable. Photos are openly licensed agriculture images
 * (public domain / CC0, no attribution required).
 */
async function fetchData<T>(path: string): Promise<T | null> {
  try {
    const response = await serverFetch(path, 300);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return payload.data as T;
  } catch {
    return null;
  }
}

const HIGHLIGHTS = [
  { icon: FlaskConical, title: "Synthetic Data", body: "Realistic records, no real farmers" },
  { icon: Code2, title: "Live Try-It Console", body: "Call every end-point from the browser" },
  { icon: ShieldCheck, title: "Consent First", body: "Built on a recorded lawful basis" },
  { icon: Rocket, title: "Path to Production", body: "Sandbox → UAT → Production" },
];

const ABOUT_POINTS = [
  "Standardised, consent-based access to farmer, farm and crop data",
  "One integration that works across member countries",
  "Mock responses for every status code, so you can build before the upstream is ready",
];

const DOMAINS = [
  { icon: Users, title: "Farmer Registry", body: "Identity and profile of registered farmers." },
  { icon: MapIcon, title: "Land & Plots", body: "Parcels, ownership and geo-referenced plots." },
  { icon: Wheat, title: "Crops & Seasons", body: "Crop sown, season and yield information." },
  { icon: CloudSun, title: "Advisory", body: "Weather, soil and agronomy advisories." },
  { icon: Landmark, title: "Schemes & Benefits", body: "Beneficiary programmes and entitlements." },
  { icon: Sprout, title: "Inputs & Markets", body: "Seed, fertiliser and market linkages." },
];

const USERS = [
  {
    icon: Code2,
    title: "Developers & Researchers",
    body: "Explore the APIs, prototype ideas and study agricultural data safely.",
  },
  {
    icon: Handshake,
    title: "Agritech Partners",
    body: "Plug network data into advisory, extension and farm-management platforms.",
  },
  {
    icon: Building2,
    title: "Government & Agencies",
    body: "Ministries, bureaus and regional offices improving scheme delivery.",
  },
  {
    icon: Landmark,
    title: "Banks, Insurers & Startups",
    body: "Credit, insurance and value-chain services built on trusted farm data.",
  },
];

const STEPS = [
  { icon: UserPlus, title: "Register", body: "Create an account for your organisation.", env: null },
  { icon: BadgeCheck, title: "Get Approved", body: "The network operator reviews your request.", env: null },
  { icon: FlaskConical, title: "Build & Test", body: "Call the APIs with synthetic data.", env: "Sandbox" },
  { icon: FileCheck2, title: "Validate", body: "Prove your integration against pre-production.", env: "UAT" },
  { icon: Rocket, title: "Go Live", body: "Serve real users once production is approved.", env: "Production" },
];

/** Shown when the CMS has no published FAQs (or the API is down). */
const DEFAULT_FAQS: Array<Pick<Faq, "faq_id" | "question" | "answer">> = [
  {
    faq_id: -1,
    question: `What is the ${config.siteName} Sandbox?`,
    answer:
      "A developer environment where registered organisations explore and test the network's agriculture APIs against synthetic data before requesting UAT and production access.",
  },
  {
    faq_id: -2,
    question: "Who can register?",
    answer:
      "Developers, agritech companies, government bodies, financial institutions and other service providers working in agriculture.",
  },
  {
    faq_id: -3,
    question: "Is the data in the sandbox real?",
    answer:
      "No. Every sandbox record is synthetic. It has the same shape as production data but does not describe real farmers or land.",
  },
  {
    faq_id: -4,
    question: "How do I move from sandbox to production?",
    answer:
      "When your integration works in the sandbox, request UAT access from your dashboard. After validation in UAT, submit a production request for approval.",
  },
  {
    faq_id: -5,
    question: "Does sandbox access cost anything?",
    answer: "No. Sandbox access is free for approved participants.",
  },
];

const CONTAINER = "mx-auto max-w-[1320px] px-4 sm:px-8";

function Eyebrow({ children, light = false }: { children: React.ReactNode; light?: boolean }) {
  return (
    <p
      className={`inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.16em] ${
        light ? "text-brand-gold" : "text-[#b7791f]"
      }`}
    >
      <span className="h-0.5 w-6 rounded-full bg-current" aria-hidden />
      {children}
    </p>
  );
}

export default async function HomePage() {
  const [home, faqGroups] = await Promise.all([
    fetchData<PublicHome>("/home"),
    fetchData<FaqGroup[]>("/faqs"),
  ]);
  const hero = home?.blocks.find((block) => block.block_key === "hero");
  const publishedFaqs = (faqGroups ?? []).flatMap((group) => group.faqs);
  const faqs = publishedFaqs.length > 0 ? publishedFaqs : DEFAULT_FAQS;

  return (
    <div className="flex min-h-screen flex-col bg-[#fbfaf6]">
      <SiteHeader />

      <main className="flex-1">
        {/* ---------- Hero: full-width photo, copy left, console preview right ---------- */}
        <section id="home-section" className="relative scroll-mt-24 overflow-hidden">
          <Image
            src="/assets/home/hero-tea-farm.webp"
            alt="Green tea farm under a blue sky"
            fill
            priority
            sizes="100vw"
            className="object-cover object-[center_70%]"
          />
          <div
            aria-hidden
            className="absolute inset-0 bg-linear-to-r from-[#0b2a1a]/95 via-[#0b2a1a]/75 to-[#0b2a1a]/25"
          />

          <div className={`${CONTAINER} relative grid items-center gap-12 pb-32 pt-16 lg:grid-cols-[1.15fr_0.85fr] lg:pb-40 lg:pt-24`}>
            <div>
              <span className="inline-flex items-center gap-2 rounded-full bg-brand-gold/15 px-4 py-1.5 text-sm font-semibold text-brand-gold ring-1 ring-brand-gold/40">
                <Sprout className="h-4 w-4" aria-hidden />
                Developer Sandbox
              </span>
              <h1 className="mt-6 text-4xl font-bold leading-[1.1] text-white sm:text-[3.4rem]">
                {hero?.title ?? (
                  <>
                    Build the Future of <span className="text-brand-gold">Farming</span> on Open
                    Agricultural Data
                  </>
                )}
              </h1>
              <p className="mt-5 max-w-xl text-lg leading-relaxed text-white/85">
                {hero?.subtitle ??
                  `${config.siteName} connects farmers, government and service providers through shared, consented data. Test every API in a safe sandbox before you go live.`}
              </p>
              <div className="mt-9 flex flex-wrap gap-3">
                <Link
                  href="/participant/register"
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-gold px-6 py-3.5 font-semibold text-[#0b2a1a] shadow-lg transition hover:brightness-110"
                >
                  Start building
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                <Link
                  href="/catalog"
                  className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-6 py-3.5 font-semibold text-white ring-1 ring-white/40 backdrop-blur transition hover:bg-white/20"
                >
                  Browse the API catalogue
                </Link>
              </div>
            </div>

            <div className="hidden rounded-2xl bg-[#0d1f16]/85 p-1 shadow-2xl ring-1 ring-white/10 backdrop-blur lg:block">
              <div className="flex items-center gap-1.5 px-4 py-3">
                <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
                <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
                <span className="h-3 w-3 rounded-full bg-[#28c840]" />
                <span className="ml-3 text-xs text-white/50">sandbox console</span>
              </div>
              <pre className="overflow-hidden rounded-xl bg-[#07140d] px-5 py-4 font-mono text-[0.8rem] leading-relaxed text-white/80">
                <span className="text-[#9fdc6b]">POST</span> /beneficiary_portal/get_register{"\n"}
                <span className="text-white/40">x-api-key: ••••••••••••</span>
                {"\n\n"}
                <span className="text-brand-gold">200 OK</span>
                <span className="text-white/40">  · 84 ms · x-sandbox-mock: true</span>
                {"\n"}
                {"{"}
                {"\n"}
                {"  "}
                <span className="text-[#7dd3fc]">&quot;registrant&quot;</span>: {"{"}
                {"\n"}
                {"    "}
                <span className="text-[#7dd3fc]">&quot;name&quot;</span>:{" "}
                <span className="text-[#fcd34d]">&quot;Amina Wanjiru&quot;</span>,{"\n"}
                {"    "}
                <span className="text-[#7dd3fc]">&quot;region&quot;</span>:{" "}
                <span className="text-[#fcd34d]">&quot;Region 04&quot;</span>,{"\n"}
                {"    "}
                <span className="text-[#7dd3fc]">&quot;crop&quot;</span>:{" "}
                <span className="text-[#fcd34d]">&quot;Maize&quot;</span>
                {"\n"}
                {"  }"}
                {"\n"}
                {"}"}
              </pre>
              <p className="px-4 py-3 text-xs text-white/50">Synthetic sample record</p>
            </div>
          </div>
        </section>

        {/* ---------- Highlights, overlapping the hero ---------- */}
        <section className={`${CONTAINER} relative z-10 -mt-20`}>
          <div className="grid gap-px overflow-hidden rounded-2xl bg-[#e8e4d8] shadow-xl sm:grid-cols-2 lg:grid-cols-4">
            {HIGHLIGHTS.map((item) => (
              <div key={item.title} className="flex items-start gap-4 bg-white p-6">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                  <item.icon className="h-5 w-5" aria-hidden />
                </span>
                <div>
                  <p className="font-semibold text-slate-900">{item.title}</p>
                  <p className="mt-1 text-sm text-slate-600">{item.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ---------- About: photos left, copy right ---------- */}
        <section className={`${CONTAINER} grid items-center gap-14 py-20 lg:grid-cols-2`}>
          <div className="relative mx-auto w-full max-w-[560px] pb-16 pr-10">
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl shadow-lg">
              <Image
                src="/assets/home/farmer-maize.webp"
                alt="Farmer inspecting a maize cob in his field"
                fill
                sizes="(min-width: 1024px) 520px, 90vw"
                className="object-cover"
              />
            </div>
            <div className="absolute bottom-0 right-0 aspect-[3/2] w-[52%] overflow-hidden rounded-2xl border-[6px] border-[#fbfaf6] shadow-lg">
              <Image
                src="/assets/home/farmers-tomatoes.webp"
                alt="Two farmers tending tomato plants"
                fill
                sizes="300px"
                className="object-cover"
              />
            </div>
          </div>

          <div>
            <Eyebrow>About the network</Eyebrow>
            <h2 className="mt-4 text-3xl font-bold leading-tight text-slate-900 sm:text-[2.5rem]">
              Digital Public Infrastructure for Agriculture
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-slate-600">
              {config.siteName} is a shared data layer for the agriculture sector. Registries,
              advisories and programmes speak one language, so a service built once can reach
              farmers everywhere the network runs.
            </p>
            <ul className="mt-7 space-y-3.5">
              {ABOUT_POINTS.map((point) => (
                <li key={point} className="flex items-start gap-3 text-slate-700">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-brand-500" aria-hidden />
                  {point}
                </li>
              ))}
            </ul>
            <Link
              href="/how-it-works"
              className="mt-8 inline-flex items-center gap-2 font-semibold text-brand-600 hover:underline"
            >
              How the sandbox works
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </section>

        {/* ---------- Data domains ---------- */}
        <section className="bg-white py-20">
          <div className={CONTAINER}>
            <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
              <div className="max-w-2xl">
                <Eyebrow>Data domains</Eyebrow>
                <h2 className="mt-4 text-3xl font-bold text-slate-900 sm:text-[2.5rem]">
                  What You Can Build With
                </h2>
                <p className="mt-4 text-slate-600">
                  The network is organised around these domains. Published APIs for each appear in
                  the catalogue with request and response samples.
                </p>
              </div>
              <Link
                href="/catalog"
                className="inline-flex items-center gap-2 self-start rounded-lg border border-brand-600 px-5 py-2.5 font-semibold text-brand-600 transition hover:bg-brand-600 hover:text-white lg:self-auto"
              >
                Open the catalogue
                <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </div>

            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {DOMAINS.map((domain) => (
                <div
                  key={domain.title}
                  className="group flex gap-4 rounded-2xl border border-[#ece8dc] bg-[#fbfaf6] p-6 transition hover:border-brand-300 hover:bg-white hover:shadow-md"
                >
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white text-brand-600 shadow-sm ring-1 ring-[#ece8dc] transition group-hover:bg-brand-600 group-hover:text-white">
                    <domain.icon className="h-6 w-6" aria-hidden />
                  </span>
                  <div>
                    <h3 className="font-semibold text-slate-900">{domain.title}</h3>
                    <p className="mt-1 text-sm text-slate-600">{domain.body}</p>
                  </div>
                </div>
              ))}
            </div>

            {home?.featured_products?.length ? (
              <div className="mt-14">
                <h3 className="text-lg font-semibold text-slate-900">Featured APIs</h3>
                <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                  {home.featured_products.map((product) => (
                    <Link
                      key={product.product_id}
                      href={`/catalog/${product.product_id}`}
                      className="rounded-2xl border border-[#ece8dc] bg-white p-6 transition hover:-translate-y-1 hover:shadow-md"
                    >
                      <h4 className="font-semibold text-slate-900">{product.product_name}</h4>
                      <p className="mt-2 line-clamp-3 text-sm text-slate-600">
                        {product.description ?? "No description provided."}
                      </p>
                    </Link>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        {/* ---------- Users: terraces photo band ---------- */}
        <section id="users-section" className="relative scroll-mt-20 overflow-hidden py-20">
          <Image
            src="/assets/home/rice-field-farmers.webp"
            alt=""
            fill
            sizes="100vw"
            className="object-cover"
          />
          <div aria-hidden className="absolute inset-0 bg-[#0b2a1a]/85" />

          <div className={`${CONTAINER} relative`}>
            <div className="mx-auto max-w-2xl text-center">
              <Eyebrow light>Who it&apos;s for</Eyebrow>
              <h2 className="mt-4 text-3xl font-bold text-white sm:text-[2.5rem]">
                Made for Everyone Building for Farmers
              </h2>
              <p className="mt-4 text-white/75">
                From a single developer to a national agency — the sandbox gives each of them the
                same safe place to experiment.
              </p>
            </div>

            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {USERS.map((user) => (
                <div
                  key={user.title}
                  className="rounded-2xl border border-white/15 bg-white/[0.07] p-6 backdrop-blur-md transition hover:-translate-y-1 hover:bg-white/[0.12]"
                >
                  <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-gold text-[#0b2a1a]">
                    <user.icon className="h-6 w-6" aria-hidden />
                  </span>
                  <h3 className="mt-5 text-lg font-semibold text-white">{user.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-white/70">{user.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- Process: horizontal stepper ---------- */}
        <section id="process-section" className={`${CONTAINER} scroll-mt-20 py-20`}>
          <div className="mx-auto max-w-2xl text-center">
            <Eyebrow>Getting access</Eyebrow>
            <h2 className="mt-4 text-3xl font-bold text-slate-900 sm:text-[2.5rem]">
              From Sign-Up to Production in Five Steps
            </h2>
          </div>

          <ol className="relative mt-14 grid gap-8 md:grid-cols-5 md:gap-4">
            <span
              aria-hidden
              className="absolute left-[10%] right-[10%] top-7 hidden h-0.5 bg-linear-to-r from-brand-300 via-brand-500 to-brand-gold md:block"
            />
            {STEPS.map((step, index) => (
              <li key={step.title} className="relative flex gap-4 md:flex-col md:items-center md:text-center">
                <span className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-white text-brand-600 shadow-md ring-4 ring-[#fbfaf6]">
                  <step.icon className="h-6 w-6" aria-hidden />
                  <span className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
                    {index + 1}
                  </span>
                </span>
                <div className="md:mt-5">
                  <h3 className="font-semibold text-slate-900">{step.title}</h3>
                  <p className="mt-1 text-sm text-slate-600">{step.body}</p>
                  {step.env ? (
                    <span className="mt-3 inline-block rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 ring-1 ring-brand-200">
                      {step.env}
                    </span>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ---------- Call to action: aerial photo ---------- */}
        <section className={`${CONTAINER} pb-20`}>
          <div className="relative overflow-hidden rounded-3xl px-6 py-14 sm:px-14">
            <Image
              src="/assets/home/tea-rows.webp"
              alt=""
              fill
              sizes="(min-width: 1320px) 1320px, 100vw"
              className="object-cover"
            />
            <div aria-hidden className="absolute inset-0 bg-linear-to-r from-[#0b2a1a]/95 to-[#0b2a1a]/60" />
            <div className="relative flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-center">
              <div className="max-w-2xl">
                <h2 className="text-3xl font-bold text-white sm:text-4xl">
                  Ready to Grow with {config.siteName}?
                </h2>
                <p className="mt-3 text-white/80">
                  Create your account, get approved and make your first sandbox call today.
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

        {/* ---------- FAQs ---------- */}
        <section id="faqs-section" className="scroll-mt-20 bg-white py-20">
          <div className={`${CONTAINER} grid gap-12 lg:grid-cols-[0.8fr_1.2fr]`}>
            <div>
              <Eyebrow>FAQs</Eyebrow>
              <h2 className="mt-4 text-3xl font-bold text-slate-900 sm:text-[2.5rem]">
                Questions, Answered
              </h2>
              <p className="mt-4 text-slate-600">
                Can&apos;t find what you need? Signed-in participants can raise a support query from
                their dashboard.
              </p>
              <div className="relative mt-8 hidden aspect-[4/3] overflow-hidden rounded-2xl lg:block">
                <Image
                  src="/assets/home/bean-harvest.webp"
                  alt="Farmers harvesting beans"
                  fill
                  sizes="480px"
                  className="object-cover"
                />
                <div className="absolute inset-x-4 bottom-4 flex items-center gap-3 rounded-xl bg-white/95 p-4 shadow-lg">
                  <LifeBuoy className="h-8 w-8 shrink-0 text-brand-600" aria-hidden />
                  <div>
                    <p className="font-semibold text-slate-900">Need more help?</p>
                    <Link href="/faqs" className="text-sm font-medium text-brand-600 hover:underline">
                      Read all FAQs
                    </Link>
                  </div>
                </div>
              </div>
            </div>

            <div className="divide-y divide-[#ece8dc] border-y border-[#ece8dc]">
              {faqs.map((faq, index) => (
                <details key={faq.faq_id} name="home-faq" open={index === 0} className="group py-1">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-lg font-semibold text-slate-900 [&::-webkit-details-marker]:hidden">
                    {faq.question}
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-50 text-brand-600 transition group-open:rotate-180 group-open:bg-brand-600 group-open:text-white">
                      <ChevronDown className="h-4 w-4" aria-hidden />
                    </span>
                  </summary>
                  <p className="pb-5 pr-12 leading-relaxed text-slate-600">{faq.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

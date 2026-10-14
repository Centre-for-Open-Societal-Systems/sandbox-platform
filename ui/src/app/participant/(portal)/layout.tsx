"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronDown,
  Gauge,
  KeyRound,
  Layers,
  LifeBuoy,
  Leaf,
  LogOut,
  Menu,
  ScrollText,
  UserRound,
  X,
} from "lucide-react";

import { SiteFooter, type FooterSection } from "@/components/layout/site-footer";
import { useToast } from "@/components/ui/toast";
import { config } from "@/lib/config";
import { participantApi } from "@/lib/services/participant";
import { useHydrated } from "@/hooks/use-hydrated";
import { participantSession } from "@/lib/session";
import { cn, initials } from "@/lib/utils";
import type { ParticipantSession } from "@/types/api";

const NAV_ITEMS = [
  { href: "/participant/dashboard", label: "Dashboard", icon: Gauge },
  {
    href: "/participant/catalog",
    label: "API Catalogue",
    icon: Layers,
    // Product pages, API documentation and the sandbox test page belong here too.
    match: ["/participant/catalog", "/participant/our-product", "/participant/product/"],
  },
  { href: "/participant/api-history", label: "API History", icon: ScrollText },
];

const FOOTER_SECTIONS: FooterSection[] = [
  {
    title: "Portal",
    links: [
      { href: "/participant/dashboard", label: "Dashboard" },
      { href: "/participant/catalog", label: "API Catalogue" },
      { href: "/participant/api-history", label: "API History" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/participant/profile", label: "My Profile" },
      { href: "/participant/profile#change-password", label: "Change Password" },
    ],
  },
  {
    title: "Support",
    links: [
      { href: "/participant/support", label: "Support & Queries" },
      { href: "/how-it-works", label: "How it works" },
      { href: "/faqs", label: "FAQs" },
      { href: "/terms", label: "Terms & Conditions" },
    ],
  },
];

const FULL_WIDTH_PREFIXES = ["/participant/our-product/", "/participant/product/"];

function isNavActive(pathname: string, item: { href: string; match?: string[] }): boolean {
  return (item.match ?? [item.href]).some((prefix) => pathname.startsWith(prefix));
}

const ENVIRONMENT_ORDER = ["PRODUCTION", "UAT", "SANDBOX"];

/** The highest environment the participant can call, shown next to the avatar. */
function currentEnvironment(environments: string[]): string | null {
  return ENVIRONMENT_ORDER.find((environment) => environments.includes(environment)) ?? null;
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const wide = FULL_WIDTH_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  const { notify } = useToast();
  const hydrated = useHydrated();
  // Local storage only exists in the browser, so read it once hydrated.
  const session = React.useMemo<ParticipantSession | null>(
    () => (hydrated ? participantSession.get() : null),
    [hydrated],
  );
  const [mobileOpen, setMobileOpen] = React.useState(false);

  React.useEffect(() => {
    if (hydrated && !session) {
      router.replace("/participant/login");
    }
  }, [hydrated, session, router]);

  async function handleSignOut() {
    try {
      await participantApi.logout();
    } catch {
      // The local session is cleared regardless so the user is never stuck.
    }
    participantSession.clear();
    notify("Signed out.", "info");
    router.replace("/participant/login");
  }

  if (!session) {
    return null;
  }

  const environment = currentEnvironment(session.environments);

  return (
    <div className="flex min-h-screen flex-col bg-[#f7faf7]">
      <header className="sticky top-0 z-[55] border-b border-hairline bg-white">
        <div className={cn("mx-auto flex h-16 items-center gap-6", wide ? "max-w-none px-4 sm:px-6 2xl:px-10" : "max-w-7xl px-4")}>
          <Link href="/participant/dashboard" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-linear-to-b from-brand-bright to-brand-deep text-white">
              <Leaf className="h-5 w-5" aria-hidden />
            </span>
            <span className="hidden font-semibold text-brand-deep sm:inline">{config.siteName}</span>
            <span className="rounded bg-surface-soft px-1.5 py-0.5 text-[0.7rem] font-semibold tracking-wide text-nav-active uppercase">
              Sandbox
            </span>
          </Link>

          <nav className="hidden h-full items-stretch gap-1 md:flex" aria-label="Portal">
            {NAV_ITEMS.map((item) => {
              const active = isNavActive(pathname, item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "-mb-px flex items-center gap-2 border-b-2 px-3 text-sm transition-colors",
                    active
                      ? "border-nav-active font-semibold text-nav-active"
                      : "border-transparent text-slate-600 hover:text-ink",
                  )}
                >
                  <item.icon className="h-4 w-4" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {environment ? (
              <span
                className="hidden items-center gap-1.5 rounded-full border border-hairline px-2.5 py-1 text-xs font-medium text-slate-600 sm:inline-flex"
                title="Highest environment you can call"
              >
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    environment === "PRODUCTION"
                      ? "bg-brand-bright"
                      : environment === "UAT"
                        ? "bg-sky-500"
                        : "bg-brand-gold",
                  )}
                  aria-hidden
                />
                {environment}
              </span>
            ) : null}

            <UserMenu session={session} onSignOut={handleSignOut} />

            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-hairline text-slate-600 md:hidden"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen((open) => !open)}
            >
              {mobileOpen ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
            </button>
          </div>
        </div>

        {mobileOpen ? (
          <nav className="border-t border-hairline bg-white px-4 py-2 md:hidden" aria-label="Portal">
            {NAV_ITEMS.map((item) => {
              const active = isNavActive(pathname, item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setMobileOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm",
                    active ? "bg-surface-soft font-semibold text-nav-active" : "text-ink hover:bg-slate-50",
                  )}
                >
                  <item.icon className="h-4 w-4" aria-hidden />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        ) : null}
      </header>

      <main
        className={cn(
          "mx-auto w-full flex-1 py-8",
          // API pages (product, documentation, sandbox) use the whole screen width.
          wide ? "max-w-none px-4 sm:px-6 2xl:px-10" : "max-w-7xl px-4",
        )}
      >
        {children}
      </main>

      <SiteFooter
        sections={FOOTER_SECTIONS}
        homeHref="/participant/dashboard"
        containerClassName={wide ? "max-w-none px-4 sm:px-6 2xl:px-10" : "max-w-7xl px-4"}
      />
    </div>
  );
}

function UserMenu({ session, onSignOut }: { session: ParticipantSession; onSignOut: () => void }) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const itemClass = "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink hover:bg-surface-soft";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-full border border-hairline bg-white py-1 pr-2.5 pl-1 text-sm font-semibold text-ink hover:bg-slate-50"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-xs text-white">
          {initials(session.display_name)}
        </span>
        <span className="hidden max-w-36 truncate lg:inline">{session.display_name}</span>
        <ChevronDown className={cn("h-4 w-4 text-subtle transition-transform", open && "rotate-180")} aria-hidden />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute top-[calc(100%+8px)] right-0 z-[56] w-64 rounded-xl border border-hairline bg-white p-1.5 shadow-[0_12px_30px_rgba(0,0,0,0.12)]"
        >
          <div className="flex items-center gap-3 border-b border-hairline px-3 pt-2 pb-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
              {initials(session.display_name)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{session.display_name}</p>
              <p className="truncate text-xs text-subtle">{session.email_id ?? session.company_name}</p>
            </div>
          </div>

          <div className="flex flex-col py-1.5">
            <Link role="menuitem" href="/participant/profile" className={itemClass} onClick={() => setOpen(false)}>
              <UserRound className="h-4 w-4 text-subtle" aria-hidden />
              My Profile
            </Link>
            <Link
              role="menuitem"
              href="/participant/profile#change-password"
              className={itemClass}
              onClick={() => setOpen(false)}
            >
              <KeyRound className="h-4 w-4 text-subtle" aria-hidden />
              Change Password
            </Link>
            <Link role="menuitem" href="/participant/support" className={itemClass} onClick={() => setOpen(false)}>
              <LifeBuoy className="h-4 w-4 text-subtle" aria-hidden />
              Support &amp; Queries
            </Link>
          </div>

          <div className="border-t border-hairline pt-1.5">
            <button
              type="button"
              role="menuitem"
              onClick={onSignOut}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-red-700 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Logout
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

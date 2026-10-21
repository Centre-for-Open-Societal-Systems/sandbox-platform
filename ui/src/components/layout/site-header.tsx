"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Leaf, LogIn, Menu, UserPlus, X } from "lucide-react";

import { config } from "@/lib/config";
import { cn } from "@/lib/utils";

/**
 * Public header following the Indian AgriStack sandbox: logo left, section links
 * that scroll the landing page (Home / Users / Process / FAQs), the API catalogue,
 * then Sign Up and Login pills.
 */
const NAV_LINKS = [
  { href: "/", label: "Home", section: "home" },
  { href: "/#users-section", label: "Users", section: "users" },
  { href: "/#process-section", label: "Process", section: "process" },
  { href: "/#faqs-section", label: "FAQs", section: "faqs" },
  { href: "/catalog", label: "API Catalogue", section: null },
] as const;

const SECTION_IDS = ["home", "users", "process", "faqs"] as const;

/** Tracks which landing-page section is in view, so the matching link lights up. */
function useActiveSection(enabled: boolean) {
  const [active, setActive] = React.useState<string>("home");

  React.useEffect(() => {
    if (!enabled) return;
    const sections = SECTION_IDS.map((id) => document.getElementById(`${id}-section`)).filter(
      (element): element is HTMLElement => element !== null,
    );
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id.replace("-section", ""));
          }
        }
      },
      { rootMargin: "-45% 0px -50% 0px" },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [enabled]);

  return active;
}

export function SiteHeader() {
  const pathname = usePathname();
  const onHome = pathname === "/";
  const activeSection = useActiveSection(onHome);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [scrolled, setScrolled] = React.useState(false);

  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function isActive(link: (typeof NAV_LINKS)[number]) {
    if (link.section) return onHome && activeSection === link.section;
    return pathname.startsWith(link.href);
  }

  return (
    <header
      className={cn(
        "sticky top-0 z-40 bg-white/95 backdrop-blur transition-shadow",
        scrolled ? "shadow-[0_2px_16px_rgba(11,42,26,0.10)]" : "border-b border-[#ece8dc]",
      )}
    >
      <div className="mx-auto flex h-[72px] max-w-[1320px] items-center justify-between gap-4 px-4 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5" onClick={() => setMenuOpen(false)}>
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-linear-to-br from-brand-gold to-[#b7791f] text-white shadow-sm">
            <Leaf className="h-5 w-5" aria-hidden />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-lg font-bold text-[#0b2a1a]">{config.siteName}</span>
            <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-brand-600">
              Sandbox
            </span>
          </span>
        </Link>

        <nav className="hidden items-center gap-1 lg:flex" aria-label="Main">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "border-b-2 px-3 py-2 text-[1.02rem] font-medium transition-colors",
                isActive(link)
                  ? "border-brand-600 text-brand-600"
                  : "border-transparent text-slate-700 hover:text-brand-600",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-2 lg:flex">
          <Link
            href="/participant/register"
            className="inline-flex items-center gap-2 rounded-full bg-brand-700 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-600"
          >
            <UserPlus className="h-4 w-4" aria-hidden />
            Sign Up
          </Link>
          <Link
            href="/participant/login"
            className="inline-flex items-center gap-2 rounded-full border border-brand-700 px-5 py-2 text-sm font-semibold text-[#0b2a1a] transition-colors hover:border-brand-600 hover:bg-brand-600 hover:text-white"
          >
            <LogIn className="h-4 w-4" aria-hidden />
            Login
          </Link>
        </div>

        <button
          type="button"
          className="rounded-md p-2 text-[#0b2a1a] lg:hidden"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {menuOpen ? (
        <nav className="border-t border-[#ece8dc] bg-white px-4 pb-5 pt-2 lg:hidden" aria-label="Mobile">
          <ul className="flex flex-col">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className={cn(
                    "block border-b border-slate-100 px-2 py-3 font-medium",
                    isActive(link) ? "text-brand-600" : "text-slate-700",
                  )}
                  onClick={() => setMenuOpen(false)}
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <Link
              href="/participant/register"
              className="flex-1 rounded-full bg-brand-700 py-2.5 text-center text-sm font-semibold text-white"
              onClick={() => setMenuOpen(false)}
            >
              Sign Up
            </Link>
            <Link
              href="/participant/login"
              className="flex-1 rounded-full border border-brand-700 py-2.5 text-center text-sm font-semibold text-[#0b2a1a]"
              onClick={() => setMenuOpen(false)}
            >
              Login
            </Link>
          </div>
        </nav>
      ) : null}
    </header>
  );
}

import Link from "next/link";
import { Leaf } from "lucide-react";

import { ScrollToTop } from "@/components/layout/scroll-to-top";
import { config } from "@/lib/config";
import { cn } from "@/lib/utils";

export interface FooterSection {
  title: string;
  links: Array<{ href: string; label: string }>;
}

const FOOTER_SECTIONS: FooterSection[] = [
  {
    title: "Explore",
    links: [
      { href: "/#users-section", label: "Who it's for" },
      { href: "/#process-section", label: "Getting access" },
      { href: "/catalog", label: "API Catalogue" },
      { href: "/how-it-works", label: "How it works" },
    ],
  },
  {
    title: "Support",
    links: [
      { href: "/faqs", label: "FAQs" },
      { href: "/terms", label: "Terms & Conditions" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/participant/register", label: "Sign Up" },
      { href: "/participant/login", label: "User Login" },
      { href: "/admin/login", label: "Admin Login" },
    ],
  },
];

interface SiteFooterProps {
  /** Link columns; the participant portal passes its own. */
  sections?: FooterSection[];
  /** Where the logo points. */
  homeHref?: string;
  /** Width and padding of the content column, to line up with the page above. */
  containerClassName?: string;
}

export function SiteFooter({
  sections = FOOTER_SECTIONS,
  homeHref = "/",
  containerClassName = "max-w-[1320px] px-4 sm:px-8",
}: SiteFooterProps) {
  return (
    <footer className="bg-[#0b2a1a] text-[#c9d6cd]">
      <div className="h-1 bg-linear-to-r from-brand-500 via-brand-gold to-brand-500" aria-hidden />
      <div className={cn("mx-auto pb-6 pt-14", containerClassName)}>
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Link href={homeHref} className="inline-flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-gold text-[#0b2a1a]">
                <Leaf className="h-5 w-5" aria-hidden />
              </span>
              <span className="text-lg font-bold text-white">{config.siteName}</span>
            </Link>
            <p className="mt-4 max-w-sm text-sm leading-relaxed">
              Shared digital infrastructure for agriculture. Test every API with synthetic data,
              then move to UAT and production.
            </p>
          </div>

          {sections.map((section) => (
            <div key={section.title}>
              <p className="text-sm font-semibold text-white">{section.title}</p>
              <ul className="mt-4 space-y-2.5">
                {section.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="text-sm transition-colors hover:text-brand-gold">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col gap-3 border-t border-white/10 pt-6 text-sm lg:flex-row lg:items-start lg:justify-between">
          <p className="text-white">
            © {new Date().getFullYear()} {config.siteName}. Sandbox data is synthetic.
          </p>
        </div>
      </div>

      <ScrollToTop />
    </footer>
  );
}

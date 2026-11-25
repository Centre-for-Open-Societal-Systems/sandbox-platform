import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/** Same width as the landing page sections, so banners line up with the rest of the site. */
export const PAGE_CONTAINER = "mx-auto w-full max-w-[1320px] px-4 sm:px-8";

interface PageBannerProps {
  title: string;
  description?: React.ReactNode;
  /** Current page label shown after "Home" in the breadcrumb. */
  crumb: string;
  /** Where the "Home" breadcrumb points; the participant portal uses its dashboard. */
  homeHref?: string;
  /** Levels between "Home" and the current page, e.g. the catalogue above a product. */
  parents?: Array<{ label: string; href: string }>;
  /** Small label above the title, such as a category. */
  eyebrow?: React.ReactNode;
  /** Background photo from /public (openly licensed, no attribution). */
  image?: string;
  /** Buttons or other content rendered under the description. */
  children?: React.ReactNode;
  /** Extra bottom space so the next section can overlap the banner with a negative margin. */
  overlap?: boolean;
  /**
   * Compact rounded card for pages inside an app layout (the participant portal), instead of
   * a full-width strip under the public site header.
   */
  inset?: boolean;
}

/** Photo banner with a dark brand overlay, used at the top of public and portal pages. */
export function PageBanner({
  title,
  description,
  crumb,
  homeHref = "/",
  parents = [],
  eyebrow,
  image = "/assets/home/tea-rows.webp",
  children,
  overlap = false,
  inset = false,
}: PageBannerProps) {
  return (
    <section className={cn("relative overflow-hidden", inset && "rounded-2xl shadow-sm")}>
      <Image
        src={image}
        alt=""
        fill
        priority
        sizes={inset ? "(min-width: 1280px) 1280px, 100vw" : "100vw"}
        className="object-cover"
      />
      <div aria-hidden className="absolute inset-0 bg-linear-to-r from-[#0b2a1a]/95 to-[#0b2a1a]/70" />
      <div
        className={cn(
          "relative",
          inset ? "px-6 py-7 sm:px-8" : cn(PAGE_CONTAINER, "pt-10", overlap ? "pb-24" : "pb-12"),
        )}
      >
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-sm text-white/70">
          <Link href={homeHref} className="hover:text-white">
            Home
          </Link>
          {parents.map((parent) => (
            <React.Fragment key={parent.href}>
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              <Link href={parent.href} className="hover:text-white">
                {parent.label}
              </Link>
            </React.Fragment>
          ))}
          <ChevronRight className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 truncate text-white" aria-current="page">
            {crumb}
          </span>
        </nav>
        {eyebrow ? <div className={inset ? "mt-3" : "mt-4"}>{eyebrow}</div> : null}
        <h1
          className={cn(
            "font-bold text-white",
            eyebrow ? "mt-2" : inset ? "mt-3" : "mt-4",
            inset ? "text-2xl sm:text-3xl" : "text-3xl sm:text-4xl",
          )}
        >
          {title}
        </h1>
        {description ? <p className="mt-2 max-w-2xl text-white/80">{description}</p> : null}
        {children ? <div className={cn("flex flex-wrap gap-3", inset ? "mt-5" : "mt-6")}>{children}</div> : null}
      </div>
    </section>
  );
}

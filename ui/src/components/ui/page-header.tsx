import * as React from "react";
import Link from "next/link";
import { ChevronRight, Search } from "lucide-react";

import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  breadcrumbs?: Crumb[];
  /** Search box in the header row, left of the actions. */
  search?: { value: string; onChange: (value: string) => void; placeholder?: string };
  className?: string;
}

/** Title on the left; search and the primary action on the right. */
export function PageHeader({ title, description, actions, breadcrumbs, search, className }: PageHeaderProps) {
  return (
    <div className={cn("mb-6 flex flex-col gap-3", className)}>
      {breadcrumbs && breadcrumbs.length > 0 ? (
        <nav aria-label="Breadcrumb">
          <ol className="flex flex-wrap items-center gap-1 text-sm text-subtle">
            {breadcrumbs.map((crumb, index) => {
              const last = index === breadcrumbs.length - 1;
              return (
                <li key={`${crumb.label}-${index}`} className="flex items-center gap-1">
                  {crumb.href && !last ? (
                    <Link href={crumb.href} className="hover:text-brand-bright">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className={cn(last && "font-medium text-ink")} aria-current={last ? "page" : undefined}>
                      {crumb.label}
                    </span>
                  )}
                  {!last ? <ChevronRight className="h-3.5 w-3.5" aria-hidden /> : null}
                </li>
              );
            })}
          </ol>
        </nav>
      ) : null}

      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink">{title}</h1>
          {description ? (
            <p className="mt-1 max-w-3xl text-sm leading-relaxed text-subtle">{description}</p>
          ) : null}
        </div>

        {search || actions ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {search ? <SearchBox {...search} /> : null}
            {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder = "Search",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative">
      <Search
        className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-subtle"
        aria-hidden
      />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-full rounded-[10px] border border-hairline bg-white py-2.5 pr-3 pl-10 text-sm text-ink placeholder:text-subtle focus:border-brand-bright focus:outline-none sm:w-80"
      />
    </div>
  );
}

/** Mint strip holding a page's filters, placed between the header and the table. */
export function FilterBar({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "mb-6 flex flex-col gap-4 rounded-xl border border-hairline bg-surface-soft px-5 py-4 sm:flex-row sm:flex-wrap sm:items-end",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** One labelled control inside a FilterBar. */
export function FilterField({
  label,
  htmlFor,
  className,
  children,
}: {
  label: string;
  htmlFor?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex w-full flex-col gap-2 sm:max-w-65", className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
    </div>
  );
}

import type { Metadata } from "next";

import { PAGE_CONTAINER, PageBanner } from "@/components/layout/page-banner";
import { Card, CardContent } from "@/components/ui/card";
import { config } from "@/lib/config";
import { serverFetch } from "@/lib/server-api";
import { formatDate } from "@/lib/utils";
import type { TermSection } from "@/types/api";

export const metadata: Metadata = {
  title: "Terms & Conditions",
  description: "Terms governing participation in the Open Agri Net network.",
};

async function loadTerms(): Promise<TermSection[]> {
  try {
    const response = await serverFetch("/terms", 300);
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.data as TermSection[]) ?? [];
  } catch {
    return [];
  }
}

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default async function TermsPage() {
  const sections = await loadTerms();
  const lastUpdated = sections
    .map((section) => section.modify_date)
    .filter(Boolean)
    .sort()
    .at(-1);

  return (
    <div className="bg-[#fbfaf6]">
      <PageBanner
        crumb="Terms & Conditions"
        title="Terms & Conditions"
        description={
          lastUpdated
            ? `The rules for participating in ${config.siteName}. Last updated ${formatDate(lastUpdated)}.`
            : `The rules for participating in ${config.siteName}.`
        }
        image="/assets/home/bean-harvest.webp"
      />

      <div className={`${PAGE_CONTAINER} py-12`}>
        {sections.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <p className="text-sm text-muted-foreground">Terms have not been published yet.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
            <nav className="lg:sticky lg:top-24 lg:self-start" aria-label="Sections">
              <ul className="space-y-1">
                {sections.map((section) => (
                  <li key={section.table_id}>
                    <a
                      href={`#${slugify(section.sidebar_title)}`}
                      className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                    >
                      {section.sidebar_title}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>

            <div className="space-y-10">
              {sections.map((section) => (
                <section key={section.table_id} id={slugify(section.sidebar_title)} className="scroll-mt-24">
                  <h2 className="text-lg font-semibold tracking-tight">{section.sidebar_title}</h2>
                  <div
                    className="prose prose-sm mt-3 max-w-none text-muted-foreground"
                    dangerouslySetInnerHTML={{ __html: section.term_content ?? "" }}
                  />
                </section>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

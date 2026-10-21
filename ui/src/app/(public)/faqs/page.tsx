import type { Metadata } from "next";

import { PAGE_CONTAINER, PageBanner } from "@/components/layout/page-banner";
import { Card, CardContent } from "@/components/ui/card";
import { serverFetch } from "@/lib/server-api";
import type { FaqGroup } from "@/types/api";

export const metadata: Metadata = {
  title: "FAQs",
  description: "Answers to common questions about joining and building on Open Agri Net.",
};

async function loadFaqs(): Promise<FaqGroup[]> {
  try {
    const response = await serverFetch("/faqs", 300);
    if (!response.ok) {
      return [];
    }
    const payload = await response.json();
    return (payload.data as FaqGroup[]) ?? [];
  } catch {
    return [];
  }
}

export default async function FaqsPage() {
  const groups = await loadFaqs();

  return (
    <div className="bg-[#fbfaf6]">
      <PageBanner
        crumb="FAQs"
        title="Frequently asked questions"
        description="If your question is not answered here, raise a support query from your dashboard."
        image="/assets/home/hero-tea-farm.webp"
      />

      <div className={`${PAGE_CONTAINER} py-12`}>
        {groups.length === 0 ? (
          <Card>
            <CardContent className="py-16 text-center">
              <p className="text-sm text-muted-foreground">No questions have been published yet.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-10">
            {groups.map((group) => (
              <section key={group.type_id}>
                <h2 className="mb-4 text-lg font-semibold tracking-tight">{group.faq_type}</h2>
                <div className="space-y-3">
                  {group.faqs.map((faq) => (
                    <details
                      key={faq.faq_id}
                      className="group rounded-xl border border-[#ece8dc] bg-white px-5 py-4 transition open:border-brand-300 open:shadow-sm"
                    >
                      <summary className="cursor-pointer list-none font-medium marker:hidden">
                        <span className="flex items-start justify-between gap-4">
                          {faq.question}
                          <span className="text-brand-600 transition-transform group-open:rotate-45">+</span>
                        </span>
                      </summary>
                      <div className="mt-3 text-sm text-muted-foreground">{faq.answer}</div>
                    </details>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

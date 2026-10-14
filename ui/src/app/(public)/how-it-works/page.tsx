import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PAGE_CONTAINER, PageBanner } from "@/components/layout/page-banner";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "The path from registration to production access on the Open Agri Net network.",
};

const STAGES = [
  {
    step: 1,
    title: "Register your organisation",
    body: "Provide your legal details, trade licence number and the service you intend to build. Individual developers can register too, with identity verification instead of a licence.",
  },
  {
    step: 2,
    title: "Get approved for the sandbox",
    body: "The network operator reviews your application, usually within three working days. Once approved you can sign in and call every published endpoint.",
  },
  {
    step: 3,
    title: "Build against synthetic data",
    body: "Sandbox responses match the production schema exactly but contain no real farmer records, so you can develop and demo freely.",
  },
  {
    step: 4,
    title: "Certify in UAT",
    body: "Request UAT access when your integration is ready. UAT runs against pre-production services and is where compatibility is formally signed off.",
  },
  {
    step: 5,
    title: "Go live",
    body: "Submit your production request with the required compliance documents. On approval you receive production credentials and agreed rate limits.",
  },
];

const RULES = [
  "Use data only for the purpose declared at registration.",
  "Retain personal data no longer than the agreed retention period.",
  "Report a suspected breach within 24 hours.",
  "Keep credentials out of client-side code and version control.",
];

export default function HowItWorksPage() {
  return (
    <div className="bg-[#fbfaf6]">
      <PageBanner
        crumb="How it works"
        title="How it works"
        description="Every participant follows the same path, from a first sandbox call to serving real users in production."
        image="/assets/home/farmers-tomatoes.webp"
      />

      <div className={`${PAGE_CONTAINER} py-12`}>
        <ol className="space-y-4">
          {STAGES.map((stage) => (
            <li key={stage.step}>
              <Card>
                <CardContent className="flex gap-4 pt-6">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-medium text-white">
                    {stage.step}
                  </span>
                  <div>
                    <h2 className="font-medium">{stage.title}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">{stage.body}</p>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ol>

        <section className="mt-12">
          <h2 className="text-lg font-semibold tracking-tight">What we ask of participants</h2>
          <ul className="mt-4 space-y-2">
            {RULES.map((rule) => (
              <li key={rule} className="flex gap-2 text-sm text-muted-foreground">
                <span aria-hidden className="text-brand-600">
                  •
                </span>
                {rule}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-muted-foreground">
            The full obligations are set out in the{" "}
            <Link href="/terms" className="text-brand-700 hover:underline">
              terms and conditions
            </Link>
            .
          </p>
        </section>

        <div className="mt-12 flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/participant/register">Create an account</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/catalog">Browse the API catalogue</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

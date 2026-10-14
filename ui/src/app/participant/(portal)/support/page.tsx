"use client";

import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Inbox, LifeBuoy, Loader2, MessageSquareReply, Send } from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { QueryStatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { participantApi } from "@/lib/services/participant";
import { QUERY_TYPES, queryTypeLabel } from "@/lib/support";
import { cn, formatDateTime } from "@/lib/utils";
import type { SupportQuery } from "@/types/api";

const DESCRIPTION_MIN = 10;
const DESCRIPTION_MAX = 4000;
const EMPTY_FORM = { queryType: 1, subject: "", description: "" };

export default function ParticipantSupportPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [form, setForm] = React.useState(EMPTY_FORM);
  const [openId, setOpenId] = React.useState<number | null>(null);

  const queriesQuery = useQuery({
    queryKey: ["participant", "queries"],
    queryFn: participantApi.listQueries,
  });

  const submit = useMutation({
    mutationFn: () => participantApi.createQuery(form.subject.trim(), form.description.trim(), form.queryType),
    onSuccess: (created) => {
      notify("Your query has been submitted. We will reply by email.", "success");
      setForm(EMPTY_FORM);
      setOpenId(created.query_id);
      queryClient.invalidateQueries({ queryKey: ["participant", "queries"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const description = form.description.trim();
  const tooShort = description.length > 0 && description.length < DESCRIPTION_MIN;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form.subject.trim().length < 3) {
      notify("Please add a short subject (at least 3 characters).", "warning");
      return;
    }
    if (description.length < DESCRIPTION_MIN) {
      notify(`Please describe your query in at least ${DESCRIPTION_MIN} characters.`, "warning");
      return;
    }
    submit.mutate();
  }

  const queries = [...(queriesQuery.data ?? [])].sort(
    (a, b) => new Date(b.added_date ?? 0).getTime() - new Date(a.added_date ?? 0).getTime(),
  );
  const openCount = queries.filter((item) => item.status === 0 || item.status === 1).length;

  return (
    <div>
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="Support & Queries"
        title="Support & Queries"
        description="Ask the Open Agri Net team about the APIs, your access or anything else. Answers appear here and are emailed to you."
        image="/assets/home/farmers-tomatoes.webp"
      />

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[420px_1fr]">
        {/* --------------------------------------------------------- new query */}
        <section className="rounded-2xl border border-hairline bg-white p-6 shadow-sm" aria-labelledby="new-query">
          <div className="flex items-center gap-2">
            <LifeBuoy className="h-5 w-5 text-brand-bright" aria-hidden />
            <h2 id="new-query" className="text-base font-semibold text-nav-active">
              Raise a query
            </h2>
          </div>

          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm font-medium">Category</legend>
              <div className="grid grid-cols-2 gap-2">
                {QUERY_TYPES.map((type) => (
                  <label
                    key={type.value}
                    className={cn(
                      "flex cursor-pointer items-center justify-center rounded-lg border px-3 py-2 text-sm font-semibold transition-colors",
                      form.queryType === type.value
                        ? "border-brand-bright bg-brand-50 text-brand-deep"
                        : "border-hairline text-slate-600 hover:bg-slate-50",
                    )}
                  >
                    <input
                      type="radio"
                      name="query_type"
                      value={type.value}
                      checked={form.queryType === type.value}
                      onChange={() => setForm({ ...form, queryType: type.value })}
                      className="sr-only"
                    />
                    {type.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="flex flex-col gap-2">
              <Label htmlFor="query-subject" required>
                Subject
              </Label>
              <Input
                id="query-subject"
                value={form.subject}
                maxLength={500}
                onChange={(event) => setForm({ ...form, subject: event.target.value })}
                placeholder="e.g. Token expires too quickly"
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="query-description" required>
                Your query
              </Label>
              <Textarea
                id="query-description"
                rows={6}
                value={form.description}
                maxLength={DESCRIPTION_MAX}
                aria-invalid={tooShort}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder="Tell us what you were trying to do, which API you called and what happened."
                required
              />
              <span className={cn("text-right text-xs", tooShort ? "text-red-600" : "text-subtle")}>
                {tooShort ? `At least ${DESCRIPTION_MIN} characters · ` : null}
                {form.description.length}/{DESCRIPTION_MAX}
              </span>
            </div>

            <Button type="submit" loading={submit.isPending}>
              <Send className="h-4 w-4" aria-hidden />
              Submit query
            </Button>
            <p className="text-xs text-subtle">
              Looking for quick answers? See the{" "}
              <Link href="/faqs" className="font-semibold text-brand-deep hover:underline">
                FAQs
              </Link>
              .
            </p>
          </form>
        </section>

        {/* ------------------------------------------------------- my queries */}
        <section className="rounded-2xl border border-hairline bg-white p-6 shadow-sm" aria-labelledby="my-queries">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="my-queries" className="text-base font-semibold text-nav-active">
              Your queries
            </h2>
            {queries.length ? (
              <span className="text-xs text-subtle">
                {queries.length} total · {openCount} awaiting a reply
              </span>
            ) : null}
          </div>

          {queriesQuery.isLoading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-subtle">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading your queries…
            </div>
          ) : queriesQuery.isError ? (
            <p className="py-16 text-center text-sm text-red-600">{(queriesQuery.error as Error).message}</p>
          ) : queries.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <Inbox className="h-9 w-9 text-slate-300" aria-hidden />
              <p className="text-sm font-semibold text-ink">No queries yet</p>
              <p className="max-w-sm text-sm text-subtle">
                Queries you raise appear here with their status and our reply.
              </p>
            </div>
          ) : (
            <ul className="mt-4 flex flex-col gap-3">
              {queries.map((item) => (
                <QueryItem
                  key={item.query_id}
                  item={item}
                  open={openId === item.query_id}
                  onToggle={() => setOpenId((current) => (current === item.query_id ? null : item.query_id))}
                />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function QueryItem({ item, open, onToggle }: { item: SupportQuery; open: boolean; onToggle: () => void }) {
  const panelId = `query-${item.query_id}`;
  return (
    <li className="rounded-xl border border-hairline">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-slate-50"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">{item.subject ?? "(no subject)"}</p>
          <p className="mt-0.5 text-xs text-subtle">
            {queryTypeLabel(item.query_type)} · {formatDateTime(item.added_date)}
          </p>
        </div>
        <QueryStatusBadge status={item.status} />
        <ChevronDown
          className={cn("mt-0.5 h-4 w-4 shrink-0 text-subtle transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open ? (
        <div id={panelId} className="border-t border-hairline px-4 py-3 text-sm">
          <p className="whitespace-pre-wrap break-words text-slate-700">{item.description}</p>
          {item.response ? (
            <div className="mt-3 rounded-lg border border-brand-bright/20 bg-brand-50 p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-brand-deep">
                <MessageSquareReply className="h-3.5 w-3.5" aria-hidden />
                Reply from the OAN team · {formatDateTime(item.responded_date)}
              </p>
              <p className="mt-1.5 whitespace-pre-wrap break-words text-slate-700">{item.response}</p>
            </div>
          ) : (
            <p className="mt-3 text-xs text-subtle">No reply yet. We will email you when the team answers.</p>
          )}
        </div>
      ) : null}
    </li>
  );
}

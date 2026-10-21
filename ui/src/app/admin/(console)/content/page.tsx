"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { PageHeader, SearchBox } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { EnabledBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { contentApi } from "@/lib/services/masters";
import { formatDate } from "@/lib/utils";
import type { Faq, TermSection } from "@/types/api";

type Tab = "faqs" | "terms" | "templates";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "faqs", label: "FAQs" },
  { id: "terms", label: "Terms & Conditions" },
  { id: "templates", label: "Email templates" },
];

interface FaqForm {
  faq_id?: number;
  type_id: string;
  question: string;
  answer: string;
  sort_order: number;
}

interface TermForm {
  table_id?: number;
  sidebar_title: string;
  term_content: string;
  sort_order: number;
}

export default function ContentPage() {
  const [tab, setTab] = React.useState<Tab>("faqs");

  return (
    <>
      <PageHeader
        title="CMS"
        description="Public-facing copy: help content, the participation terms and transactional emails."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "CMS" }]}
      />

      <div className="mb-6 flex flex-wrap gap-1 border-b border-hairline" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={
              tab === item.id
                ? "-mb-px border-b-2 border-nav-active px-4 py-2.5 text-sm font-semibold text-nav-active"
                : "-mb-px border-b-2 border-transparent px-4 py-2.5 text-sm text-subtle hover:text-ink"
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "faqs" ? <FaqsTab /> : null}
      {tab === "terms" ? <TermsTab /> : null}
      {tab === "templates" ? <TemplatesTab /> : null}
    </>
  );
}

function FaqsTab() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });
  const [form, setForm] = React.useState<FaqForm | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const faqsQuery = useQuery({
    queryKey: ["admin", "faqs", list.query],
    queryFn: () => contentApi.listFaqs(list.query),
  });

  const typesQuery = useQuery({
    queryKey: ["admin", "faq-types", "dropdown"],
    queryFn: contentApi.faqTypeDropdown,
    staleTime: CATALOG_STALE_MS,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "faqs"] });
  }

  const save = useMutation({
    mutationFn: (values: FaqForm) => {
      const payload = { ...values, type_id: Number(values.type_id) };
      return values.faq_id ? contentApi.updateFaq(payload) : contentApi.createFaq(payload);
    },
    onSuccess: (_data, values) => {
      notify(values.faq_id ? "FAQ updated." : "FAQ added.", "success");
      setForm(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggle = useMutation({
    mutationFn: (faq: Faq) => contentApi.toggleFaq(faq.faq_id),
    onSuccess: () => {
      notify("FAQ status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (faq: Faq) => contentApi.deleteFaq(faq.faq_id),
    onSuccess: () => {
      notify("FAQ deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<Faq>[] = [
    {
      key: "question",
      header: "Question",
      render: (row) => (
        <div>
          <p className="font-medium">{row.question}</p>
          <p className="line-clamp-1 text-xs text-muted-foreground">{row.answer ?? "—"}</p>
        </div>
      ),
    },
    { key: "faq_type", header: "FAQ Type", render: (row) => row.faq_type ?? "—" },
    { key: "sort_order", header: "Order By", render: (row) => row.sort_order },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel="FAQ"
          onEdit={() =>
            setForm({
              faq_id: row.faq_id,
              type_id: String(row.type_id),
              question: row.question,
              answer: row.answer ?? "",
              sort_order: row.sort_order,
            })
          }
          onDelete={async () => {
            const ok = await confirm({
              title: "Delete FAQ?",
              consequence: `"${row.question}" will be removed from the public FAQ page.`,
              confirmLabel: "Delete",
            });
            if (ok) {
              remove.mutate(row);
            }
          }}
          status={{
            checked: row.is_enabled,
            onChange: async (next) => {
              if (!next) {
                const ok = await confirm({
                  title: "Hide FAQ?",
                  consequence: "It will no longer be shown on the public FAQ page.",
                  confirmLabel: "Hide",
                  tone: "warning",
                });
                if (!ok) {
                  return;
                }
              }
              toggle.mutate(row);
            },
          }}
        />
      ),
    },
  ];

  return (
    <>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SearchBox value={list.searchInput} onChange={list.setSearchInput} placeholder="Search FAQs" />
        <Button onClick={() => setForm({ type_id: "", question: "", answer: "", sort_order: 0 })}>
          <Plus className="h-4 w-4" aria-hidden />
          Add FAQ
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={faqsQuery.data?.faqs ?? []}
        rowKey={(row) => row.faq_id}
        pagination={faqsQuery.data?.pagination}
        loading={faqsQuery.isLoading}
        noun="FAQs"
        emptyMessage="No FAQs have been published yet."
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {confirmDialog}

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{form?.faq_id ? "Edit FAQ" : "Add FAQ"}</DialogTitle>
            <DialogDescription>Shown on the public FAQ page.</DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="faq-type" required>
                  Category
                </Label>
                <Select
                  id="faq-type"
                  value={form.type_id}
                  onChange={(event) => setForm({ ...form, type_id: event.target.value })}
                  required
                >
                  <option value="">Select a category</option>
                  {typesQuery.data?.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="question" required>
                  Question
                </Label>
                <Input
                  id="question"
                  value={form.question}
                  onChange={(event) => setForm({ ...form, question: event.target.value })}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="answer" required>
                  Answer
                </Label>
                <Textarea
                  id="answer"
                  className="min-h-32"
                  value={form.answer}
                  onChange={(event) => setForm({ ...form, answer: event.target.value })}
                  required
                />
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  {form.faq_id ? "Save changes" : "Add FAQ"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function TermsTab() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });
  const [form, setForm] = React.useState<TermForm | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const remove = useMutation({
    mutationFn: (section: TermSection) => contentApi.deleteTerm(section.table_id),
    onSuccess: () => {
      notify("Section deleted.", "success");
      queryClient.invalidateQueries({ queryKey: ["admin", "terms"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const termsQuery = useQuery({
    queryKey: ["admin", "terms", list.query],
    queryFn: () => contentApi.listTerms(list.query),
  });

  const save = useMutation({
    mutationFn: (values: TermForm) => {
      const payload = {
        sidebar_title: values.sidebar_title,
        term_content: values.term_content,
        sort_order: values.sort_order,
      };
      return values.table_id
        ? contentApi.updateTerm({ ...payload, table_id: values.table_id })
        : contentApi.createTerm(payload);
    },
    onSuccess: () => {
      notify("Section saved.", "success");
      setForm(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "terms"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<TermSection>[] = [
    {
      key: "sidebar_title",
      header: "Section",
      render: (row) => <span className="font-medium">{row.sidebar_title}</span>,
    },
    { key: "sort_order", header: "Order By", render: (row) => row.sort_order },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    { key: "modify_date", header: "Updated Date", render: (row) => formatDate(row.modify_date) },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`section ${row.sidebar_title}`}
          onEdit={() =>
            setForm({
              table_id: row.table_id,
              sidebar_title: row.sidebar_title,
              term_content: row.term_content ?? "",
              sort_order: row.sort_order,
            })
          }
          onDelete={async () => {
            const ok = await confirm({
              title: "Delete Section?",
              consequence: `"${row.sidebar_title}" will be removed from the terms page.`,
              confirmLabel: "Delete",
            });
            if (ok) {
              remove.mutate(row);
            }
          }}
        />
      ),
    },
  ];

  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setForm({ sidebar_title: "", term_content: "", sort_order: 0 })}>
          <Plus className="h-4 w-4" aria-hidden />
          Add Section
        </Button>
      </div>
      {confirmDialog}

      <DataTable
        columns={columns}
        rows={termsQuery.data?.terms ?? []}
        rowKey={(row) => row.table_id}
        pagination={termsQuery.data?.pagination}
        loading={termsQuery.isLoading}
        emptyMessage="No terms sections have been created yet."
        onPageChange={list.setPage}
      />

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{form?.table_id ? "Edit section" : "Add section"}</DialogTitle>
            <DialogDescription>
              Content accepts HTML and is rendered on the public terms page.
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="sidebar_title" required>
                  Section title
                </Label>
                <Input
                  id="sidebar_title"
                  value={form.sidebar_title}
                  onChange={(event) => setForm({ ...form, sidebar_title: event.target.value })}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="term_content" required>
                  Content
                </Label>
                <Textarea
                  id="term_content"
                  className="min-h-64 font-mono text-xs"
                  value={form.term_content}
                  onChange={(event) => setForm({ ...form, term_content: event.target.value })}
                  required
                />
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  Save section
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

function TemplatesTab() {
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });

  const templatesQuery = useQuery({
    queryKey: ["admin", "email-templates", list.query],
    queryFn: () => contentApi.listEmailTemplates(list.query),
  });

  const columns: Column<Record<string, unknown>>[] = [
    {
      key: "template_name",
      header: "Template",
      render: (row) => (
        <div>
          <p className="font-medium">{String(row.template_name ?? "")}</p>
          <p className="font-mono text-xs text-muted-foreground">{String(row.template_code ?? "")}</p>
        </div>
      ),
    },
    { key: "subject", header: "Subject", render: (row) => <span className="text-sm">{String(row.subject ?? "—")}</span> },
    {
      key: "variables",
      header: "Placeholders",
      render: (row) => (
        <span className="font-mono text-xs text-muted-foreground">
          {Array.isArray(row.variables) && row.variables.length > 0
            ? (row.variables as string[]).join(", ")
            : "—"}
        </span>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={templatesQuery.data?.templates ?? []}
      rowKey={(row) => String(row.template_id)}
      pagination={templatesQuery.data?.pagination}
      loading={templatesQuery.isLoading}
      noun="templates"
      emptyMessage="No email templates have been seeded yet."
      onPageChange={list.setPage}
    />
  );
}

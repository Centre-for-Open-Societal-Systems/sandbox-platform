"use client";

import * as React from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Send, SquarePen } from "lucide-react";

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
import type { EmailTemplate, Faq, TermSection } from "@/types/api";

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
        title="Content Management"
        description="Public-facing copy: help content, the participation terms and transactional emails."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Content Management" }]}
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
    void queryClient.invalidateQueries({ queryKey: ["admin", "faqs"] });
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
      void queryClient.invalidateQueries({ queryKey: ["admin", "terms"] });
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
      void queryClient.invalidateQueries({ queryKey: ["admin", "terms"] });
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

/** Placeholders the services fill in; any other {{name}} stays as typed. */
const PLACEHOLDERS: Array<{ name: string; hint: string }> = [
  { name: "name", hint: "Recipient's name" },
  { name: "portal_url", hint: "Portal address" },
  { name: "otp", hint: "Verification code (OTP email)" },
  { name: "validity_minutes", hint: "Code validity (OTP email)" },
  { name: "environment", hint: "UAT / PRODUCTION" },
  { name: "reason", hint: "Rejection reason" },
  { name: "token", hint: "Link token (password emails)" },
  { name: "subject", hint: "Query subject (query reply)" },
  { name: "response", hint: "Reply text (query reply)" },
];

const PREVIEW_STYLE =
  "body{margin:0;padding:24px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.5;color:#1f2937;background:#fff}";

/** The rendered email in an isolated frame: no scripts, no access to the console. */
function EmailPreview({ subject, html, loading }: { subject?: string; html?: string; loading?: boolean }) {
  const srcDoc = `<!doctype html><html><head><meta charset="utf-8"><style>${PREVIEW_STYLE}</style></head><body>${html ?? ""}</body></html>`;
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-hairline bg-white">
      <div className="border-b border-hairline bg-surface-soft px-4 py-2.5 text-sm">
        <span className="text-subtle">Subject: </span>
        <span className="font-medium">{subject || "—"}</span>
        {loading ? <span className="ml-2 text-xs text-subtle">updating…</span> : null}
      </div>
      <iframe title="Email preview" sandbox="" srcDoc={srcDoc} className="min-h-[420px] w-full flex-1 bg-white" />
    </div>
  );
}

interface TemplateForm {
  template_id: number;
  template_code: string;
  template_name: string;
  subject: string;
  body_text: string;
}

function TemplatesTab() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "sort_order", sortDir: "asc" });
  const [viewing, setViewing] = React.useState<EmailTemplate | null>(null);
  const [form, setForm] = React.useState<TemplateForm | null>(null);
  const [testing, setTesting] = React.useState<EmailTemplate | null>(null);
  const [testTo, setTestTo] = React.useState("");
  const bodyRef = React.useRef<HTMLTextAreaElement>(null);

  const templatesQuery = useQuery({
    queryKey: ["admin", "email-templates", list.query],
    queryFn: () => contentApi.listEmailTemplates(list.query),
  });

  // Preview of what is open: the text being typed (edit, debounced) or the saved template (view).
  const subject = form ? form.subject : (viewing?.subject ?? "");
  const body = form ? form.body_text : (viewing?.body_text ?? "");
  const open = form !== null || viewing !== null;
  const [debounced, setDebounced] = React.useState({ subject, body });
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced({ subject, body }), form ? 400 : 0);
    return () => clearTimeout(timer);
  }, [subject, body, form]);
  const previewQuery = useQuery({
    queryKey: ["admin", "email-templates", "preview", debounced.subject, debounced.body],
    queryFn: () => contentApi.previewEmailTemplate({ subject: debounced.subject, body_text: debounced.body }),
    enabled: open,
    placeholderData: keepPreviousData,
  });

  const save = useMutation({
    mutationFn: (values: TemplateForm) => contentApi.saveEmailTemplate({ ...values }),
    onSuccess: () => {
      notify("Email template saved.", "success");
      setForm(null);
      void queryClient.invalidateQueries({ queryKey: ["admin", "email-templates"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const sendTest = useMutation({
    mutationFn: (values: { to_email: string; template_code: string }) => contentApi.sendTestMail(values),
    onSuccess: (result, values) => {
      if (result.sent) {
        notify(`Test email sent to ${values.to_email}.`, "success");
        setTesting(null);
      } else {
        notify("Mail delivery is switched off (MAIL_ENABLED / SMTP_HOST): nothing was sent.", "error");
      }
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function edit(row: EmailTemplate) {
    setViewing(null);
    setForm({
      template_id: row.template_id,
      template_code: row.template_code,
      template_name: row.template_name,
      subject: row.subject ?? "",
      body_text: row.body_text ?? "",
    });
  }

  function insertPlaceholder(name: string) {
    if (!form) {
      return;
    }
    const token = `{{${name}}}`;
    const area = bodyRef.current;
    const start = area?.selectionStart ?? form.body_text.length;
    const end = area?.selectionEnd ?? start;
    setForm({ ...form, body_text: form.body_text.slice(0, start) + token + form.body_text.slice(end) });
    requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(start + token.length, start + token.length);
    });
  }

  const columns: Column<EmailTemplate>[] = [
    {
      key: "template_name",
      header: "Template",
      render: (row) => (
        <div>
          <p className="font-medium">{row.template_name}</p>
          <p className="font-mono text-xs text-muted-foreground">{row.template_code}</p>
        </div>
      ),
    },
    { key: "subject", header: "Subject", render: (row) => <span className="text-sm">{row.subject ?? "—"}</span> },
    {
      key: "variables",
      header: "Placeholders",
      render: (row) => (
        <span className="font-mono text-xs text-muted-foreground">
          {row.variables && row.variables.length > 0 ? row.variables.join(", ") : "—"}
        </span>
      ),
    },
    { key: "modify_date", header: "Updated Date", render: (row) => formatDate(row.modify_date) },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`template ${row.template_name}`}
          onView={() => setViewing(row)}
          onEdit={() => edit(row)}
          extra={[{ icon: Send, label: `Send a test of ${row.template_name}`, onClick: () => setTesting(row) }]}
        />
      ),
    },
  ];

  return (
    <>
      <p className="mb-4 text-sm text-subtle">
        Transactional emails the platform sends. Edit the subject and the HTML body (inline styles work best in email
        clients); <code className="font-mono">{"{{placeholders}}"}</code> are filled in when the email is sent.
      </p>
      <DataTable
        columns={columns}
        rows={templatesQuery.data?.templates ?? []}
        rowKey={(row) => row.template_id}
        pagination={templatesQuery.data?.pagination}
        loading={templatesQuery.isLoading}
        noun="templates"
        emptyMessage="No email templates have been seeded yet."
        onPageChange={list.setPage}
      />

      {/* ---------- view ---------- */}
      <Dialog open={viewing !== null} onOpenChange={(next) => !next && setViewing(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{viewing?.template_name}</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{viewing?.template_code}</span> · shown with sample values
            </DialogDescription>
          </DialogHeader>
          <div className="h-[60vh]">
            <EmailPreview
              subject={previewQuery.data?.subject}
              html={previewQuery.data?.body_html}
              loading={previewQuery.isFetching}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => viewing && setTesting(viewing)}>
              <Send className="h-4 w-4" aria-hidden />
              Send test
            </Button>
            <Button type="button" onClick={() => viewing && edit(viewing)}>
              <SquarePen className="h-4 w-4" aria-hidden />
              Edit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---------- edit ---------- */}
      <Dialog open={form !== null} onOpenChange={(next) => !next && setForm(null)}>
        <DialogContent className="max-w-6xl">
          <DialogHeader>
            <DialogTitle>Edit email template</DialogTitle>
            <DialogDescription>
              <span className="font-mono">{form?.template_code}</span> · the preview updates as you type (sample
              values).
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="grid gap-5 lg:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="flex min-w-0 flex-col gap-4">
                <div className="space-y-2">
                  <Label htmlFor="template_name" required>
                    Name
                  </Label>
                  <Input
                    id="template_name"
                    value={form.template_name}
                    onChange={(event) => setForm({ ...form, template_name: event.target.value })}
                    required
                    minLength={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="template_subject" required>
                    Subject
                  </Label>
                  <Input
                    id="template_subject"
                    value={form.subject}
                    onChange={(event) => setForm({ ...form, subject: event.target.value })}
                    required
                    minLength={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="template_body" required>
                    Body (HTML)
                  </Label>
                  <div className="flex flex-wrap gap-1.5" aria-label="Insert a placeholder">
                    {PLACEHOLDERS.map((item) => (
                      <button
                        key={item.name}
                        type="button"
                        title={item.hint}
                        onClick={() => insertPlaceholder(item.name)}
                        className="rounded-md border border-hairline bg-white px-2 py-0.5 font-mono text-xs text-subtle hover:border-brand-300 hover:text-ink"
                      >
                        {`{{${item.name}}}`}
                      </button>
                    ))}
                  </div>
                  <Textarea
                    id="template_body"
                    ref={bodyRef}
                    className="min-h-[360px] font-mono text-xs"
                    value={form.body_text}
                    onChange={(event) => setForm({ ...form, body_text: event.target.value })}
                    spellCheck={false}
                    required
                  />
                </div>
              </div>

              <div className="flex min-h-[480px] min-w-0 flex-col gap-2">
                <span className="text-sm font-medium">Preview</span>
                <EmailPreview
                  subject={previewQuery.data?.subject}
                  html={previewQuery.data?.body_html}
                  loading={previewQuery.isFetching}
                />
              </div>

              <DialogFooter className="lg:col-span-2">
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  Save template
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* ---------- test mail ---------- */}
      <Dialog open={testing !== null} onOpenChange={(next) => !next && setTesting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send a test email</DialogTitle>
            <DialogDescription>Sends the saved version of “{testing?.template_name}” with sample values.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (testing) {
                sendTest.mutate({ to_email: testTo, template_code: testing.template_code });
              }
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="test_to" required>
                Send to
              </Label>
              <Input
                id="test_to"
                type="email"
                value={testTo}
                onChange={(event) => setTestTo(event.target.value)}
                placeholder="you@example.org"
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setTesting(null)}>
                Cancel
              </Button>
              <Button type="submit" loading={sendTest.isPending}>
                <Send className="h-4 w-4" aria-hidden />
                Send test
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

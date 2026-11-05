"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MethodBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { catalogApi } from "@/lib/services/catalog";
import { participantApi } from "@/lib/services/participant";

const CERTIFICATE_ACCEPT = ".pem,.crt,.cer";
const DOCUMENT_ACCEPT = ".pdf,.png,.jpg,.jpeg";

const EMPTY = {
  publicKey: "",
  endpointIds: [] as number[],
  dailyVolume: "",
  integrationContact: "",
  escalationContact: "",
  remarks: "",
  declaration: false,
};

interface ProductionRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the submitted form; the caller sends it and closes on success. */
  onSubmit: (formData: FormData) => void;
  submitting: boolean;
}

/**
 * "Move to Production" form, following the reference portal: security
 * artefacts, the end-points to go live with, expected volume and contacts.
 * Organisation and contact details come from the profile, so they are not
 * asked again.
 */
export function ProductionRequestDialog({ open, onOpenChange, onSubmit, submitting }: ProductionRequestDialogProps) {
  const { notify } = useToast();
  const [form, setForm] = React.useState(EMPTY);
  const [certificate, setCertificate] = React.useState<File | null>(null);
  const [document, setDocument] = React.useState<File | null>(null);
  const [endpointSearch, setEndpointSearch] = React.useState("");
  const [selectedOnly, setSelectedOnly] = React.useState(false);
  const [expanded, setExpanded] = React.useState<Set<number>>(new Set());

  const menuQuery = useQuery({
    queryKey: ["participant", "catalog", "menu"],
    queryFn: catalogApi.portalMenu,
    staleTime: CATALOG_STALE_MS,
    enabled: open,
  });
  const profileQuery = useQuery({
    queryKey: ["participant", "profile"],
    queryFn: participantApi.profile,
    enabled: open,
  });

  const term = endpointSearch.trim().toLowerCase();
  // Searching or "selected only" shows every match, so all groups open.
  const forceOpen = Boolean(term) || selectedOnly;
  const products = (menuQuery.data ?? [])
    .map((product) => ({
      ...product,
      endpoints: product.endpoints.filter(
        (endpoint) =>
          (!selectedOnly || form.endpointIds.includes(endpoint.endpoint_id)) &&
          (!term ||
            (product.display_name ?? product.product_name).toLowerCase().includes(term) ||
            (endpoint.display_name ?? "").toLowerCase().includes(term) ||
            (endpoint.endpoint_url ?? "").toLowerCase().includes(term)),
      ),
    }))
    .filter((product) => product.endpoints.length > 0);

  function toggleEndpoints(endpointIds: number[], on: boolean) {
    setForm((current) => {
      const next = new Set(current.endpointIds);
      endpointIds.forEach((id) => (on ? next.add(id) : next.delete(id)));
      return { ...current, endpointIds: [...next] };
    });
  }

  function toggleExpanded(productId: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(productId)) next.delete(productId);
      else next.add(productId);
      return next;
    });
  }

  function handleOpenChange(next: boolean) {
    if (!next && !submitting) {
      setForm(EMPTY);
      setCertificate(null);
      setDocument(null);
      setEndpointSearch("");
      setSelectedOnly(false);
      setExpanded(new Set());
    }
    onOpenChange(next);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.publicKey.trim()) {
      notify("Paste the public key you will use in production.", "warning");
      return;
    }
    if (form.endpointIds.length === 0) {
      notify("Select at least one end-point to move to production.", "warning");
      return;
    }
    if (!form.declaration) {
      notify("Please accept the self-declaration.", "warning");
      return;
    }

    const details: Record<string, unknown> = {
      public_key: form.publicKey.trim(),
      endpoint_ids: form.endpointIds,
    };
    if (form.dailyVolume) details.daily_volume = Number(form.dailyVolume);
    if (form.integrationContact.trim()) details.integration_contact = form.integrationContact.trim();
    if (form.escalationContact.trim()) details.escalation_contact = form.escalationContact.trim();

    const formData = new FormData();
    formData.append("target_environment", "PRODUCTION");
    formData.append("extra_data", JSON.stringify(details));
    if (form.remarks.trim()) formData.append("remarks", form.remarks.trim());
    if (certificate) formData.append("certificate", certificate);
    if (document) formData.append("document", document);
    onSubmit(formData);
  }

  const profile = profileQuery.data;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Move to Production</DialogTitle>
          <DialogDescription>
            Tell us how you will use the APIs in production. An administrator reviews the request and emails you
            the decision.
          </DialogDescription>
        </DialogHeader>

        <form id="production-request" onSubmit={handleSubmit} className="flex flex-col gap-6">
          {/* --------------------------------------------------- organisation */}
          <section>
            <h3 className="mb-2 text-sm font-semibold text-nav-active">General information</h3>
            <dl className="grid gap-x-6 gap-y-2 rounded-xl border border-hairline bg-surface-soft p-4 text-sm sm:grid-cols-2">
              {[
                ["Organisation", profile?.company_name],
                ["Service domain", profile?.service_domain],
                ["Contact person", profile?.authorized_person_name],
                ["Designation", profile?.authorized_person_designation],
                ["Email", profile?.email_id],
                ["Mobile", profile?.mobile_number],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-2">
                  <dt className="shrink-0 text-subtle">{label}:</dt>
                  <dd className="truncate font-medium text-ink">{value || "—"}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-1.5 text-xs text-subtle">Taken from your profile. Update the profile to change them.</p>
          </section>

          {/* ------------------------------------------------------- security */}
          <section className="flex flex-col gap-4">
            <h3 className="text-sm font-semibold text-nav-active">Security artefacts</h3>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-public-key" required>
                Public key
              </Label>
              <Textarea
                id="prod-public-key"
                rows={4}
                maxLength={10000}
                value={form.publicKey}
                onChange={(event) => setForm({ ...form, publicKey: event.target.value })}
                placeholder="-----BEGIN PUBLIC KEY-----"
                className="font-mono text-xs"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-certificate">Certificate (.pem, .crt or .cer)</Label>
              <Input
                id="prod-certificate"
                type="file"
                accept={CERTIFICATE_ACCEPT}
                onChange={(event) => setCertificate(event.target.files?.[0] ?? null)}
              />
              <span className="text-xs text-subtle">Never upload a private key.</span>
            </div>
          </section>

          {/* ------------------------------------------------------ end-points */}
          <section className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-nav-active">
                End-points <span className="text-destructive">*</span>
              </h3>
              <span className="text-xs text-subtle">{form.endpointIds.length} selected</span>
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" aria-hidden />
              <Input
                value={endpointSearch}
                onChange={(event) => setEndpointSearch(event.target.value)}
                placeholder="Search products and end-points"
                aria-label="Search end-points"
                className="pl-9"
              />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedOnly}
                  onChange={(event) => setSelectedOnly(event.target.checked)}
                  className="h-4 w-4 accent-[var(--color-brand-bright)]"
                />
                Selected only
              </label>
              <div className="flex gap-3">
                <button
                  type="button"
                  className="text-nav-active hover:underline disabled:opacity-50"
                  disabled={forceOpen}
                  onClick={() => setExpanded(new Set(products.map((p) => p.product_id)))}
                >
                  Expand all
                </button>
                <button
                  type="button"
                  className="text-nav-active hover:underline disabled:opacity-50"
                  disabled={forceOpen}
                  onClick={() => setExpanded(new Set())}
                >
                  Collapse all
                </button>
              </div>
            </div>
            {/* relative: contains the sr-only (absolute) legends so they don't stretch the dialog's scroll area */}
            <div className="relative max-h-80 overflow-y-auto rounded-xl border border-hairline">
              {menuQuery.isLoading ? (
                <p className="p-4 text-sm text-subtle">Loading the catalogue…</p>
              ) : products.length === 0 ? (
                <p className="p-4 text-sm text-subtle">
                  {selectedOnly && !term ? "No end-points selected yet." : "No end-points match."}
                </p>
              ) : (
                products.map((product) => {
                  const name = product.display_name ?? product.product_name;
                  const ids = product.endpoints.map((e) => e.endpoint_id);
                  const count = ids.filter((id) => form.endpointIds.includes(id)).length;
                  const isOpen = forceOpen || expanded.has(product.product_id);
                  const panelId = `prod-group-${product.product_id}`;
                  return (
                    <fieldset key={product.product_id} className="border-b border-hairline last:border-b-0">
                      <legend className="sr-only">{name}</legend>
                      <div className="sticky top-0 z-10 flex items-center gap-3 bg-surface-soft px-4 py-2 text-sm">
                        <input
                          type="checkbox"
                          aria-label={`Select all end-points of ${name}`}
                          checked={count > 0 && count === ids.length}
                          ref={(el) => {
                            if (el) el.indeterminate = count > 0 && count < ids.length;
                          }}
                          onChange={(event) => toggleEndpoints(ids, event.target.checked)}
                          className="h-4 w-4 shrink-0 accent-[var(--color-brand-bright)]"
                        />
                        <button
                          type="button"
                          aria-expanded={isOpen}
                          aria-controls={panelId}
                          disabled={forceOpen}
                          onClick={() => toggleExpanded(product.product_id)}
                          className="flex min-w-0 flex-1 items-center gap-2 text-left font-semibold text-nav-active"
                        >
                          <ChevronRight
                            className={`h-4 w-4 shrink-0 text-subtle transition-transform ${isOpen ? "rotate-90" : ""}`}
                            aria-hidden
                          />
                          <span className="truncate">{name}</span>
                          <span className="ml-auto shrink-0 text-xs font-normal text-subtle">
                            {count} / {ids.length} selected
                          </span>
                        </button>
                      </div>
                      {isOpen ? (
                        <div id={panelId}>
                          {product.endpoints.map((endpoint) => (
                            <label
                              key={endpoint.endpoint_id}
                              className="flex cursor-pointer items-center gap-3 px-4 py-2 pl-11 text-sm hover:bg-slate-50"
                            >
                              <input
                                type="checkbox"
                                checked={form.endpointIds.includes(endpoint.endpoint_id)}
                                onChange={(event) => toggleEndpoints([endpoint.endpoint_id], event.target.checked)}
                                className="h-4 w-4 shrink-0 accent-[var(--color-brand-bright)]"
                              />
                              <MethodBadge method={endpoint.method} />
                              <span className="flex min-w-0 flex-1 flex-col">
                                {endpoint.display_name ? (
                                  <span className="truncate">{endpoint.display_name}</span>
                                ) : null}
                                <code className="truncate font-mono text-xs text-subtle" title={endpoint.endpoint_url ?? ""}>
                                  {endpoint.endpoint_url}
                                </code>
                              </span>
                            </label>
                          ))}
                        </div>
                      ) : null}
                    </fieldset>
                  );
                })
              )}
            </div>
          </section>

          {/* ------------------------------------------------------ additional */}
          <section className="grid gap-4 sm:grid-cols-2">
            <h3 className="text-sm font-semibold text-nav-active sm:col-span-2">Additional information</h3>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-volume">Expected daily volume (calls)</Label>
              <Input
                id="prod-volume"
                type="number"
                min={0}
                inputMode="numeric"
                value={form.dailyVolume}
                onChange={(event) => setForm({ ...form, dailyVolume: event.target.value })}
                placeholder="e.g. 5000"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-document">Data retention policy (PDF or image)</Label>
              <Input
                id="prod-document"
                type="file"
                accept={DOCUMENT_ACCEPT}
                onChange={(event) => setDocument(event.target.files?.[0] ?? null)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-integration">Integration contact person</Label>
              <Input
                id="prod-integration"
                maxLength={255}
                value={form.integrationContact}
                onChange={(event) => setForm({ ...form, integrationContact: event.target.value })}
                placeholder="Name, email or phone"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-escalation">Escalation contact</Label>
              <Input
                id="prod-escalation"
                maxLength={255}
                value={form.escalationContact}
                onChange={(event) => setForm({ ...form, escalationContact: event.target.value })}
                placeholder="Name, email or phone"
              />
            </div>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label htmlFor="prod-remarks">Remarks</Label>
              <Textarea
                id="prod-remarks"
                rows={3}
                maxLength={2000}
                value={form.remarks}
                onChange={(event) => setForm({ ...form, remarks: event.target.value })}
                placeholder="Anything the reviewer should know"
              />
            </div>
          </section>

          <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-[#ece8dc] bg-[#fbfaf6] p-4 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.declaration}
              onChange={(event) => setForm({ ...form, declaration: event.target.checked })}
              className="mt-0.5 h-4 w-4 accent-[var(--color-brand-bright)]"
            />
            <span>
              I declare that the information above is correct and that production data will be used only for the
              purpose described, in line with the Terms &amp; Conditions.
            </span>
          </label>
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="production-request" loading={submitting}>
            Submit request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

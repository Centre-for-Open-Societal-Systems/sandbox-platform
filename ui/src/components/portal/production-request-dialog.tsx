"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileDropzone } from "@/components/ui/file-dropzone";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { participantApi } from "@/lib/services/participant";

const CERTIFICATE_ACCEPT = [".pem", ".crt", ".cer", ".der"];
const DOCUMENT_ACCEPT = [".pdf", ".png", ".jpg", ".jpeg"];
const PUBLIC_KEY_PLACEHOLDER = ["-----BEGIN PUBLIC KEY-----", "…", "-----END PUBLIC KEY-----"].join("\n");

const EMPTY = {
  publicKey: "",
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
 * "Move to Production" form for the account, following the reference portal:
 * security artefacts, expected volume and contacts. Organisation and contact
 * details come from the profile, so they are not asked again. Which APIs go
 * live is not asked here: once approved, each UAT app is taken to production
 * from My Apps ("Move to production"), with its API products.
 */
export function ProductionRequestDialog({ open, onOpenChange, onSubmit, submitting }: ProductionRequestDialogProps) {
  const { notify } = useToast();
  const [form, setForm] = React.useState(EMPTY);
  const [certificate, setCertificate] = React.useState<File | null>(null);
  const [document, setDocument] = React.useState<File | null>(null);

  const profileQuery = useQuery({
    queryKey: ["participant", "profile"],
    queryFn: participantApi.profile,
    enabled: open,
  });

  function handleOpenChange(next: boolean) {
    if (!next && !submitting) {
      setForm(EMPTY);
      setCertificate(null);
      setDocument(null);
    }
    onOpenChange(next);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const pasted = form.publicKey.trim();
    if (!certificate && !pasted) {
      notify("Upload your certificate, or paste your public key.", "warning");
      return;
    }
    if (pasted.includes("PRIVATE KEY")) {
      notify("That is a private key. Never share it: paste the public key or upload the certificate.", "error");
      return;
    }
    if (!form.declaration) {
      notify("Please accept the self-declaration.", "warning");
      return;
    }

    const details: Record<string, unknown> = {};
    // The certificate carries the key; a pasted key is checked against it on the server.
    if (pasted) details.public_key = pasted;
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
            <div>
              <h3 className="text-sm font-semibold text-nav-active">
                Signing key <span className="text-destructive">*</span>
              </h3>
              <p className="mt-0.5 text-xs text-subtle">
                Your X.509 certificate (recommended), or only its public key. The certificate already holds the public
                key, so one is enough. Accepted: RSA 2048 bits or more, EC P-256 / P-384, Ed25519.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-certificate">Certificate</Label>
              <FileDropzone
                id="prod-certificate"
                accept={CERTIFICATE_ACCEPT}
                value={certificate}
                onChange={setCertificate}
                hint="PEM, CRT, CER or DER certificate. Never upload a private key"
                disabled={submitting}
              />
            </div>
            <div className="flex items-center gap-3 text-xs font-semibold text-subtle uppercase" aria-hidden>
              <span className="h-px flex-1 bg-hairline" />
              or
              <span className="h-px flex-1 bg-hairline" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="prod-public-key">Public key</Label>
              <Textarea
                id="prod-public-key"
                rows={4}
                maxLength={10000}
                value={form.publicKey}
                onChange={(event) => setForm({ ...form, publicKey: event.target.value })}
                placeholder={PUBLIC_KEY_PLACEHOLDER}
                className="font-mono text-xs"
                aria-describedby="prod-public-key-hint"
              />
              <span id="prod-public-key-hint" className="text-xs text-subtle">
                {certificate
                  ? "Optional with a certificate; if you paste it, it must be the certificate's key."
                  : "Only when you have no certificate."}
              </span>
            </div>
            <details className="rounded-lg border border-hairline bg-surface-soft px-3 py-2 text-xs text-ink">
              <summary className="cursor-pointer font-semibold text-nav-active">How do I get these?</summary>
              <pre className="mt-2 overflow-x-auto font-mono text-[0.7rem] leading-relaxed whitespace-pre">{`# Public key from your certificate
openssl x509 -in certificate.crt -pubkey -noout > public_key.pem

# Public key from your private key (the private key never leaves you)
openssl pkey -in private.pem -pubout -out public_key.pem

# New key pair and self-signed certificate (or have a CA sign one)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out private.pem
openssl req -new -x509 -key private.pem -days 365 -subj "/CN=your-domain/O=Your organisation" -out certificate.crt`}</pre>
            </details>
          </section>

          {/* --------------------------------------------------------- apps */}
          <p className="flex gap-2 rounded-lg border border-hairline bg-surface-soft p-3 text-sm text-ink">
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-brand-bright" aria-hidden />
            <span>
              Once production access is approved, open <strong>My Apps</strong> and choose{" "}
              <strong>Move to production</strong> on each app you want to take live. Its API products go with it, an
              administrator approves them, and the production app gets its own API key and secret.
            </span>
          </p>

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
              <Label htmlFor="prod-document">Data retention policy</Label>
              <FileDropzone
                id="prod-document"
                accept={DOCUMENT_ACCEPT}
                value={document}
                onChange={setDocument}
                hint="PDF, PNG or JPG"
                disabled={submitting}
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

"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Building2,
  CalendarDays,
  Check,
  CheckCircle2,
  Circle,
  Eye,
  EyeOff,
  FileText,
  Globe2,
  KeyRound,
  Lock,
  Mail,
  MapPin,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { ProductionRequestDialog } from "@/components/portal/production-request-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { REFERENCE_STALE_MS } from "@/lib/cache-times";
import { publicApi, participantApi } from "@/lib/services/participant";
import { participantSession } from "@/lib/session";
import { cn, formatDate } from "@/lib/utils";
import type { Participant } from "@/types/api";

/**
 * Every field the API requires before a UAT request is accepted. Kept in step
 * with `REQUIRED_FOR_UAT` in `app/services/user_service.py` - if the two drift,
 * the form lets people submit a request the API will refuse.
 */
const REQUIRED_FOR_UAT = [
  "profile_type",
  "company_name",
  "organization_registration_number",
  "admin_area_code_l1",
  "participant_type_id",
  "service_domain",
  "authorized_person_name",
  "authorized_person_designation",
  "description",
] as const;

/** Checklist labels for the completeness card; keys match the form field ids. */
const REQUIRED_LABELS: Record<(typeof REQUIRED_FOR_UAT)[number], string> = {
  profile_type: "Registering as",
  company_name: "Company name",
  organization_registration_number: "Registration number",
  admin_area_code_l1: "Region",
  participant_type_id: "Network role",
  service_domain: "Service domain",
  authorized_person_name: "Authorised contact",
  authorized_person_designation: "Designation",
  description: "Service description",
};

interface ProfileForm {
  profile_type: string;
  company_name: string;
  organization_registration_number: string;
  admin_area_code_l1: string;
  admin_area_code_l2: string;
  participant_type_id: string;
  service_domain: string;
  operating_area: string;
  authorized_person_name: string;
  authorized_person_designation: string;
  authorized_person_address: string;
  website: string;
  description: string;
}

const EMPTY_FORM: ProfileForm = {
  profile_type: "",
  company_name: "",
  organization_registration_number: "",
  admin_area_code_l1: "",
  admin_area_code_l2: "",
  participant_type_id: "",
  service_domain: "",
  operating_area: "",
  authorized_person_name: "",
  authorized_person_designation: "",
  authorized_person_address: "",
  website: "",
  description: "",
};

type AccessTone = "success" | "info" | "warning" | "danger" | "neutral";

/** Status of one environment, in the order a participant moves through them. */
function environmentRows(profile: Participant | undefined) {
  const rows: Array<{ name: string; label: string; tone: AccessTone }> = [
    {
      name: "Sandbox",
      label: profile?.is_sandbox_approved ? "Active" : "Pending approval",
      tone: profile?.is_sandbox_approved ? "success" : "warning",
    },
    {
      name: "UAT",
      label: profile?.is_uat_approved
        ? "Active"
        : profile?.is_uat_rejected
          ? "Rejected"
          : profile?.is_uat_requested
            ? "Under review"
            : "Not requested",
      tone: profile?.is_uat_approved
        ? "success"
        : profile?.is_uat_rejected
          ? "danger"
          : profile?.is_uat_requested
            ? "warning"
            : "neutral",
    },
    {
      name: "Production",
      label: profile?.is_prod_approved
        ? "Active"
        : profile?.is_prod_rejected
          ? "Rejected"
          : profile?.is_prod_requested
            ? "Under review"
            : profile?.is_uat_approved
              ? "Not requested"
              : "Locked",
      tone: profile?.is_prod_approved
        ? "success"
        : profile?.is_prod_rejected
          ? "danger"
          : profile?.is_prod_requested
            ? "warning"
            : "neutral",
    },
  ];
  return rows;
}

export default function ParticipantProfilePage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const session = participantSession.get();
  const [form, setForm] = React.useState<ProfileForm | null>(null);
  const [passwords, setPasswords] = React.useState({ old_password: "", new_password: "" });
  const [showPasswords, setShowPasswords] = React.useState(false);

  const profileQuery = useQuery({ queryKey: ["participant", "profile"], queryFn: participantApi.profile });
  const networkRoles = useQuery({
    queryKey: ["public", "masters", "participant-type"],
    queryFn: () => publicApi.masters("participant-type"),
    staleTime: REFERENCE_STALE_MS,
  });
  const serviceDomains = useQuery({
    queryKey: ["public", "masters", "service-domain"],
    queryFn: () => publicApi.masters("service-domain"),
    staleTime: REFERENCE_STALE_MS,
  });
  const regions = useQuery({
    queryKey: ["public", "areas", 1],
    queryFn: () => publicApi.areas(1),
    staleTime: REFERENCE_STALE_MS,
  });

  // Populate the editable copy once the stored profile arrives (guarded, so
  // this runs once - React allows this state adjustment during render).
  {
    const profile = profileQuery.data;
    if (profile && form === null) {
      setForm({
        ...EMPTY_FORM,
        profile_type: profile.profile_type ?? "",
        company_name: profile.company_name ?? "",
        organization_registration_number: profile.organization_registration_number ?? "",
        admin_area_code_l1: profile.admin_area_code_l1 ?? "",
        admin_area_code_l2: profile.admin_area_code_l2 ?? "",
        participant_type_id: profile.participant_type_id ? String(profile.participant_type_id) : "",
        service_domain: profile.service_domain ?? "",
        operating_area: profile.operating_area ?? "",
        authorized_person_name: profile.authorized_person_name ?? "",
        authorized_person_designation: profile.authorized_person_designation ?? "",
        authorized_person_address: profile.authorized_person_address ?? "",
        website: profile.website ?? "",
        description: profile.description ?? "",
      });
    }
  }

  const save = useMutation({
    mutationFn: (values: ProfileForm) => {
      const formData = new FormData();
      for (const [key, value] of Object.entries(values)) {
        if (value) {
          formData.append(key, value);
        }
      }
      return participantApi.updateProfile(formData);
    },
    onSuccess: (updated) => {
      notify(
        updated.is_profile_complete
          ? "Profile saved. You can now request UAT access."
          : "Profile saved.",
        "success",
      );
      queryClient.invalidateQueries({ queryKey: ["participant"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const [productionFormOpen, setProductionFormOpen] = React.useState(false);

  const requestPromotion = useMutation({
    mutationFn: ({ formData }: { environment: "UAT" | "PRODUCTION"; formData: FormData }) =>
      participantApi.requestPromotion(formData),
    onSuccess: (_result, { environment }) => {
      notify(`${environment} access request submitted for review.`, "success");
      setProductionFormOpen(false);
      queryClient.invalidateQueries({ queryKey: ["participant"] });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function requestUat() {
    const formData = new FormData();
    formData.append("target_environment", "UAT");
    requestPromotion.mutate({ environment: "UAT", formData });
  }

  const changePassword = useMutation({
    mutationFn: () => participantApi.changePassword(passwords.old_password, passwords.new_password),
    onSuccess: () => {
      notify("Password changed successfully.", "success");
      setPasswords({ old_password: "", new_password: "" });
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const profile = profileQuery.data;
  const missing = form ? REQUIRED_FOR_UAT.filter((field) => !form[field]) : [];
  const filled = form ? REQUIRED_FOR_UAT.length - missing.length : 0;
  const percent = Math.round((filled / REQUIRED_FOR_UAT.length) * 100);
  const complete = form !== null && missing.length === 0;
  const environments = environmentRows(profile);

  function set<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  return (
    <div className="space-y-6">
      <PageBanner
        inset
        homeHref="/participant/dashboard"
        crumb="My Profile"
        title={profile?.company_name || session?.display_name || "My Profile"}
        description="Your organisation details, environment access and account security."
        image="/assets/home/farmers-tomatoes.webp"
      >
        {profile ? (
          <>
            <BannerChip icon={Mail}>{profile.email_id ?? "—"}</BannerChip>
            <BannerChip icon={CalendarDays}>Member since {formatDate(profile.register_date)}</BannerChip>
            <BannerChip icon={ShieldCheck}>Profile {percent}% complete</BannerChip>
          </>
        ) : null}
      </PageBanner>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* ------------------------------------------------------------ main */}
        <div className="min-w-0 space-y-6">
          <Panel
            icon={Building2}
            title="Organisation details"
            description="What the network operator reviews when you request UAT access. Sandbox access does not depend on these."
          >
            {form ? (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  save.mutate(form);
                }}
              >
                <FormSection icon={Building2} title="Organisation">
                  <Field id="profile_type" label="Registering as" required>
                    <Select
                      id="profile_type"
                      value={form.profile_type}
                      onChange={(event) => set("profile_type", event.target.value)}
                    >
                      <option value="">Select</option>
                      <option value="ORGANIZATION">An organisation</option>
                      <option value="INDIVIDUAL">An individual developer</option>
                    </Select>
                  </Field>
                  <Field id="company_name" label="Company name" required>
                    <Input
                      id="company_name"
                      value={form.company_name}
                      onChange={(event) => set("company_name", event.target.value)}
                    />
                  </Field>
                  <Field id="organization_registration_number" label="Trade licence / registration number" required>
                    <Input
                      id="organization_registration_number"
                      value={form.organization_registration_number}
                      onChange={(event) => set("organization_registration_number", event.target.value.toUpperCase())}
                    />
                  </Field>
                  <Field id="website" label="Website">
                    <Input
                      id="website"
                      type="url"
                      placeholder="https://"
                      value={form.website}
                      onChange={(event) => set("website", event.target.value)}
                    />
                  </Field>
                </FormSection>

                <FormSection icon={MapPin} title="Location & role">
                  <Field id="admin_area_code_l1" label="Region" required>
                    <Select
                      id="admin_area_code_l1"
                      value={form.admin_area_code_l1}
                      onChange={(event) => {
                        set("admin_area_code_l1", event.target.value);
                        set("admin_area_code_l2", "");
                      }}
                    >
                      <option value="">Select a region</option>
                      {regions.data?.map((region) => (
                        <option key={region.value} value={region.value}>
                          {region.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field id="participant_type_id" label="Network role" required>
                    <Select
                      id="participant_type_id"
                      value={form.participant_type_id}
                      onChange={(event) => set("participant_type_id", event.target.value)}
                    >
                      <option value="">Select a role</option>
                      {networkRoles.data?.map((role) => (
                        <option key={role.value} value={role.value}>
                          {role.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field id="service_domain" label="Service domain" required>
                    <Select
                      id="service_domain"
                      value={form.service_domain}
                      onChange={(event) => set("service_domain", event.target.value)}
                    >
                      <option value="">Select a domain</option>
                      {serviceDomains.data?.map((domain) => (
                        <option key={domain.value} value={domain.label}>
                          {domain.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field id="operating_area" label="Operating area">
                    <Input
                      id="operating_area"
                      value={form.operating_area}
                      onChange={(event) => set("operating_area", event.target.value)}
                    />
                  </Field>
                </FormSection>

                <FormSection icon={UserRound} title="Authorised contact">
                  <Field id="authorized_person_name" label="Full name" required>
                    <Input
                      id="authorized_person_name"
                      value={form.authorized_person_name}
                      onChange={(event) => set("authorized_person_name", event.target.value)}
                    />
                  </Field>
                  <Field id="authorized_person_designation" label="Designation" required>
                    <Input
                      id="authorized_person_designation"
                      value={form.authorized_person_designation}
                      onChange={(event) => set("authorized_person_designation", event.target.value)}
                    />
                  </Field>
                  <Field id="authorized_person_address" label="Address" wide>
                    <Input
                      id="authorized_person_address"
                      value={form.authorized_person_address}
                      onChange={(event) => set("authorized_person_address", event.target.value)}
                    />
                  </Field>
                </FormSection>

                <FormSection icon={FileText} title="About your service">
                  <Field id="description" label="Service description" required wide>
                    <Textarea
                      id="description"
                      rows={4}
                      value={form.description}
                      onChange={(event) => set("description", event.target.value)}
                      placeholder="Describe the service you intend to offer using OAN data."
                    />
                  </Field>
                </FormSection>

                <div className="-mx-5 -mb-5 mt-6 flex flex-col gap-3 rounded-b-2xl border-t border-hairline bg-surface-soft px-5 py-4 sm:-mx-6 sm:-mb-6 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                  <p className="text-sm text-subtle">
                    <span className="font-semibold text-ink">{filled}</span> of {REQUIRED_FOR_UAT.length} required
                    fields complete
                  </p>
                  <Button type="submit" loading={save.isPending}>
                    Save changes
                  </Button>
                </div>
              </form>
            ) : (
              <p className="py-8 text-sm text-subtle">Loading profile…</p>
            )}
          </Panel>

          <Panel
            id="change-password"
            icon={KeyRound}
            title="Change password"
            description="Use at least 8 characters."
          >
            <form
              onSubmit={(event) => {
                event.preventDefault();
                changePassword.mutate();
              }}
            >
              <div className="grid gap-5 sm:grid-cols-2">
                <Field id="old_password" label="Current password" required>
                  <Input
                    id="old_password"
                    type={showPasswords ? "text" : "password"}
                    autoComplete="current-password"
                    value={passwords.old_password}
                    onChange={(event) => setPasswords({ ...passwords, old_password: event.target.value })}
                    required
                  />
                </Field>
                <Field id="new_password" label="New password" required>
                  <Input
                    id="new_password"
                    type={showPasswords ? "text" : "password"}
                    autoComplete="new-password"
                    value={passwords.new_password}
                    onChange={(event) => setPasswords({ ...passwords, new_password: event.target.value })}
                    required
                    minLength={8}
                  />
                </Field>
              </div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setShowPasswords((value) => !value)}
                  className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-ink"
                >
                  {showPasswords ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                  {showPasswords ? "Hide passwords" : "Show passwords"}
                </button>
                <Button type="submit" variant="outline" loading={changePassword.isPending}>
                  <Lock className="h-4 w-4" aria-hidden />
                  Update password
                </Button>
              </div>
            </form>
          </Panel>
        </div>

        {/* --------------------------------------------------------- sidebar */}
        <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <Panel icon={ShieldCheck} title="Profile completeness">
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-bold text-ink tabular-nums">{percent}%</span>
              <span className="text-sm text-subtle">
                {filled}/{REQUIRED_FOR_UAT.length} fields
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-soft">
              <div
                className={cn("h-full rounded-full transition-all", complete ? "bg-nav-active" : "bg-brand-gold")}
                style={{ width: `${percent}%` }}
              />
            </div>
            <ul className="mt-4 space-y-1.5">
              {REQUIRED_FOR_UAT.map((field) => {
                const done = Boolean(form?.[field]);
                return (
                  <li key={field}>
                    <a
                      href={`#${field}`}
                      className={cn(
                        "flex items-center gap-2 rounded-lg px-2 py-1 text-sm transition-colors hover:bg-surface-soft",
                        done ? "text-subtle" : "font-medium text-ink",
                      )}
                    >
                      {done ? (
                        <Check className="h-4 w-4 shrink-0 text-nav-active" aria-hidden />
                      ) : (
                        <Circle className="h-4 w-4 shrink-0 text-slate-300" aria-hidden />
                      )}
                      {REQUIRED_LABELS[field]}
                    </a>
                  </li>
                );
              })}
            </ul>
          </Panel>

          <Panel icon={Globe2} title="Environment access">
            <ul className="space-y-2.5">
              {environments.map((row) => (
                <li
                  key={row.name}
                  className="flex items-center justify-between gap-3 rounded-xl border border-hairline px-3.5 py-2.5"
                >
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                    {row.label === "Locked" ? (
                      <Lock className="h-4 w-4 text-subtle" aria-hidden />
                    ) : (
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full",
                          row.tone === "success" ? "bg-brand-bright" : row.tone === "warning" ? "bg-brand-gold" : "bg-slate-300",
                        )}
                        aria-hidden
                      />
                    )}
                    {row.name}
                  </span>
                  <Badge variant={row.tone}>{row.label}</Badge>
                </li>
              ))}
            </ul>

            <div className="mt-4 space-y-3">
              {profile && !profile.is_uat_approved ? (
                <>
                  {!complete ? (
                    <p className="flex items-start gap-2 text-sm text-subtle">
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
                      Complete {missing.length} more field{missing.length === 1 ? "" : "s"} to request UAT access.
                    </p>
                  ) : null}
                  <Button
                    className="w-full"
                    disabled={!complete || profile.is_uat_requested}
                    loading={requestPromotion.isPending}
                    onClick={requestUat}
                  >
                    {profile.is_uat_requested ? "UAT request under review" : "Request UAT access"}
                  </Button>
                </>
              ) : null}

              {profile?.is_uat_approved && !profile.is_prod_approved ? (
                <Button
                  className="w-full"
                  disabled={profile.is_prod_requested}
                  onClick={() => setProductionFormOpen(true)}
                >
                  {profile.is_prod_requested ? "Production request under review" : "Request production access"}
                </Button>
              ) : null}

              {profile?.is_prod_approved ? (
                <p className="flex items-center gap-2 text-sm text-subtle">
                  <CheckCircle2 className="h-4 w-4 text-nav-active" aria-hidden />
                  You have full production access.
                </p>
              ) : null}

              {profile?.rejection_reason ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {profile.rejection_reason}
                </p>
              ) : null}
            </div>
          </Panel>

          <Panel icon={UserRound} title="Account">
            <dl className="space-y-3 text-sm">
              <DetailRow label="Email">
                <span className="break-all">{profile?.email_id ?? "—"}</span>
              </DetailRow>
              <DetailRow label="Mobile">{profile?.mobile_number ?? "—"}</DetailRow>
              <DetailRow label="Registered">{formatDate(profile?.register_date)}</DetailRow>
              <DetailRow label="Country">{profile?.country_code ?? "—"}</DetailRow>
            </dl>
          </Panel>
        </aside>
      </div>

      <ProductionRequestDialog
        open={productionFormOpen}
        onOpenChange={setProductionFormOpen}
        submitting={requestPromotion.isPending}
        onSubmit={(formData) => requestPromotion.mutate({ environment: "PRODUCTION", formData })}
      />
    </div>
  );
}

function BannerChip({ icon: Icon, children }: { icon: LucideIcon; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm text-white ring-1 ring-white/25 backdrop-blur">
      <Icon className="h-4 w-4 text-brand-gold" aria-hidden />
      {children}
    </span>
  );
}

function Panel({
  id,
  icon: Icon,
  title,
  description,
  children,
}: {
  id?: string;
  icon: LucideIcon;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 rounded-2xl border border-hairline bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-5 flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-soft text-brand-bright">
          <Icon className="h-4.5 w-4.5" aria-hidden />
        </span>
        <div>
          <h2 className="text-base font-semibold text-nav-active">{title}</h2>
          {description ? <p className="mt-0.5 text-sm text-subtle">{description}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function FormSection({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: React.ReactNode }) {
  return (
    <fieldset className="border-t border-hairline pt-5 pb-6 first:border-t-0 first:pt-0">
      <legend className="sr-only">{title}</legend>
      <p aria-hidden className="mb-4 flex items-center gap-2 text-xs font-semibold tracking-wide text-subtle uppercase">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </p>
      <div className="grid gap-5 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function Field({
  id,
  label,
  required,
  wide,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    // The checklist links jump to the control itself, so offset that past the sticky header.
    <div className={cn("space-y-2 [&_input,&_select,&_textarea]:scroll-mt-28", wide && "sm:col-span-2")}>
      <Label htmlFor={id} required={required}>
        {label}
      </Label>
      {children}
    </div>
  );
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-subtle">{label}</dt>
      <dd className="text-right font-medium text-ink">{children}</dd>
    </div>
  );
}

"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Briefcase,
  Building2,
  Check,
  Circle,
  Eye,
  EyeOff,
  FlaskConical,
  Lock,
  Mail,
  MailCheck,
  PartyPopper,
  Phone,
  ShieldCheck,
  User,
  Zap,
} from "lucide-react";

import { PageBanner } from "@/components/layout/page-banner";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { useToast } from "@/components/ui/toast";
import { REFERENCE_STALE_MS } from "@/lib/cache-times";
import { ApiError } from "@/lib/api-client";
import { DIAL_CODES, config } from "@/lib/config";
import { PASSWORD_RULES } from "@/lib/password-rules";
import { publicApi, participantApi } from "@/lib/services/participant";
import { cn } from "@/lib/utils";

type Step = 1 | 2 | 3;

const STEPS: Array<{ id: Step; label: string }> = [
  { id: 1, label: "Your details" },
  { id: 2, label: "Verify email" },
  { id: 3, label: "Start building" },
];

const BENEFITS = [
  { icon: Zap, title: "Instant sandbox access", body: "Active as soon as your email is verified." },
  { icon: FlaskConical, title: "Synthetic test data", body: "Realistic records, never real farmers." },
  { icon: ShieldCheck, title: "Clear path to production", body: "Move to UAT and production when ready." },
];

interface SignupForm {
  first_name: string;
  last_name: string;
  country_code: string;
  mobile_number: string;
  email_id: string;
  category_id: string;
  company_name: string;
  password: string;
  confirm_password: string;
  declaration: boolean;
}

const EMPTY_FORM: SignupForm = {
  first_name: "",
  last_name: "",
  country_code: config.defaultCountry,
  mobile_number: "",
  email_id: "",
  category_id: "",
  company_name: "",
  password: "",
  confirm_password: "",
  declaration: false,
};

const FIELD =
  "h-11 w-full rounded-lg border border-hairline bg-white pl-10 pr-3.5 text-sm text-ink transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none";

function Field({
  id,
  label,
  icon: Icon,
  hint,
  children,
}: {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-slate-700">
        {label} <span className="text-red-500">*</span>
      </label>
      <div className="relative">
        <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        {children}
      </div>
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

function SectionTitle({ number, children }: { number: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-700 ring-1 ring-brand-200">
        {number}
      </span>
      <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">{children}</h2>
      <span className="h-px flex-1 bg-[#ece8dc]" aria-hidden />
    </div>
  );
}

export default function RegisterPage() {
  const router = useRouter();
  const { notify } = useToast();

  const [step, setStep] = React.useState<Step>(1);
  const [form, setForm] = React.useState<SignupForm>({ ...EMPTY_FORM });
  const [uniqueId, setUniqueId] = React.useState("");
  const [maskedEmail, setMaskedEmail] = React.useState("");
  const [fixedOtp, setFixedOtp] = React.useState(false);
  const [otp, setOtp] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const categories = useQuery({
    queryKey: ["public", "masters", "category"],
    queryFn: () => publicApi.masters("category"),
    staleTime: REFERENCE_STALE_MS,
  });

  function set<K extends keyof SignupForm>(key: K, value: SignupForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submitSignup(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (form.password !== form.confirm_password) {
      setError("The two passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await participantApi.signup({
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        country_code: form.country_code,
        mobile_number: form.mobile_number.trim(),
        email_id: form.email_id.trim(),
        category_id: Number(form.category_id),
        company_name: form.company_name.trim(),
        password: form.password,
        declaration: form.declaration,
      });
      setUniqueId(result.unique_id);
      setMaskedEmail(result.masked_email);
      setFixedOtp(Boolean(result.is_fixed_otp));
      setStep(2);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Registration could not be completed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOtp(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await participantApi.verifyEmail(uniqueId, otp.trim());
      setStep(3);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The code could not be verified.");
    } finally {
      setSubmitting(false);
    }
  }

  async function resendOtp() {
    try {
      const result = await participantApi.resendOtp(uniqueId);
      setMaskedEmail(result.masked_email);
      setFixedOtp(Boolean(result.is_fixed_otp));
      notify(
        result.is_fixed_otp ? "Email is off on this server: use the code 000000." : "A new verification code has been sent.",
        result.is_fixed_otp ? "info" : "success",
      );
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "Could not resend the code.", "error");
    }
  }

  const dialCode = DIAL_CODES[form.country_code] ?? "";
  const passwordsMismatch = form.confirm_password.length > 0 && form.password !== form.confirm_password;

  return (
    <div className="flex min-h-screen flex-col bg-[#fbfaf6]">
      <SiteHeader />

      <main className="flex-1">
        {/* ---------- Page banner ---------- */}
        <PageBanner
          crumb="Sign Up"
          title="Create your developer account"
          description={`Join ${config.siteName} and start testing agriculture APIs in the sandbox in minutes.`}
          overlap
        />

        {/* ---------- Form area ---------- */}
        <section className="relative mx-auto -mt-14 max-w-[1320px] px-4 pb-20 sm:px-8">
          <div className="grid overflow-hidden rounded-2xl bg-white shadow-xl ring-1 ring-black/5 lg:grid-cols-[0.8fr_1.6fr]">
            {/* Info panel */}
            <aside className="relative hidden overflow-hidden bg-[#0b2a1a] p-10 text-white lg:block">
              <Image
                src="/assets/home/farmers-tomatoes.webp"
                alt=""
                fill
                sizes="420px"
                className="object-cover opacity-20"
              />
              <div className="relative flex h-full flex-col">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-brand-gold">Why join</p>
                <h2 className="mt-3 text-2xl font-bold leading-snug">
                  Everything you need to build for farmers
                </h2>

                <ul className="mt-8 space-y-6">
                  {BENEFITS.map((benefit) => (
                    <li key={benefit.title} className="flex gap-4">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-gold text-[#0b2a1a]">
                        <benefit.icon className="h-5 w-5" aria-hidden />
                      </span>
                      <div>
                        <p className="font-semibold">{benefit.title}</p>
                        <p className="mt-0.5 text-sm text-white/70">{benefit.body}</p>
                      </div>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto rounded-xl border border-white/15 bg-white/[0.07] p-5 backdrop-blur-sm">
                  <p className="text-sm text-white/80">Already have an account?</p>
                  <Link
                    href="/participant/login"
                    className="mt-2 inline-flex items-center gap-2 font-semibold text-brand-gold hover:underline"
                  >
                    Login to your dashboard
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </Link>
                </div>
              </div>
            </aside>

            {/* Form panel */}
            <div className="p-6 sm:p-10">
              <ol className="flex items-center gap-2" aria-label="Sign-up progress">
                {STEPS.map((item, index) => (
                  <li key={item.id} className="flex flex-1 items-center gap-2 last:flex-none">
                    <span
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-colors",
                        step > item.id
                          ? "bg-brand-600 text-white"
                          : step === item.id
                            ? "bg-brand-gold text-[#0b2a1a] ring-4 ring-brand-gold/25"
                            : "bg-slate-100 text-slate-400",
                      )}
                      aria-current={step === item.id ? "step" : undefined}
                    >
                      {step > item.id ? <Check className="h-4 w-4" aria-hidden /> : item.id}
                    </span>
                    <span
                      className={cn(
                        "hidden whitespace-nowrap text-sm sm:block",
                        step === item.id ? "font-semibold text-slate-900" : "text-slate-500",
                      )}
                    >
                      {item.label}
                    </span>
                    {index < STEPS.length - 1 ? (
                      <span
                        aria-hidden
                        className={cn("mx-1 h-0.5 flex-1 rounded-full", step > item.id ? "bg-brand-600" : "bg-slate-200")}
                      />
                    ) : null}
                  </li>
                ))}
              </ol>

              {error ? (
                <p role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </p>
              ) : null}

              {step === 1 ? (
                <form className="mt-8 space-y-8" onSubmit={submitSignup} noValidate>
                  <div className="space-y-5">
                    <SectionTitle number={1}>Personal details</SectionTitle>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <Field id="first_name" label="First name" icon={User}>
                        <input
                          id="first_name"
                          autoComplete="given-name"
                          placeholder="e.g. Amina"
                          value={form.first_name}
                          onChange={(event) => set("first_name", event.target.value)}
                          required
                          className={FIELD}
                        />
                      </Field>
                      <Field id="last_name" label="Last name" icon={User}>
                        <input
                          id="last_name"
                          autoComplete="family-name"
                          placeholder="e.g. Wanjiru"
                          value={form.last_name}
                          onChange={(event) => set("last_name", event.target.value)}
                          required
                          className={FIELD}
                        />
                      </Field>
                      <Field
                        id="email_id"
                        label="Business email"
                        icon={Mail}
                        hint="You will sign in with this address."
                      >
                        <input
                          id="email_id"
                          type="email"
                          autoComplete="email"
                          placeholder="you@company.com"
                          value={form.email_id}
                          onChange={(event) => set("email_id", event.target.value)}
                          required
                          className={FIELD}
                        />
                      </Field>
                      <div className="flex flex-col gap-1.5">
                        <label htmlFor="mobile_number" className="text-sm font-semibold text-slate-700">
                          Mobile number <span className="text-red-500">*</span>
                        </label>
                        <div className="flex gap-2">
                          <select
                            aria-label="Country dialling code"
                            value={form.country_code}
                            onChange={(event) => set("country_code", event.target.value)}
                            className="h-11 w-28 shrink-0 rounded-lg border border-hairline bg-white px-2.5 text-sm text-ink focus:border-brand-bright focus:outline-none"
                          >
                            {Object.entries(DIAL_CODES).map(([code, dial]) => (
                              <option key={code} value={code}>
                                {code} +{dial}
                              </option>
                            ))}
                          </select>
                          <div className="relative flex-1">
                            <Phone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                            <input
                              id="mobile_number"
                              inputMode="tel"
                              autoComplete="tel-national"
                              placeholder="Without leading zero"
                              value={form.mobile_number}
                              onChange={(event) => set("mobile_number", event.target.value)}
                              required
                              className={FIELD}
                            />
                          </div>
                        </div>
                        <p className="text-xs text-slate-500">Saved as +{dialCode} followed by your number.</p>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-5">
                    <SectionTitle number={2}>Organisation</SectionTitle>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <Field id="company_name" label="Company name" icon={Building2}>
                        <input
                          id="company_name"
                          autoComplete="organization"
                          placeholder="Registered organisation name"
                          value={form.company_name}
                          onChange={(event) => set("company_name", event.target.value)}
                          required
                          className={FIELD}
                        />
                      </Field>
                      <Field id="category_id" label="Business category" icon={Briefcase}>
                        <select
                          id="category_id"
                          value={form.category_id}
                          onChange={(event) => set("category_id", event.target.value)}
                          required
                          className={cn(FIELD, !form.category_id && "text-slate-400")}
                        >
                          <option value="">{categories.isLoading ? "Loading…" : "Select a category"}</option>
                          {categories.data?.map((category) => (
                            <option key={category.value} value={category.value} className="text-ink">
                              {category.label}
                            </option>
                          ))}
                        </select>
                      </Field>
                    </div>
                  </div>

                  <div className="space-y-5">
                    <SectionTitle number={3}>Security</SectionTitle>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <Field id="password" label="Password" icon={Lock}>
                        <input
                          id="password"
                          type={showPassword ? "text" : "password"}
                          autoComplete="new-password"
                          placeholder="Create a password"
                          value={form.password}
                          onChange={(event) => set("password", event.target.value)}
                          required
                          minLength={8}
                          className={cn(FIELD, "pr-10")}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((shown) => !shown)}
                          aria-label={showPassword ? "Hide password" : "Show password"}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                        >
                          {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </Field>
                      <Field
                        id="confirm_password"
                        label="Confirm password"
                        icon={Lock}
                        hint={
                          passwordsMismatch ? (
                            <span className="text-red-600">Passwords do not match.</span>
                          ) : undefined
                        }
                      >
                        <input
                          id="confirm_password"
                          type={showPassword ? "text" : "password"}
                          autoComplete="new-password"
                          placeholder="Repeat the password"
                          value={form.confirm_password}
                          onChange={(event) => set("confirm_password", event.target.value)}
                          required
                          aria-invalid={passwordsMismatch}
                          className={cn(FIELD, passwordsMismatch && "border-red-400")}
                        />
                      </Field>
                    </div>
                    <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Password rules">
                      {PASSWORD_RULES.map((rule) => {
                        const met = rule.test(form.password);
                        return (
                          <li
                            key={rule.label}
                            className={cn(
                              "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors",
                              met ? "bg-brand-50 text-brand-700" : "bg-slate-50 text-slate-500",
                            )}
                          >
                            {met ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Circle className="h-3 w-3" aria-hidden />}
                            {rule.label}
                          </li>
                        );
                      })}
                    </ul>
                  </div>

                  <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-[#ece8dc] bg-[#fbfaf6] p-4 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={form.declaration}
                      onChange={(event) => set("declaration", event.target.checked)}
                      className="mt-0.5 h-4 w-4 accent-brand-600"
                      required
                    />
                    <span>
                      I confirm the details are correct and accept the{" "}
                      <Link href="/terms" className="font-semibold text-brand-700 hover:underline" target="_blank">
                        Terms and Privacy Policy
                      </Link>
                      .
                    </span>
                  </label>

                  <div className="flex flex-col-reverse items-center gap-4 sm:flex-row sm:justify-between">
                    <p className="text-sm text-slate-600">
                      Already registered?{" "}
                      <Link href="/participant/login" className="font-semibold text-brand-700 hover:underline">
                        Login
                      </Link>
                    </p>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-linear-to-b from-brand-bright to-brand-deep px-8 py-3.5 font-semibold text-white shadow-md transition-[filter] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
                    >
                      {submitting ? "Creating account…" : "Create account"}
                      {!submitting ? <ArrowRight className="h-4 w-4" aria-hidden /> : null}
                    </button>
                  </div>
                </form>
              ) : null}

              {step === 2 ? (
                <form className="mx-auto mt-10 max-w-md text-center" onSubmit={submitOtp} noValidate>
                  <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
                    <MailCheck className="h-8 w-8" aria-hidden />
                  </span>
                  <h2 className="mt-5 text-2xl font-bold text-slate-900">Check your inbox</h2>
                  <p className="mt-2 text-slate-600">
                    We sent a verification code to{" "}
                    <span className="font-semibold text-slate-900">{maskedEmail}</span>. Enter it below to
                    activate your account.
                  </p>
                  {fixedOtp ? (
                    <p
                      role="note"
                      className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900"
                    >
                      <strong>Test server:</strong> email is not set up yet, so no code is sent. Enter{" "}
                      <span className="font-mono font-semibold tracking-widest">000000</span> to verify.
                    </p>
                  ) : null}

                  <label htmlFor="otp" className="sr-only">
                    Verification code
                  </label>
                  <input
                    id="otp"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="••••••"
                    value={otp}
                    onChange={(event) => setOtp(event.target.value.replace(/\s/g, ""))}
                    required
                    maxLength={10}
                    className="mt-8 h-14 w-full rounded-xl border border-hairline bg-[#fbfaf6] text-center font-mono text-2xl tracking-[0.5em] text-ink focus:border-brand-bright focus:bg-white focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none"
                  />

                  <button
                    type="submit"
                    disabled={submitting || !otp}
                    className="mt-6 w-full rounded-lg bg-linear-to-b from-brand-bright to-brand-deep py-3.5 font-semibold text-white shadow-md transition-[filter] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {submitting ? "Verifying…" : "Verify email"}
                  </button>
                  <p className="mt-4 text-sm text-slate-600">
                    Didn&apos;t get it?{" "}
                    <button type="button" onClick={resendOtp} className="font-semibold text-brand-700 hover:underline">
                      Resend the code
                    </button>
                  </p>
                </form>
              ) : null}

              {step === 3 ? (
                <div className="mx-auto mt-10 max-w-md py-4 text-center">
                  <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-gold/20 text-[#b7791f]">
                    <PartyPopper className="h-8 w-8" aria-hidden />
                  </span>
                  <h2 className="mt-5 text-2xl font-bold text-slate-900">Your account is ready</h2>
                  <p className="mt-2 text-slate-600">
                    Sandbox access is active. Login to browse the API catalogue and make your first
                    call. When you are ready for UAT, complete your organisation profile from the
                    dashboard.
                  </p>
                  <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => router.push("/participant/login")}
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-linear-to-b from-brand-bright to-brand-deep px-6 py-3 font-semibold text-white shadow-md hover:brightness-110"
                    >
                      Go to login
                      <ArrowRight className="h-4 w-4" aria-hidden />
                    </button>
                    <button
                      type="button"
                      onClick={() => router.push("/")}
                      className="rounded-lg px-6 py-3 font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50"
                    >
                      Back to home
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

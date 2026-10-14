"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, Circle, Eye, EyeOff, KeyRound, Lock, Mail, MailCheck } from "lucide-react";

import { AuthShell, FIELD_BASE, FIELD_ICON, FIELD_LABEL, SUBMIT_BUTTON } from "@/components/auth/auth-shell";
import type { LoginRole } from "@/components/auth/login-screen";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { PASSWORD_RULES, isStrongPassword } from "@/lib/password-rules";
import { adminApi } from "@/lib/services/admin";
import { participantApi } from "@/lib/services/participant";
import { cn } from "@/lib/utils";

const LOGIN_ROUTES: Record<LoginRole, string> = {
  user: "/participant/login",
  admin: "/admin/login",
};

const FORGOT_ROUTES: Record<LoginRole, string> = {
  user: "/participant/forgot-password",
  admin: "/admin/forgot-password",
};

function errorMessage(caught: unknown, fallback: string) {
  return caught instanceof ApiError ? caught.message : fallback;
}

function BackToLogin({ role }: { role: LoginRole }) {
  return (
    <Link
      href={LOGIN_ROUTES[role]}
      className="mt-6 inline-flex w-full items-center justify-center gap-1.5 text-sm font-semibold text-brand-deep hover:underline"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden />
      Back to sign in
    </Link>
  );
}

// ------------------------------------------------------------ password form
interface PasswordFormProps {
  /** Ask for the verification code too (development reset without mail). */
  withCode?: boolean;
  submitLabel: string;
  onSave: (password: string, code: string) => Promise<void>;
}

/** New password + rules + confirmation, optionally preceded by a code field. */
function PasswordForm({ withCode = false, submitLabel, onSave }: PasswordFormProps) {
  const [code, setCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const mismatch = confirm.length > 0 && password !== confirm;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (withCode && !code.trim()) {
      setError("Enter the verification code.");
      return;
    }
    if (!isStrongPassword(password)) {
      setError("The password does not meet all the rules below.");
      return;
    }
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSave(password, code.trim());
    } catch (caught) {
      setError(errorMessage(caught, "Unable to save the password right now."));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
      {withCode ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="reset-code" className={FIELD_LABEL}>
            Verification Code
          </label>
          <div className="relative">
            <KeyRound className={FIELD_ICON} aria-hidden />
            <input
              id="reset-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\s/g, ""))}
              placeholder="6-digit code"
              maxLength={10}
              required
              className={cn(FIELD_BASE, "pl-10 pr-3.5 font-mono tracking-[0.3em]")}
            />
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <label htmlFor="new-password" className={FIELD_LABEL}>
          New Password
        </label>
        <div className="relative">
          <Lock className={FIELD_ICON} aria-hidden />
          <input
            id="new-password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Create a password"
            required
            className={cn(FIELD_BASE, "pl-10 pr-10")}
          />
          <button
            type="button"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-slate-600"
          >
            {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
          </button>
        </div>
      </div>

      <ul className="grid grid-cols-2 gap-2" aria-label="Password rules">
        {PASSWORD_RULES.map((rule) => {
          const met = rule.test(password);
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

      <div className="flex flex-col gap-1.5">
        <label htmlFor="confirm-password" className={FIELD_LABEL}>
          Confirm Password
        </label>
        <div className="relative">
          <Lock className={FIELD_ICON} aria-hidden />
          <input
            id="confirm-password"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            placeholder="Repeat the password"
            required
            aria-invalid={mismatch}
            className={cn(FIELD_BASE, "pl-10 pr-3.5", mismatch && "border-red-400")}
          />
        </div>
        {mismatch ? <span className="text-xs text-red-600">Passwords do not match.</span> : null}
      </div>

      {error ? (
        <p role="alert" className="text-sm font-medium text-red-600">
          {error}
        </p>
      ) : null}

      <button type="submit" disabled={submitting} className={SUBMIT_BUTTON}>
        {submitting ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

// ------------------------------------------------------------ forgot password
/**
 * Step 1: ask for the account email. With mail on, a reset link is emailed.
 * Without mail (development) the same page continues with the fixed code
 * and the new password.
 */
export function ForgotPasswordScreen({ role }: { role: LoginRole }) {
  const router = useRouter();
  const { notify } = useToast();
  const [email, setEmail] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState<{ to: string; fixedCode: boolean } | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const address = email.trim();
    try {
      const result =
        role === "admin" ? await adminApi.forgotPassword(address) : await participantApi.forgotPassword(address);
      setSent({ to: address, fixedCode: Boolean(result?.is_fixed_otp) });
    } catch (caught) {
      setError(errorMessage(caught, "Unable to send the reset link right now."));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveWithCode(password: string, code: string) {
    if (!sent) return;
    if (role === "admin") {
      await adminApi.setPasswordWithCode(sent.to, code, password);
    } else {
      await participantApi.resetPasswordWithCode(sent.to, code, password);
    }
    notify("Password saved. You can now sign in.", "success");
    router.replace(LOGIN_ROUTES[role]);
  }

  if (sent?.fixedCode) {
    return (
      <AuthShell>
        <h2 className="text-[2rem] font-bold tracking-[-0.5px] text-ink">Set a New Password</h2>
        <p className="mt-1 text-[0.95rem] text-muted-foreground">
          For <span className="font-semibold text-ink">{sent.to}</span>
        </p>
        <p
          role="note"
          className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <strong>Test server:</strong> email is not set up yet, so no reset link is sent. Enter the code{" "}
          <span className="font-mono font-semibold tracking-widest">000000</span> with your new password.
        </p>
        <PasswordForm withCode submitLabel="Save Password" onSave={saveWithCode} />
        <button
          type="button"
          onClick={() => setSent(null)}
          className="mt-4 w-full text-center text-sm font-semibold text-brand-deep hover:underline"
        >
          Use a different email
        </button>
        <BackToLogin role={role} />
      </AuthShell>
    );
  }

  if (sent) {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-50 text-brand-deep">
            <MailCheck className="h-7 w-7" aria-hidden />
          </span>
          <h2 className="mt-4 text-2xl font-bold tracking-[-0.5px] text-ink">Check your email</h2>
          <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground">
            If <span className="font-semibold text-ink">{sent.to}</span> belongs to an account, we have
            sent a link to set a new password. The link expires in{" "}
            {role === "admin" ? "24 hours" : "two hours"}.
          </p>
          <button
            type="button"
            onClick={() => setSent(null)}
            className="mt-5 text-sm font-semibold text-brand-deep hover:underline"
          >
            Use a different email
          </button>
        </div>
        <BackToLogin role={role} />
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <h2 className="text-[2rem] font-bold tracking-[-0.5px] text-ink">Forgot Password</h2>
      <p className="mt-1 text-[0.95rem] text-muted-foreground">
        Enter the email address of your {role === "admin" ? "console" : "developer"} account and we
        will send you a link to set a new password.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="forgot-email" className={FIELD_LABEL}>
            {role === "admin" ? "Email" : "Business Email"}
          </label>
          <div className="relative">
            <Mail className={FIELD_ICON} aria-hidden />
            <input
              id="forgot-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="e.g. dev@company.com"
              required
              className={cn(FIELD_BASE, "pl-10 pr-3.5")}
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className="text-sm font-medium text-red-600">
            {error}
          </p>
        ) : null}

        <button type="submit" disabled={submitting} className={SUBMIT_BUTTON}>
          {submitting ? "Sending…" : "Send Reset Link"}
        </button>
      </form>

      <BackToLogin role={role} />
    </AuthShell>
  );
}

// --------------------------------------------------------------- new password
interface NewPasswordScreenProps {
  role: LoginRole;
  /** Token from the emailed link; missing when the link was mangled. */
  token: string | null;
  /** "invite" when an administrator sets their first password. */
  mode?: "reset" | "invite";
}

/** Step 2 with mail on: the emailed link lands here to choose the new password. */
export function NewPasswordScreen({ role, token, mode = "reset" }: NewPasswordScreenProps) {
  const router = useRouter();
  const { notify } = useToast();
  const title = mode === "invite" ? "Set Your Password" : "Set a New Password";

  async function save(password: string) {
    if (!token) return;
    if (role === "admin") {
      await adminApi.setPassword(token, password);
    } else {
      await participantApi.resetPassword(token, password);
    }
    notify("Password saved. You can now sign in.", "success");
    router.replace(LOGIN_ROUTES[role]);
  }

  if (!token) {
    return (
      <AuthShell>
        <h2 className="text-2xl font-bold tracking-[-0.5px] text-ink">Link not valid</h2>
        <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground">
          This password link is incomplete. Open the link from your email again, or request a new one.
        </p>
        <Link href={FORGOT_ROUTES[role]} className={cn(SUBMIT_BUTTON, "mt-6 w-full")}>
          Request a new link
        </Link>
        <BackToLogin role={role} />
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <h2 className="text-[2rem] font-bold tracking-[-0.5px] text-ink">{title}</h2>
      <p className="mt-1 text-[0.95rem] text-muted-foreground">
        Choose a strong password for your {role === "admin" ? "console" : "developer"} account.
      </p>
      <PasswordForm submitLabel="Save Password" onSave={save} />
      <BackToLogin role={role} />
    </AuthShell>
  );
}

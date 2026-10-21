"use client";

import * as React from "react";
import Link from "next/link";
import { Eye, EyeOff, Lock, User } from "lucide-react";

import { AuthShell, FIELD_BASE, FIELD_ICON, FIELD_LABEL, SUBMIT_BUTTON } from "@/components/auth/auth-shell";
import { cn } from "@/lib/utils";

export type LoginRole = "user" | "admin";

const ROLE_ROUTES: Record<LoginRole, string> = {
  user: "/participant/login",
  admin: "/admin/login",
};

const FORGOT_ROUTES: Record<LoginRole, string> = {
  user: "/participant/forgot-password",
  admin: "/admin/forgot-password",
};

interface LoginScreenProps {
  role: LoginRole;
  submitting: boolean;
  error: string | null;
  onSubmit: (username: string, password: string) => void;
}

/**
 * Sign-in screen shared by the participant and admin logins, inside the shared
 * {@link AuthShell} (brand photo panel + card).
 * The User/Admin toggle switches between the two login routes.
 */
export function LoginScreen({ role, submitting, error, onSubmit }: LoginScreenProps) {
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(username.trim(), password);
  }

  return (
    <AuthShell>
      <h2 className="text-[2rem] font-bold tracking-[-0.5px] text-ink">Welcome Back</h2>
      <p className="mt-1 text-[0.95rem] text-muted-foreground">
        {role === "admin" ? "Sign in to the admin console" : "Sign in to your developer account"}
      </p>

      {/* Role toggle */}
      <div
        role="tablist"
        aria-label="Sign in as"
        className="mt-6 grid grid-cols-2 gap-1 rounded-full border border-slate-200 bg-slate-50 p-1"
      >
        {(["user", "admin"] as const).map((option) => {
          const active = role === option;
          return (
            <Link
              key={option}
              role="tab"
              aria-selected={active}
              href={ROLE_ROUTES[option]}
              replace
              className={cn(
                "rounded-full border py-2 text-center text-sm font-semibold transition-colors",
                active
                  ? "border-brand-bright/40 bg-white text-brand-deep shadow-sm"
                  : "border-transparent text-muted-foreground hover:text-slate-700",
              )}
            >
              {option === "user" ? "User" : "Admin"}
            </Link>
          );
        })}
      </div>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-username" className={FIELD_LABEL}>
            {role === "admin" ? "Email or Username" : "Business Email"}
          </label>
          <div className="relative">
            <User className={FIELD_ICON} aria-hidden />
            <input
              id="login-username"
              type={role === "admin" ? "text" : "email"}
              autoComplete={role === "admin" ? "username" : "email"}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={role === "admin" ? "e.g. admin" : "e.g. dev@company.com"}
              required
              className={cn(FIELD_BASE, "pl-10 pr-3.5")}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="login-password" className={FIELD_LABEL}>
              Password
            </label>
            <Link
              href={FORGOT_ROUTES[role]}
              className="text-xs font-semibold text-brand-deep hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <Lock className={FIELD_ICON} aria-hidden />
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
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

        {error ? (
          <p role="alert" className="text-sm font-medium text-red-600">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={submitting}
          className={SUBMIT_BUTTON}
        >
          {submitting ? "Signing in…" : "Sign In"}
        </button>
      </form>

      {role === "user" ? (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Not registered yet?{" "}
          <Link href="/participant/register" className="font-semibold text-brand-deep hover:underline">
            Create an account
          </Link>
        </p>
      ) : null}
    </AuthShell>
  );
}

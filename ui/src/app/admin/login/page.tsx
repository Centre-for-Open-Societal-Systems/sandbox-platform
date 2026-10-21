"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LoginScreen } from "@/components/auth/login-screen";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { adminApi } from "@/lib/services/admin";
import { adminSession } from "@/lib/session";

export default function AdminLoginPage() {
  const router = useRouter();
  const { notify } = useToast();
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // A live session should not sit on the sign-in screen.
  React.useEffect(() => {
    if (adminSession.isSignedIn()) {
      router.replace("/admin/dashboard");
    }
  }, [router]);

  async function handleSubmit(username: string, password: string) {
    setError(null);
    setSubmitting(true);
    try {
      const session = await adminApi.login(username, password);
      adminSession.set(session);
      notify("Signed in successfully.", "success");
      router.replace("/admin/dashboard");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to sign in right now.");
    } finally {
      setSubmitting(false);
    }
  }

  return <LoginScreen role="admin" submitting={submitting} error={error} onSubmit={handleSubmit} />;
}

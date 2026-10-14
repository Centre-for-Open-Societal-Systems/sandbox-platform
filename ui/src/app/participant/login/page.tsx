"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { LoginScreen } from "@/components/auth/login-screen";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { participantApi } from "@/lib/services/participant";
import { participantSession } from "@/lib/session";

export default function ParticipantLoginPage() {
  const router = useRouter();
  const { notify } = useToast();
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (participantSession.isSignedIn()) {
      router.replace("/participant/dashboard");
    }
  }, [router]);

  async function handleSubmit(emailId: string, password: string) {
    setError(null);
    setSubmitting(true);
    try {
      const session = await participantApi.login(emailId, password);
      participantSession.set(session);
      notify(`Welcome back, ${session.display_name}.`, "success");
      router.replace("/participant/dashboard");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to sign in right now.");
    } finally {
      setSubmitting(false);
    }
  }

  return <LoginScreen role="user" submitting={submitting} error={error} onSubmit={handleSubmit} />;
}

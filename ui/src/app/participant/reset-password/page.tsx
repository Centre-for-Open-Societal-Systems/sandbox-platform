"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";

import { NewPasswordScreen } from "@/components/auth/password-screens";

function ResetPassword() {
  const token = useSearchParams().get("token");
  return <NewPasswordScreen role="user" token={token} />;
}

/** Landing page of the emailed reset link (`/participant/reset-password?token=…`). */
export default function ParticipantResetPasswordPage() {
  return (
    <React.Suspense fallback={null}>
      <ResetPassword />
    </React.Suspense>
  );
}

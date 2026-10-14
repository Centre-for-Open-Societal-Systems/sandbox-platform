"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";

import { NewPasswordScreen } from "@/components/auth/password-screens";

function SetPassword() {
  const token = useSearchParams().get("token");
  return <NewPasswordScreen role="admin" token={token} />;
}

/** Landing page of the admin invitation and reset emails (`/admin/set-password?token=…`). */
export default function AdminSetPasswordPage() {
  return (
    <React.Suspense fallback={null}>
      <SetPassword />
    </React.Suspense>
  );
}

"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { ENVIRONMENTS, type Environment } from "@/lib/config";
import { participantApi } from "@/lib/services/participant";
import { participantSession } from "@/lib/session";

/**
 * The environments the signed-in participant may call, as the server says now.
 *
 * The session saved at sign-in goes stale when an administrator approves or
 * rejects an environment later (or when an environment is retired), so the
 * server's list wins and is written back to the session. Until it arrives the
 * session's list is used, limited to the environments that still exist.
 */
export function useEnvironments(): Environment[] {
  const session = participantSession.get();
  const { data } = useQuery({
    // Same query as the dashboard, so the two share one request.
    queryKey: ["participant", "dashboard"],
    queryFn: participantApi.dashboard,
    enabled: Boolean(session),
  });
  const fresh = data?.environments;

  React.useEffect(() => {
    const saved = participantSession.get();
    if (fresh && saved && fresh.join() !== saved.environments.join()) {
      participantSession.set({ ...saved, environments: fresh });
    }
  }, [fresh]);

  const current = fresh ?? session?.environments ?? [];
  return ENVIRONMENTS.filter((item) => current.includes(item));
}

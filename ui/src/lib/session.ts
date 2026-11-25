/**
 * Browser session storage for the two independent audiences.
 *
 * Admin sessions live in `sessionStorage` so closing the tab ends them; portal
 * user sessions live in `localStorage` so developers are not signed out
 * between visits. Neither store holds anything the API would not re-issue on a
 * fresh login.
 */

import { STORAGE_KEYS, config } from "@/lib/config";
import type { AdminSession, ParticipantSession } from "@/types/api";

type Audience = "admin" | "participant";

function storeFor(audience: Audience): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  return audience === "admin" ? window.sessionStorage : window.localStorage;
}

function read<T>(audience: Audience): T | null {
  const store = storeFor(audience);
  if (!store) {
    return null;
  }
  const raw = store.getItem(STORAGE_KEYS[audience]);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    // A corrupt entry is worse than none - clear it so the user can sign in.
    store.removeItem(STORAGE_KEYS[audience]);
    return null;
  }
}

function write(audience: Audience, session: unknown): void {
  storeFor(audience)?.setItem(STORAGE_KEYS[audience], JSON.stringify(session));
}

function clear(audience: Audience): void {
  storeFor(audience)?.removeItem(STORAGE_KEYS[audience]);
}

export const adminSession = {
  get: () => read<AdminSession>("admin"),
  set: (session: AdminSession) => write("admin", session),
  clear: () => clear("admin"),
  isSignedIn: () => Boolean(read<AdminSession>("admin")?.access_token),
};

export const participantSession = {
  get: () => read<ParticipantSession>("participant"),
  set: (session: ParticipantSession) => write("participant", session),
  clear: () => clear("participant"),
  isSignedIn: () => Boolean(read<ParticipantSession>("participant")?.access_token),
};

/** Auth headers for a request made on behalf of the given audience. */
export function authHeaders(audience: Audience): Record<string, string> {
  const session = audience === "admin" ? adminSession.get() : participantSession.get();
  if (!session) {
    return {};
  }
  return {
    "x-access-token": session.access_token,
    "x-auth-key": session.auth_key,
  };
}

/** The member country in scope, from the user's choice or the deployment default. */
export function activeCountry(): string {
  if (typeof window === "undefined") {
    return config.defaultCountry;
  }
  return window.localStorage.getItem(STORAGE_KEYS.country) ?? config.defaultCountry;
}

export function setActiveCountry(countryCode: string): void {
  window.localStorage.setItem(STORAGE_KEYS.country, countryCode);
}

/** True when the signed-in admin may open the screen behind `permissionId`. */
export function adminCan(permissionId: number): boolean {
  const session = adminSession.get();
  if (!session) {
    return false;
  }
  if (session.is_master) {
    return true;
  }
  return session.permissions.some((flag) => flag.id === permissionId && flag.status);
}

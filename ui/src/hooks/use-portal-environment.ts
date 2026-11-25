"use client";

import * as React from "react";

import { useEnvironments } from "@/hooks/use-environments";
import { ENVIRONMENTS, type Environment } from "@/lib/config";

const STORAGE_KEY = "oan.portal.environment";
const CHANGE_EVENT = "oan:portal-environment";

function read(): Environment | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return (ENVIRONMENTS as readonly string[]).includes(value ?? "") ? (value as Environment) : null;
  } catch {
    return null; // storage blocked (private window, policy)
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange); // other tabs
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** Remember ``environment`` for the portal (this browser) and tell every page using it. */
export function setPortalEnvironment(environment: Environment): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, environment);
  } catch {
    // Not remembered; the pages still follow it for this visit through the event.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Pick ``preferred`` when the account may use it, else the first environment it may use. */
export function effectiveEnvironment(preferred: Environment | null, available: Environment[]): Environment {
  if (preferred && available.includes(preferred)) return preferred;
  return available[0] ?? "UAT";
}

/**
 * The environment the participant works in (UAT / Production), shared by My Apps and
 * the try-it page and remembered in this browser: choosing it on one page sets it on
 * the others. It never names an environment the account is not approved for.
 */
export function usePortalEnvironment(): [Environment, (environment: Environment) => void, Environment[]] {
  const available = useEnvironments();
  const stored = React.useSyncExternalStore(subscribe, read, () => null);
  return [effectiveEnvironment(stored, available), setPortalEnvironment, available];
}

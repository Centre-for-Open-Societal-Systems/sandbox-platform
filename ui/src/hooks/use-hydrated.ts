import * as React from "react";

const noopSubscribe = () => () => {};

/**
 * False during the server render and hydration, true afterwards.
 *
 * Lets a client component read browser-only state (session storage, local
 * storage) without an effect that sets state, and without a hydration
 * mismatch: server and first client render agree on `false`.
 */
export function useHydrated(): boolean {
  return React.useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

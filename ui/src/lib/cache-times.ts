/**
 * How long React Query treats data as fresh before refetching.
 *
 * The default (30 s, set in providers.tsx) suits live data such as API history.
 * Catalogue and reference data change only when an administrator edits them,
 * so pages reuse them across navigation instead of refetching on every visit.
 */

/** Published catalogue: products, end-points, the API menu, code samples. */
export const CATALOG_STALE_MS = 5 * 60_000;

/** Reference data: masters, administrative areas, dropdown lists. */
export const REFERENCE_STALE_MS = 30 * 60_000;

import { connection } from "next/server";

import { config } from "@/lib/config";

/**
 * API base URL for calls made by the Next.js server (public pages).
 *
 * `NEXT_PUBLIC_API_BASE_URL` is the address the browser uses. Inside Docker
 * that is `localhost:8010`, which from the web container is the container
 * itself, so the server reads `API_INTERNAL_URL` (e.g. `http://api:8000/oan`)
 * at run time instead. Outside Docker the two are the same.
 */
function serverApiBaseUrl(): string {
  return (process.env.API_INTERNAL_URL ?? config.apiBaseUrl).replace(/\/$/, "");
}

/**
 * GET a public API path from a server component. The page renders per request
 * (not at build time, when the API is unreachable) and the response is cached
 * for `revalidate` seconds.
 */
export async function serverFetch(path: string, revalidate: number): Promise<Response> {
  await connection();
  return fetch(`${serverApiBaseUrl()}${path}`, {
    next: { revalidate },
    headers: { "x-country-code": config.defaultCountry },
  });
}

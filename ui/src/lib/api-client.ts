/**
 * HTTP client for the OAN sandbox API.
 *
 * The API always answers with the same envelope, so this unwraps `data` and
 * turns a non-success envelope into a typed `ApiError` the callers can catch.
 */

import { config } from "@/lib/config";
import { activeCountry, adminSession, authHeaders, participantSession } from "@/lib/session";
import type { Envelope } from "@/types/api";

export type Audience = "public" | "admin" | "participant";

export class ApiError extends Error {
  readonly status: number;
  readonly code: number;
  readonly details: unknown;

  constructor(message: string, status: number, code: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

interface RequestOptions {
  audience?: Audience;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Send as multipart instead of JSON. */
  formData?: FormData;
  /**
   * Browser cache mode. Default "no-store". Use "no-cache" for responses that
   * carry an ETag: the browser revalidates and reuses its copy on 304.
   */
  cache?: RequestCache;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${config.apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function buildHeaders(options: RequestOptions, hasJsonBody: boolean): Headers {
  const headers = new Headers();
  if (hasJsonBody) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("x-country-code", activeCountry());

  const audience = options.audience ?? "public";
  if (audience !== "public") {
    for (const [key, value] of Object.entries(authHeaders(audience))) {
      headers.set(key, value);
    }
  }
  return headers;
}

/** Set before the redirect; the home page reads it to say why the user landed there. */
export const SESSION_EXPIRED_FLAG = "oan.session-expired";

let redirecting = false;

/**
 * Drop the local session when the server says it is no longer valid, and send
 * the user to the home page. Returns true when a redirect is under way.
 *
 * Only a request that carried a session counts: a public call (such as a
 * login with a wrong password) also gets 401 and must stay on its page.
 */
function handleUnauthorized(audience: Audience): boolean {
  const store = audience === "admin" ? adminSession : audience === "participant" ? participantSession : null;
  if (!store || !store.isSignedIn()) {
    return redirecting;
  }
  store.clear();
  if (!redirecting && typeof window !== "undefined") {
    redirecting = true;
    window.sessionStorage.setItem(SESSION_EXPIRED_FLAG, audience);
    window.location.replace("/");
  }
  return redirecting;
}

/** Keeps the caller waiting while the page navigates away, so no error flashes on screen. */
function untilNavigation<T>(): Promise<T> {
  return new Promise<T>(() => {});
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const audience = options.audience ?? "public";
  const isMultipart = Boolean(options.formData);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers: buildHeaders(options, body !== undefined && !isMultipart),
      body: isMultipart ? options.formData : body === undefined ? undefined : JSON.stringify(body),
      signal: options.signal,
      cache: options.cache ?? "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError("Unable to reach the server. Check your connection.", 0, 0);
  }

  if (response.status === 401 && handleUnauthorized(audience)) {
    return untilNavigation<T>();
  }

  const payload = (await response.json().catch(() => null)) as Envelope<T> | null;
  if (!payload) {
    throw new ApiError("The server returned an unreadable response.", response.status, response.status);
  }

  if (!response.ok || payload.status === false) {
    throw new ApiError(
      payload.message || "Request failed.",
      response.status,
      payload.code ?? response.status,
      (payload as unknown as { error?: unknown }).error,
    );
  }

  return payload.data;
}

/** Download an export; returns the raw blob rather than an envelope. */
async function download(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<Blob> {
  const response = await fetch(buildUrl(path, options.query), {
    method: "POST",
    headers: buildHeaders(options, true),
    body: JSON.stringify(body),
  });

  if (response.status === 401 && handleUnauthorized(options.audience ?? "public")) {
    return untilNavigation<Blob>();
  }
  if (!response.ok) {
    throw new ApiError("The export could not be generated.", response.status, response.status);
  }
  return response.blob();
}

/** Fetch an uploaded file (`/files/...`) with the caller's session headers. */
async function file(path: string, options: RequestOptions = {}): Promise<Blob> {
  const response = await fetch(buildUrl(path, options.query), {
    method: "GET",
    headers: buildHeaders(options, false),
    cache: "no-store",
  });
  if (response.status === 401 && handleUnauthorized(options.audience ?? "public")) {
    return untilNavigation<Blob>();
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as Envelope<unknown> | null;
    throw new ApiError(payload?.message || "The file could not be opened.", response.status, response.status);
  }
  return response.blob();
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
  /** Multipart request; POST unless the route expects another method (e.g. PUT). */
  upload: <T>(
    path: string,
    formData: FormData,
    options?: RequestOptions,
    method: "POST" | "PUT" = "POST",
  ) => request<T>(method, path, undefined, { ...options, formData }),
  download,
  file,
};

/**
 * Open a blob in a new tab. Call `window.open()` before awaiting the download
 * and pass the tab here, so pop-up blockers treat it as a user action.
 */
export function showBlobInTab(blob: Blob, tab: Window | null): void {
  const url = URL.createObjectURL(blob);
  if (tab) {
    tab.location.href = url;
  } else {
    window.open(url, "_blank", "noopener");
  }
  // Long enough for the tab to load the document.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Trigger a browser save for a blob the API returned. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

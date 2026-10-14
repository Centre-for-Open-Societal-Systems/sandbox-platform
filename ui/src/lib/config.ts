/**
 * Runtime configuration, read once from the public environment variables.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/oan";

export const config = {
  apiBaseUrl: API_BASE_URL.replace(/\/$/, ""),
  defaultCountry: process.env.NEXT_PUBLIC_DEFAULT_COUNTRY ?? "ET",
  siteName: process.env.NEXT_PUBLIC_SITE_NAME ?? "Open Agri Net",
} as const;

/** Storage keys for the two independent sessions the app can hold. */
export const STORAGE_KEYS = {
  admin: "oan.admin.session",
  participant: "oan.participant.session",
  country: "oan.country",
} as const;

/**
 * Dialling codes for the member countries, mirroring `COUNTRY_RULES` in
 * `app/utils/validators.py`. The signup form uses the selected country both to
 * prefix the number and to pick the length rule the API validates against.
 */
export const DIAL_CODES: Record<string, string> = {
  ET: "251",
  KE: "254",
  RW: "250",
  GH: "233",
  NG: "234",
};

export const ENVIRONMENTS = ["SANDBOX", "UAT", "PRODUCTION"] as const;
export type Environment = (typeof ENVIRONMENTS)[number];

export const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;
export type HttpMethod = (typeof HTTP_METHODS)[number];

export const DEFAULT_PAGE_SIZE = 10;
export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;

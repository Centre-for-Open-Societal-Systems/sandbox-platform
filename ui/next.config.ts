import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

/** Origin of the OAN API the browser calls (NEXT_PUBLIC_API_BASE_URL, inlined at build time). */
function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/oan").origin;
  } catch {
    return "";
  }
}

/**
 * Content-Security-Policy. Scripts allow 'unsafe-inline' because the App Router
 * streams inline bootstrap scripts and the pages are statically rendered, so
 * per-request nonces are not available. 'unsafe-eval' and ws: (HMR) are dev-only.
 * Try-it calls go through the API, so the gateway origin is not needed here.
 */
function contentSecurityPolicy(): string {
  const api = apiOrigin();
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", ...(isDev ? ["'unsafe-eval'"] : [])],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", api],
    "font-src": ["'self'", "data:"],
    "connect-src": ["'self'", api, ...(isDev ? ["ws:", "wss:"] : [])],
    "frame-src": ["'self'"],
    "frame-ancestors": ["'none'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
  };
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.filter(Boolean).join(" ")}`)
    .join("; ");
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The Docker image sets NEXT_STANDALONE=true to ship a self-contained server
  // (.next/standalone) instead of all of node_modules. Local builds are unchanged.
  output: process.env.NEXT_STANDALONE === "true" ? "standalone" : undefined,
  async redirects() {
    return [
      // Reset emails sent from databases seeded before 13 Oct 2026 link here.
      { source: "/reset-password", destination: "/participant/reset-password", permanent: false },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Content-Security-Policy", value: contentSecurityPolicy() },
          ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
        ],
      },
    ];
  },
};

export default nextConfig;

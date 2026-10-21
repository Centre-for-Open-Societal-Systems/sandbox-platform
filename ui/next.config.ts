import type { NextConfig } from "next";

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
        ],
      },
    ];
  },
};

export default nextConfig;

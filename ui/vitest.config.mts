import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Unit tests for components and helpers (`src/**/*.test.ts(x)`). Next.js route
// files (`src/app/**`) are screens, checked end to end, so they are left out of
// the coverage figures; `npm run test:coverage` writes coverage/lcov.info for Sonar.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text-summary", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/app/**", "src/**/*.test.{ts,tsx}", "src/types/**"],
    },
  },
});

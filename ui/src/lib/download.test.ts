import { describe, expect, it } from "vitest";

import { fileSlug } from "@/lib/download";

describe("fileSlug", () => {
  it("makes a file-safe name", () => {
    expect(fileSlug("Farmer Registry (v2)")).toBe("farmer-registry-v2");
  });

  it("falls back when nothing usable is left", () => {
    expect(fileSlug("???")).toBe("api");
  });
});

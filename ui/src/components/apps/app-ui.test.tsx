import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EnvironmentBadge } from "@/components/apps/app-ui";

afterEach(cleanup);

describe("EnvironmentBadge", () => {
  it("names a production app", () => {
    render(<EnvironmentBadge environment="PRODUCTION" />);
    expect(screen.getByText("Production").className).toContain("FFF1CC");
  });

  it("names a UAT app", () => {
    render(<EnvironmentBadge environment="UAT" />);
    expect(screen.getByText("UAT").className).toContain("DCEBFF");
  });
});

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

afterEach(cleanup);

describe("Card", () => {
  it("renders the title text inside the heading", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle className="extra">Usage</CardTitle>
          <CardDescription>Calls this month</CardDescription>
        </CardHeader>
        <CardContent>42</CardContent>
      </Card>,
    );

    const heading = screen.getByRole("heading", { level: 3, name: "Usage" });
    expect(heading.className).toContain("extra");
    expect(screen.getByText("Calls this month")).toBeDefined();
    expect(screen.getByText("42")).toBeDefined();
  });

  it("passes other heading attributes through", () => {
    render(<CardTitle id="t1">Apps</CardTitle>);

    expect(screen.getByRole("heading", { name: "Apps" }).id).toBe("t1");
  });
});

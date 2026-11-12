import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EnvironmentToggle } from "@/components/portal/environment-toggle";
import { effectiveEnvironment, setPortalEnvironment, usePortalEnvironment } from "@/hooks/use-portal-environment";
import type { Environment } from "@/lib/config";

let approved: Environment[] = ["UAT", "PRODUCTION"];
vi.mock("@/hooks/use-environments", () => ({ useEnvironments: () => approved }));

beforeEach(() => {
  window.localStorage.clear();
  approved = ["UAT", "PRODUCTION"];
});
afterEach(cleanup);

describe("EnvironmentToggle", () => {
  it("marks the chosen environment, counts apps and reports a change", () => {
    const onChange = vi.fn();
    render(<EnvironmentToggle value="UAT" onChange={onChange} available={["UAT", "PRODUCTION"]} counts={{ UAT: 3, PRODUCTION: 1 }} />);

    const uat = screen.getByRole("radio", { name: /UAT/ });
    const production = screen.getByRole("radio", { name: /Production/ });
    expect(uat.getAttribute("aria-checked")).toBe("true");
    expect(production.getAttribute("aria-checked")).toBe("false");
    expect(uat.textContent).toBe("UAT3");
    fireEvent.click(production);
    expect(onChange).toHaveBeenCalledWith("PRODUCTION");
  });

  it("shows an environment the account may not use, disabled", () => {
    const onChange = vi.fn();
    render(<EnvironmentToggle value="UAT" onChange={onChange} available={["UAT"]} />);
    const production = screen.getByRole("radio", { name: "Production" }) as HTMLButtonElement;
    expect(production.disabled).toBe(true);
    expect(production.title).toContain("not approved");
  });
});

function Probe({ id }: { id: string }) {
  const [environment, setEnvironment] = usePortalEnvironment();
  return (
    <button type="button" data-testid={id} onClick={() => setEnvironment(environment === "UAT" ? "PRODUCTION" : "UAT")}>
      {environment}
    </button>
  );
}

describe("usePortalEnvironment", () => {
  it("is shared by every page using it and remembered", () => {
    render(
      <>
        <Probe id="apps" />
        <Probe id="try-it" />
      </>,
    );
    expect(screen.getByTestId("apps").textContent).toBe("UAT");

    fireEvent.click(screen.getByTestId("apps"));
    expect(screen.getByTestId("try-it").textContent).toBe("PRODUCTION");
    expect(window.localStorage.getItem("oan.portal.environment")).toBe("PRODUCTION");
  });

  it("never names an environment the account is not approved for", () => {
    approved = ["UAT"];
    act(() => setPortalEnvironment("PRODUCTION"));
    render(<Probe id="only" />);
    expect(screen.getByTestId("only").textContent).toBe("UAT");
  });

  it("picks the stored choice when allowed, else the first allowed one", () => {
    expect(effectiveEnvironment("PRODUCTION", ["UAT", "PRODUCTION"])).toBe("PRODUCTION");
    expect(effectiveEnvironment("PRODUCTION", ["UAT"])).toBe("UAT");
    expect(effectiveEnvironment(null, [])).toBe("UAT");
  });
});

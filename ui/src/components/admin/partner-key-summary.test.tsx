import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PartnerKeySummary } from "@/components/admin/partner-key-summary";
import type { PartnerKeyInfo } from "@/types/api";

afterEach(cleanup);

const FINGERPRINT = Array.from({ length: 32 }, () => "AB").join(":");

const FROM_CERTIFICATE: PartnerKeyInfo = {
  algorithm: "RSA 2048",
  fingerprint_sha256: FINGERPRINT,
  source: "certificate",
  certificate: {
    subject: "O=Partner Ltd,CN=partner.example.org",
    common_name: "partner.example.org",
    issuer: "O=Partner Ltd,CN=partner.example.org",
    serial_number: "1A2B3C",
    not_before: "2026-11-01T00:00:00+00:00",
    not_after: "2027-11-01T00:00:00+00:00",
    self_signed: true,
  },
};

describe("PartnerKeySummary", () => {
  it("shows the certificate's owner, validity and fingerprint", () => {
    render(<PartnerKeySummary info={FROM_CERTIFICATE} now={new Date("2026-11-11")} />);
    expect(screen.getByText("RSA 2048")).toBeDefined();
    expect(screen.getByText("From certificate")).toBeDefined();
    expect(screen.getByText("Self-signed")).toBeDefined();
    expect(screen.queryByText("Expired")).toBeNull();
    expect(screen.getByText("partner.example.org")).toBeDefined();
    expect(screen.getByText("Itself (self-signed)")).toBeDefined();
    expect(screen.getByText("2026-11-01 to 2027-11-01")).toBeDefined();
    expect(screen.getByText(FINGERPRINT)).toBeDefined();
  });

  it("marks an expired certificate and names a CA issuer", () => {
    const signed = {
      ...FROM_CERTIFICATE,
      certificate: { ...FROM_CERTIFICATE.certificate!, self_signed: false, issuer: "CN=Test CA" },
    };
    render(<PartnerKeySummary info={signed} now={new Date("2028-01-01")} />);
    expect(screen.getByText("Expired")).toBeDefined();
    expect(screen.getByText("CN=Test CA")).toBeDefined();
    expect(screen.queryByText("Self-signed")).toBeNull();
  });

  it("shows a pasted public key without certificate details", () => {
    render(
      <PartnerKeySummary info={{ algorithm: "Ed25519", fingerprint_sha256: FINGERPRINT, source: "public_key", certificate: null }} />,
    );
    expect(screen.getByText("Public key only")).toBeDefined();
    expect(screen.queryByText("Issued to")).toBeNull();
  });
});

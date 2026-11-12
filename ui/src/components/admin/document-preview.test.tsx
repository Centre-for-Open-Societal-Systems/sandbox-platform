import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { DocumentPreview, previewKind } from "@/components/admin/document-preview";

const saveBlob = vi.fn();
vi.mock("@/lib/api-client", () => ({ saveBlob: (...args: unknown[]) => saveBlob(...args) }));

const revoked: string[] = [];
beforeAll(() => {
  // jsdom has no object URLs.
  URL.createObjectURL = () => "blob:preview-1";
  URL.revokeObjectURL = (url: string) => void revoked.push(url);
});
afterEach(() => {
  cleanup();
  saveBlob.mockClear();
  revoked.length = 0;
});

function show(fileName: string, load: () => Promise<Blob>, onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DocumentPreview open onOpenChange={onOpenChange} title="Data retention policy" fileName={fileName} load={load} />
    </QueryClientProvider>,
  );
  return onOpenChange;
}

describe("previewKind", () => {
  it("picks the viewer and blob type from the extension", () => {
    expect(previewKind("policy.PDF")).toEqual({ kind: "pdf", type: "application/pdf" });
    expect(previewKind("scan.jpg")).toEqual({ kind: "image", type: "image/jpeg" });
    expect(previewKind("client.crt")).toEqual({ kind: "text", type: "text/plain" });
    expect(previewKind("client.der").kind).toBe("other");
    expect(previewKind("noextension").kind).toBe("other");
  });
});

describe("DocumentPreview", () => {
  it("shows a PDF inside the dialog, and frees it on close", async () => {
    const onOpenChange = show("policy.pdf", async () => new Blob(["%PDF-1.4"]));
    const frame = await screen.findByTitle("Data retention policy");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame.getAttribute("src")).toBe("blob:preview-1");
    expect(screen.getByText("policy.pdf")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Download" }));
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), "policy.pdf");
    expect((saveBlob.mock.calls[0]![0] as Blob).type).toBe("application/pdf");

    fireEvent.click(screen.getAllByRole("button", { name: "Close" }).at(-1)!);
    expect(revoked).toEqual(["blob:preview-1"]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("shows an image", async () => {
    show("scan.png", async () => new Blob(["png"]));
    expect((await screen.findByAltText("Data retention policy")).getAttribute("src")).toBe("blob:preview-1");
  });

  it("shows a certificate as text", async () => {
    show("client.pem", async () => new Blob(["-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----"]));
    expect(await screen.findByText(/BEGIN CERTIFICATE/)).toBeDefined();
    expect(screen.queryByRole("button", { name: "Open in new tab" })).toBeNull();
  });

  it("offers a download for a file without a preview", async () => {
    show("client.der", async () => new Blob([new Uint8Array([0x30, 0x82])]));
    expect(await screen.findByText(/no preview/)).toBeDefined();
  });

  it("says when the file cannot be loaded", async () => {
    show("policy.pdf", async () => {
      throw new Error("File not found.");
    });
    expect(await screen.findByText("File not found.")).toBeDefined();
    expect((screen.getByRole("button", { name: "Download" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

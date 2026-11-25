import * as React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FileDropzone, fileProblem, formatBytes } from "@/components/ui/file-dropzone";

afterEach(cleanup);

const ACCEPT = [".pdf", ".png"];

function Harness({ onChange, maxMb }: { onChange?: (file: File | null) => void; maxMb?: number }) {
  const [file, setFile] = React.useState<File | null>(null);
  return (
    <>
      <label htmlFor="doc">Data retention policy</label>
      <FileDropzone
        id="doc"
        accept={ACCEPT}
        value={file}
        maxMb={maxMb}
        hint="PDF or PNG"
        onChange={(next) => {
          setFile(next);
          onChange?.(next);
        }}
      />
    </>
  );
}

function pdf(name = "policy.pdf", bytes = 2048): File {
  return new File([new Uint8Array(bytes)], name, { type: "application/pdf" });
}

describe("FileDropzone", () => {
  it("invites a click or a drop and states what it takes", () => {
    render(<Harness />);
    expect(screen.getByText("Click to upload")).toBeDefined();
    expect(screen.getByText("PDF or PNG · up to 25 MB")).toBeDefined();
    expect(screen.getByLabelText("Data retention policy").getAttribute("accept")).toBe(".pdf,.png");
  });

  it("shows the chosen file with its size, and removes it", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const file = pdf();
    fireEvent.change(screen.getByLabelText("Data retention policy"), { target: { files: [file] } });

    expect(onChange).toHaveBeenLastCalledWith(file);
    expect(screen.getByText("policy.pdf")).toBeDefined();
    expect(screen.getByText("2.0 KB")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Remove policy.pdf" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByText("Click to upload")).toBeDefined();
  });

  it("takes a dropped file", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const file = pdf("dropped.pdf");
    fireEvent.drop(screen.getByText("Click to upload").closest("label")!, { dataTransfer: { files: [file] } });
    expect(onChange).toHaveBeenLastCalledWith(file);
  });

  it("refuses a wrong type or a file over the limit, with a message", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} maxMb={1} />);
    const input = screen.getByLabelText("Data retention policy");

    fireEvent.change(input, { target: { files: [new File(["x"], "key.pem")] } });
    expect(screen.getByRole("alert").textContent).toBe('"key.pem" is not accepted. Choose a .pdf, .png file.');
    expect(input.getAttribute("aria-invalid")).toBe("true");

    fireEvent.change(input, { target: { files: [pdf("big.pdf", 2 * 1024 * 1024)] } });
    expect(screen.getByRole("alert").textContent).toBe('"big.pdf" is 2.0 MB; files up to 1 MB are accepted.');
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("helpers", () => {
  it("formats sizes and checks files", () => {
    expect([formatBytes(512), formatBytes(1536), formatBytes(3 * 1024 * 1024)]).toEqual(["512 B", "1.5 KB", "3.0 MB"]);
    expect(fileProblem(pdf("A.PDF"), ACCEPT, 25)).toBeNull();
    expect(fileProblem(new File(["x"], "noextension"), ACCEPT, 25)).toContain("is not accepted");
  });
});

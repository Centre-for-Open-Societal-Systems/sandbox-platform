"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, FileWarning, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { saveBlob } from "@/lib/api-client";

type Kind = "pdf" | "image" | "text" | "other";

const IMAGE_TYPES: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
const TEXT_EXTENSIONS = new Set(["pem", "crt", "cer", "txt"]);

/** How a stored upload is shown, and the type its blob is given, from its extension. */
export function previewKind(fileName: string): { kind: Kind; type: string } {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return { kind: "pdf", type: "application/pdf" };
  if (IMAGE_TYPES[ext]) return { kind: "image", type: IMAGE_TYPES[ext] };
  if (TEXT_EXTENSIONS.has(ext)) return { kind: "text", type: "text/plain" };
  return { kind: "other", type: "application/octet-stream" };
}

interface DocumentPreviewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Dialog title, e.g. "Data retention policy". */
  title: string;
  fileName: string;
  /** Loads the file with the admin session (private uploads are not public URLs). */
  load: () => Promise<Blob>;
}

/**
 * A private upload shown in the console itself: a PDF in the browser's viewer, an
 * image, or a certificate as text. Download and "Open in new tab" stay available.
 * The blob is typed from the file's extension (the API checks PDF / image content
 * on upload), so nothing is rendered as a web page.
 */
export function DocumentPreview({ open, onOpenChange, title, fileName, load }: DocumentPreviewProps) {
  const { kind, type } = previewKind(fileName);
  const fileQuery = useQuery({
    queryKey: ["admin", "document-preview", fileName],
    queryFn: async () => {
      const loaded = await load();
      const blob = new Blob([loaded], { type });
      return {
        blob,
        text: kind === "text" ? await loaded.text() : null,
        // Made here, freed when the dialog closes (handleOpenChange).
        url: kind === "text" ? null : URL.createObjectURL(blob),
      };
    },
    enabled: open,
    // Each opening loads the file again, so a freed URL is never reused.
    gcTime: 0,
    retry: false,
  });

  const blob = fileQuery.data?.blob;
  const url = fileQuery.data?.url ?? null;

  function handleOpenChange(next: boolean) {
    if (!next && url) URL.revokeObjectURL(url);
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="flex max-h-[92vh] w-[min(96vw,64rem)] max-w-none flex-col">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="truncate" title={fileName}>
            {fileName}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-[50vh] flex-1 overflow-auto rounded-lg border border-hairline bg-surface-soft">
          {fileQuery.isLoading ? (
            <p className="flex h-full min-h-[50vh] items-center justify-center gap-2 text-sm text-subtle">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading the document…
            </p>
          ) : fileQuery.isError ? (
            <p className="flex h-full min-h-[50vh] items-center justify-center gap-2 p-6 text-center text-sm text-destructive">
              <FileWarning className="h-4 w-4 shrink-0" aria-hidden />
              {fileQuery.error instanceof Error ? fileQuery.error.message : "The document could not be loaded."}
            </p>
          ) : kind === "pdf" && url ? (
            <iframe src={url} title={title} className="h-[70vh] w-full rounded-lg bg-white" />
          ) : kind === "image" && url ? (
            // A blob URL: next/image cannot optimise it.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={title} className="mx-auto max-h-[70vh] max-w-full object-contain p-2" />
          ) : kind === "text" && fileQuery.data?.text != null ? (
            <pre className="h-full max-h-[70vh] overflow-auto p-4 font-mono text-xs break-all whitespace-pre-wrap text-ink">
              {fileQuery.data.text}
            </pre>
          ) : kind === "other" && blob ? (
            <p className="flex h-full min-h-[50vh] items-center justify-center p-6 text-center text-sm text-subtle">
              This file type has no preview. Download it to open it.
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={!blob} onClick={() => blob && saveBlob(blob, fileName)}>
            <Download className="h-4 w-4" aria-hidden />
            Download
          </Button>
          {url ? (
            <Button variant="outline" onClick={() => window.open(url, "_blank", "noopener")}>
              <ExternalLink className="h-4 w-4" aria-hidden />
              Open in new tab
            </Button>
          ) : null}
          <Button onClick={() => handleOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

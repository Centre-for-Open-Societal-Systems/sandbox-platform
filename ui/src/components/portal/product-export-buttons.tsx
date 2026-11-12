"use client";

import * as React from "react";
import { FileJson, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { downloadJson, fileSlug } from "@/lib/download";
import { catalogApi } from "@/lib/services/catalog";

/** "Download OpenAPI" for one product. The file holds the contract, never a key. */
export function ProductExportButtons({
  productId,
  productName,
  audience,
  environment,
  variant = "outline",
}: {
  productId: number;
  productName: string;
  audience: "public" | "participant";
  /** Participant only: the gateway of this environment is written into the file. */
  environment?: string;
  variant?: "outline" | "secondary";
}) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const document = await catalogApi.exportProduct(productId, audience, environment);
      downloadJson(`${fileSlug(productName)}.openapi.json`, document);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The download failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant={variant} size="sm" disabled={busy} onClick={download}>
          {busy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <FileJson className="h-3.5 w-3.5" aria-hidden />
          )}
          Download OpenAPI
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}

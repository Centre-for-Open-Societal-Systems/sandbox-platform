"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { catalogApi } from "@/lib/services/catalog";

/**
 * Old console address (still linked from API History): forward to the sandbox
 * test page, which needs the end-point's product in its URL.
 */
export default function LegacyConsoleRedirect() {
  const params = useParams<{ endpointId: string }>();
  const router = useRouter();
  const endpointId = Number(params.endpointId);

  const endpointQuery = useQuery({
    queryKey: ["participant", "endpoint", endpointId],
    queryFn: () => catalogApi.portalEndpoint(endpointId),
    enabled: Number.isFinite(endpointId),
  });
  const productId = endpointQuery.data?.product_id;

  React.useEffect(() => {
    if (productId) {
      router.replace(`/participant/product/${productId}/${endpointId}`);
    } else if (endpointQuery.isError) {
      router.replace("/participant/catalog");
    }
  }, [productId, endpointId, endpointQuery.isError, router]);

  return (
    <p className="flex items-center gap-2 py-16 text-sm text-subtle">
      <Loader2 className="h-4 w-4 animate-spin text-brand-bright" aria-hidden />
      Opening the sandbox…
    </p>
  );
}

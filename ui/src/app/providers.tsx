"use client";

import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ToastProvider, useToast } from "@/components/ui/toast";
import { ApiError, SESSION_EXPIRED_FLAG } from "@/lib/api-client";

/** After an expired session sends the user home, say why once. */
function SessionExpiredNotice() {
  const { notify } = useToast();
  React.useEffect(() => {
    if (window.sessionStorage.getItem(SESSION_EXPIRED_FLAG)) {
      window.sessionStorage.removeItem(SESSION_EXPIRED_FLAG);
      notify("Your session has expired. Please sign in again.", "warning");
    }
  }, [notify]);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error) => {
              // An expired session or a missing permission will not fix itself.
              if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
                return false;
              }
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <SessionExpiredNotice />
        {children}
      </ToastProvider>
    </QueryClientProvider>
  );
}

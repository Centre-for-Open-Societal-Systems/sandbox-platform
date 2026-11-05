"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { adminAppsApi } from "@/lib/services/apps";
import { formatDateTime } from "@/lib/utils";
import type { IamAccount, PartnerPortalAccount } from "@/types/api";

const STATUS: Record<IamAccount["status"], { label: string; variant: "success" | "neutral" | "danger" }> = {
  ACTIVE: { label: "Active", variant: "success" },
  DISABLED: { label: "No access yet", variant: "neutral" },
  FAILED: { label: "Not ready", variant: "danger" },
};

function RoleBadges({ roles }: { roles: string[] }) {
  if (roles.length === 0) {
    return <span className="text-xs text-subtle">no environment role</span>;
  }
  return (
    <>
      {roles.map((role) => (
        <Badge key={role} variant="info">
          {role.toUpperCase()}
        </Badge>
      ))}
    </>
  );
}

/** Console view of a participant's Keycloak user: status, roles, errors and retry. */
export function AdminIamAccount({ participantId }: { participantId: number }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const key = ["admin", "participants", participantId, "iam-account"];
  const accountQuery = useQuery({ queryKey: key, queryFn: () => adminAppsApi.iamAccount(participantId) });
  const retry = useMutation({
    mutationFn: () => adminAppsApi.retryIamAccount(participantId),
    onSuccess: (data) => {
      queryClient.setQueryData(key, data);
      notify("Keycloak sync re-run.", "success");
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const data = accountQuery.data;
  if (!data?.enabled) {
    return null;
  }
  const account = data.account;
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">Keycloak user (API login)</h3>
      {!account ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-subtle">
          No user yet: it is created when UAT access is approved.
          <Button size="sm" variant="outline" loading={retry.isPending} onClick={() => retry.mutate()}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Create now
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border border-hairline px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={(STATUS[account.status] ?? STATUS.FAILED).variant}>
              {(STATUS[account.status] ?? STATUS.FAILED).label}
            </Badge>
            <RoleBadges roles={account.roles} />
            <code className="min-w-0 truncate font-mono text-xs">{account.username}</code>
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              loading={retry.isPending}
              onClick={() => retry.mutate()}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              {account.status === "FAILED" ? "Retry" : "Sync"}
            </Button>
          </div>
          <p className="mt-1 text-xs text-subtle">
            Password {account.password_synced ? "in sync" : "not set yet (set at the next portal sign-in)"}
            {account.synced_at ? ` · last sync ${formatDateTime(account.synced_at)}` : ""}
          </p>
          {account.console_url ? (
            <a
              href={account.console_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs text-brand-bright hover:underline"
            >
              Open in Keycloak <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          ) : null}
          {account.error ? <p className="mt-1 text-xs break-words text-red-700">{account.error}</p> : null}
          {account.partner_portal ? <PartnerPortal portal={account.partner_portal} /> : null}
        </div>
      )}
    </div>
  );
}

const PM_STATUS: Record<string, { label: string; variant: "success" | "neutral" | "danger" }> = {
  ACTIVE: { label: "Active", variant: "success" },
  DISABLED: { label: "Disabled", variant: "neutral" },
  FAILED: { label: "Not ready", variant: "danger" },
};

/** Consent Manager partner portal: partner ID, portal role and the Partner Management partner. */
function PartnerPortal({ portal }: { portal: PartnerPortalAccount }) {
  const pm = portal.pm_status ? (PM_STATUS[portal.pm_status] ?? PM_STATUS.FAILED) : null;
  return (
    <div className="mt-2 border-t border-hairline pt-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold">Consent partner portal</span>
        <code className="font-mono">{portal.partner_id ?? "-"}</code>
        <Badge variant={portal.portal_access ? "success" : "neutral"}>
          {portal.portal_access ? portal.role : "no portal access"}
        </Badge>
      </div>
      {portal.pm_enabled ? (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-subtle">Partner Management</span>
          {portal.pm_partner_id ? <code className="font-mono">{portal.pm_partner_id}</code> : null}
          {pm ? <Badge variant={pm.variant}>{pm.label}</Badge> : <span className="text-subtle">not onboarded</span>}
          {portal.pm_synced_at ? <span className="text-subtle">· {formatDateTime(portal.pm_synced_at)}</span> : null}
        </div>
      ) : null}
      {portal.pm_error ? <p className="mt-1 text-xs break-words text-red-700">{portal.pm_error}</p> : null}
    </div>
  );
}

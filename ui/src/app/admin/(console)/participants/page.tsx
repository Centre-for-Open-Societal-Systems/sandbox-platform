"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleX, Download } from "lucide-react";

import { ParticipantReview } from "@/components/admin/participant-review";
import { Button } from "@/components/ui/button";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { EnabledBadge, EnvironmentBadge, VerifiedBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { saveBlob } from "@/lib/api-client";
import { Permission } from "@/lib/permissions";
import { adminApi } from "@/lib/services/admin";
import { formatDate } from "@/lib/utils";
import type { Participant } from "@/types/api";

type Tab =
  | "all"
  | "uat-pending"
  | "uat"
  | "uat-rejected"
  | "prod-pending"
  | "prod"
  | "prod-rejected";

interface TabSpec {
  id: Tab;
  label: string;
  permission: number;
  /** Which environment a decision on this tab applies to. */
  environment?: "UAT" | "PRODUCTION";
  /** Show the approve/reject buttons - only the two pending queues do. */
  decidable?: boolean;
}

const TABS: TabSpec[] = [
  { id: "all", label: "All Participants", permission: Permission.ALL_PARTICIPANTS },
  {
    id: "uat-pending",
    label: "UAT Approval Pending",
    permission: Permission.UAT_APPROVAL_PENDING,
    environment: "UAT",
    decidable: true,
  },
  { id: "uat", label: "UAT Participants", permission: Permission.UAT_PARTICIPANTS, environment: "UAT" },
  {
    id: "uat-rejected",
    label: "UAT Rejected Participants",
    permission: Permission.UAT_REJECTED_PARTICIPANTS,
    environment: "UAT",
  },
  {
    id: "prod-pending",
    label: "Prod Approval Pending",
    permission: Permission.PROD_APPROVAL_PENDING,
    environment: "PRODUCTION",
    decidable: true,
  },
  {
    id: "prod",
    label: "Prod Participants",
    permission: Permission.PROD_PARTICIPANTS,
    environment: "PRODUCTION",
  },
  {
    id: "prod-rejected",
    label: "Prod Rejected Participants",
    permission: Permission.PROD_REJECTED_PARTICIPANTS,
    environment: "PRODUCTION",
  },
];

interface DecisionState {
  participant: Participant;
  action: "approve" | "reject";
  environment: string;
}

function fetchTab(tab: Tab, query: ReturnType<typeof useListQuery>["query"]) {
  switch (tab) {
    case "uat-pending":
      return adminApi.listPending(query, "UAT");
    case "uat":
      return adminApi.listParticipants(query, "UAT");
    case "uat-rejected":
      return adminApi.listRejected(query, "UAT");
    case "prod-pending":
      return adminApi.listPending(query, "PRODUCTION");
    case "prod":
      return adminApi.listParticipants(query, "PRODUCTION");
    case "prod-rejected":
      return adminApi.listRejected(query, "PRODUCTION");
    default:
      return adminApi.listParticipants(query);
  }
}

function isTab(value: string | null): value is Tab {
  return TABS.some((item) => item.id === value);
}

export default function ParticipantsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const searchParams = useSearchParams();
  // The sidebar deep-links each list as ?tab=..., so the URL is the only
  // source of truth for which list is shown.
  const requested = searchParams.get("tab");
  const tab: Tab = isTab(requested) ? requested : "all";
  const [decision, setDecision] = React.useState<DecisionState | null>(null);
  const [reason, setReason] = React.useState("");
  const [viewing, setViewing] = React.useState<Participant | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const list = useListQuery({ sortBy: "register_date" });
  const active = TABS.find((item) => item.id === tab) ?? TABS[0]!;

  // Switching list starts again at page 1 (state adjusted during render,
  // which React prefers over an effect for derived resets).
  const [shownTab, setShownTab] = React.useState(tab);
  if (shownTab !== tab) {
    setShownTab(tab);
    list.setPage(1);
  }

  const participantsQuery = useQuery({
    queryKey: ["admin", "participants", tab, list.query],
    queryFn: () => fetchTab(tab, list.query),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "participants"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "dashboard"] });
  }

  const decide = useMutation({
    mutationFn: ({ participant, action, environment }: DecisionState) =>
      action === "approve"
        ? adminApi.approveEnvironment(participant.participant_id, environment)
        : adminApi.rejectParticipant(participant.participant_id, environment, reason),
    onSuccess: (_result, variables) => {
      notify(
        variables.action === "approve"
          ? `${variables.environment} access approved.`
          : `${variables.environment} access rejected.`,
        "success",
      );
      setDecision(null);
      setReason("");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggle = useMutation({
    mutationFn: (participant: Participant) =>
      adminApi.toggleParticipant(participant.participant_id),
    onSuccess: () => {
      notify("Participant status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  async function handleExport() {
    try {
      const blob = await adminApi.exportParticipants(list.query);
      saveBlob(blob, `participants-${new Date().toISOString().slice(0, 10)}.xlsx`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Export failed.", "error");
    }
  }

  const columns: Column<Participant>[] = [
    {
      key: "display_name",
      header: "Name",
      sortable: true,
      render: (row) => (
        <div>
          <p className="font-medium">{row.display_name || "—"}</p>
          <p className="text-xs text-subtle">{row.email_id}</p>
        </div>
      ),
    },
    { key: "company_name", header: "Company", render: (row) => row.company_name ?? "—" },
    { key: "profile_type", header: "Profile Type", render: (row) => row.profile_type ?? "—" },
    { key: "environment", header: "Environment", render: (row) => <EnvironmentBadge participant={row} /> },
    { key: "is_email_verified", header: "Email", render: (row) => <VerifiedBadge verified={row.is_email_verified} /> },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "register_date",
      header: "Added Date",
      sortable: true,
      render: (row) => formatDate(row.register_date),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => {
        const name = row.display_name || row.email_id || "participant";
        const decisions =
          active.decidable && active.environment
            ? [
                {
                  icon: CircleCheck,
                  label: `Approve ${active.environment} access for ${name}`,
                  onClick: () => setDecision({ participant: row, action: "approve", environment: active.environment! }),
                },
                {
                  icon: CircleX,
                  label: `Reject ${active.environment} request of ${name}`,
                  tone: "danger" as const,
                  onClick: () => setDecision({ participant: row, action: "reject", environment: active.environment! }),
                },
              ]
            : [];
        return (
          <RowActions
            recordLabel={name}
            onView={() => setViewing(row)}
            extra={decisions}
            status={{
              checked: row.is_enabled,
              onChange: async (next) => {
                if (!next) {
                  const ok = await confirm({
                    title: "Deactivate Participant?",
                    consequence: `${name} will be signed out and cannot use the portal until reactivated.`,
                    confirmLabel: "Deactivate",
                  });
                  if (!ok) {
                    return;
                  }
                }
                toggle.mutate(row);
              },
            }}
          />
        );
      },
    },
  ];

  return (
    <>
      <PageHeader
        title={active.label}
        description="Sandbox access is automatic once an email is verified; UAT and production are approved here."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Manage Participant" }, { label: active.label }]}
        search={{
          value: list.searchInput,
          onChange: list.setSearchInput,
          placeholder: "Search name, company or email",
        }}
        actions={
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4" aria-hidden />
            Export
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="Profile Type" htmlFor="profile-type">
          <Select
            id="profile-type"
            value={(list.filters.profile_type as string) ?? ""}
            onChange={(event) => list.setFilter("profile_type", event.target.value)}
          >
            <option value="">All</option>
            <option value="ORGANIZATION">Organisation</option>
            <option value="INDIVIDUAL">Individual</option>
          </Select>
        </FilterField>
        <Button variant="ghost" onClick={list.resetFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={participantsQuery.data?.participants ?? []}
        rowKey={(row) => row.participant_id}
        pagination={participantsQuery.data?.pagination}
        loading={participantsQuery.isLoading}
        noun="participants"
        emptyMessage="No participants match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {confirmDialog}

      <Dialog open={viewing !== null} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Participant Details</DialogTitle>
            <DialogDescription>{viewing?.display_name}</DialogDescription>
          </DialogHeader>
          {viewing ? (
            <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {[
                ["Name", viewing.display_name],
                ["Email", viewing.email_id],
                ["Mobile", viewing.mobile_number],
                ["Company", viewing.company_name],
                ["Profile type", viewing.profile_type],
                ["Registration no.", viewing.organization_registration_number],
                ["Website", viewing.website],
                ["Country", viewing.country_code],
                ["Region", viewing.admin_area_code_l1],
                ["Service domain", viewing.service_domain],
                ["Registered", formatDate(viewing.register_date)],
                ["UAT approved", formatDate(viewing.uat_approved_date)],
                ["Production approved", formatDate(viewing.prod_approved_date)],
                ["Rejection reason", viewing.rejection_reason],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-medium text-subtle">{label}</dt>
                  <dd className="mt-0.5 text-sm break-words text-ink">{value || "—"}</dd>
                </div>
              ))}
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <EnvironmentBadge participant={viewing} />
                <VerifiedBadge verified={viewing.is_email_verified} />
                <EnabledBadge enabled={viewing.is_enabled} />
              </div>
              <div className="border-t border-hairline pt-4 sm:col-span-2">
                <ParticipantReview participantId={viewing.participant_id} />
              </div>
            </dl>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={decision !== null} onOpenChange={(open) => !open && setDecision(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {decision?.action === "approve" ? "Approve access" : "Reject request"}
            </DialogTitle>
            <DialogDescription>
              {decision?.participant.display_name} · {decision?.environment}
            </DialogDescription>
          </DialogHeader>

          {decision?.action === "reject" ? (
            <div className="space-y-2">
              <Label htmlFor="reason" required>
                Reason
              </Label>
              <Textarea
                id="reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Explain what the participant needs to correct."
              />
              <p className="text-xs text-muted-foreground">
                This is sent to the participant, so write it for their eyes.
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              The participant will be notified and gains access immediately.
            </p>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDecision(null)}>
              Cancel
            </Button>
            <Button
              variant={decision?.action === "reject" ? "destructive" : "primary"}
              loading={decide.isPending}
              disabled={decision?.action === "reject" && reason.trim().length < 3}
              onClick={() => decision && decide.mutate(decision)}
            >
              {decision?.action === "approve" ? "Approve" : "Reject"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailPlus, Plus } from "lucide-react";

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
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { FilterBar, FilterField, PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { EnabledBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { CATALOG_STALE_MS } from "@/lib/cache-times";
import { adminApi } from "@/lib/services/admin";
import { formatDate } from "@/lib/utils";
import type { AdminUser } from "@/types/api";

interface FormState {
  admin_id?: number;
  first_name: string;
  last_name: string;
  email_id: string;
  mobile_no: string;
  login_name: string;
  role_id: string;
  description: string;
}

const EMPTY_FORM: FormState = {
  first_name: "",
  last_name: "",
  email_id: "",
  mobile_no: "",
  login_name: "",
  role_id: "",
  description: "",
};

export default function AdministratorsPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "added_date" });
  const [form, setForm] = React.useState<FormState | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const usersQuery = useQuery({
    queryKey: ["admin", "users", list.query],
    queryFn: () => adminApi.listUsers(list.query),
  });

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles", "dropdown"],
    queryFn: adminApi.roleDropdown,
    staleTime: CATALOG_STALE_MS,
  });

  function closeForm() {
    setForm(null);
  }

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  }

  const save = useMutation({
    mutationFn: (values: FormState) => {
      const payload = {
        ...values,
        role_id: Number(values.role_id),
        last_name: values.last_name || null,
        mobile_no: values.mobile_no || null,
        description: values.description || null,
      };
      return values.admin_id ? adminApi.updateUser(payload) : adminApi.createUser(payload);
    },
    onSuccess: (_data, values) => {
      notify(
        values.admin_id
          ? "User updated successfully."
          : "User created. An invitation has been emailed to them.",
        "success",
      );
      closeForm();
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggle = useMutation({
    mutationFn: (user: AdminUser) => adminApi.toggleUser(user.admin_id),
    onSuccess: () => {
      notify("User status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (user: AdminUser) => adminApi.deleteUser(user.admin_id),
    onSuccess: () => {
      notify("User deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const resendInvite = useMutation({
    mutationFn: (user: AdminUser) => adminApi.resendInvite(user.admin_id),
    onSuccess: () => notify("Invitation sent.", "success"),
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<AdminUser>[] = [
    {
      key: "first_name",
      header: "Name",
      sortable: true,
      render: (row) => (
        <div>
          <p className="font-medium">{[row.first_name, row.last_name].filter(Boolean).join(" ")}</p>
          <p className="text-xs text-subtle">{row.email_id}</p>
        </div>
      ),
    },
    { key: "login_name", header: "Username", render: (row) => row.login_name },
    { key: "role_name", header: "Role", render: (row) => row.role_name ?? "—" },
    { key: "country_code", header: "Scope", render: (row) => row.country_code ?? "Network-wide" },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "added_date",
      header: "Added Date",
      sortable: true,
      render: (row) => formatDate(row.added_date),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => {
        const name = [row.first_name, row.last_name].filter(Boolean).join(" ") || row.login_name;
        return (
          <RowActions
            recordLabel={`user ${name}`}
            onEdit={() =>
              setForm({
                admin_id: row.admin_id,
                first_name: row.first_name ?? "",
                last_name: row.last_name ?? "",
                email_id: row.email_id ?? "",
                mobile_no: row.mobile_no ?? "",
                login_name: row.login_name,
                role_id: String(row.role_id ?? ""),
                description: row.description ?? "",
              })
            }
            extra={
              !row.is_activated
                ? [{ icon: MailPlus, label: `Resend invite to ${name}`, onClick: () => resendInvite.mutate(row) }]
                : []
            }
            onDelete={async () => {
              const ok = await confirm({
                title: "Delete User?",
                consequence: `${name} will lose access to the console. This cannot be undone.`,
                confirmLabel: "Delete",
              });
              if (ok) {
                remove.mutate(row);
              }
            }}
            canDelete={!row.is_master}
            deleteBlockedReason="The master administrator cannot be deleted"
            status={{
              checked: row.is_enabled,
              disabled: row.is_master,
              onChange: async (next) => {
                if (!next) {
                  const ok = await confirm({
                    title: "Deactivate User?",
                    consequence: `${name} will be signed out and cannot sign in until reactivated.`,
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
        title="Admin Users"
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "User Management" }, { label: "Admin Users" }]}
        search={{
          value: list.searchInput,
          onChange: list.setSearchInput,
          placeholder: "Search name, email or username",
        }}
        actions={
          <Button onClick={() => setForm({ ...EMPTY_FORM })}>
            <Plus className="h-4 w-4" aria-hidden />
            Add User
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="Role" htmlFor="role-filter">
          <Select
            id="role-filter"
            value={(list.filters.role_id as string) ?? ""}
            onChange={(event) =>
              list.setFilter("role_id", event.target.value ? Number(event.target.value) : "")
            }
          >
            <option value="">All roles</option>
            {rolesQuery.data?.map((role) => (
              <option key={role.value} value={role.value}>
                {role.label}
              </option>
            ))}
          </Select>
        </FilterField>
        <Button variant="ghost" onClick={list.resetFilters}>
          Clear
        </Button>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={usersQuery.data?.users ?? []}
        rowKey={(row) => row.admin_id}
        pagination={usersQuery.data?.pagination}
        loading={usersQuery.isLoading}
        noun="users"
        emptyMessage="No admin users match these filters."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {confirmDialog}
      <Dialog open={form !== null} onOpenChange={(open) => !open && closeForm()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{form?.admin_id ? "Edit user" : "Add user"}</DialogTitle>
            <DialogDescription>
              {form?.admin_id
                ? "Update this account's details and role."
                : "The user receives an email invitation to set their own password."}
            </DialogDescription>
          </DialogHeader>

          {form ? (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                save.mutate(form);
              }}
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="first_name" required>
                    First name
                  </Label>
                  <Input
                    id="first_name"
                    value={form.first_name}
                    onChange={(event) => setForm({ ...form, first_name: event.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="last_name">Last name</Label>
                  <Input
                    id="last_name"
                    value={form.last_name}
                    onChange={(event) => setForm({ ...form, last_name: event.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="email_id" required>
                  Email
                </Label>
                <Input
                  id="email_id"
                  type="email"
                  value={form.email_id}
                  onChange={(event) => setForm({ ...form, email_id: event.target.value })}
                  required
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="login_name" required>
                    Username
                  </Label>
                  <Input
                    id="login_name"
                    value={form.login_name}
                    onChange={(event) => setForm({ ...form, login_name: event.target.value })}
                    required
                    minLength={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mobile_no">Mobile</Label>
                  <Input
                    id="mobile_no"
                    value={form.mobile_no}
                    onChange={(event) => setForm({ ...form, mobile_no: event.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="role_id" required>
                  Role
                </Label>
                <Select
                  id="role_id"
                  value={form.role_id}
                  onChange={(event) => setForm({ ...form, role_id: event.target.value })}
                  required
                >
                  <option value="">Select a role</option>
                  {rolesQuery.data?.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </Select>
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeForm}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  {form.admin_id ? "Save changes" : "Create user"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

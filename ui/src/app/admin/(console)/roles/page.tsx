"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, type Column } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfirm } from "@/components/ui/confirm-dialog";
import { PageHeader } from "@/components/ui/page-header";
import { RowActions } from "@/components/ui/row-actions";
import { EnabledBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { useListQuery } from "@/hooks/use-list-query";
import { adminApi } from "@/lib/services/admin";
import type { PermissionNode, Role } from "@/types/api";

export default function RolesPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const list = useListQuery({ sortBy: "role_name", sortDir: "asc" });

  const [selectedRole, setSelectedRole] = React.useState<Role | null>(null);
  const [granted, setGranted] = React.useState<Set<number>>(new Set());
  const [creating, setCreating] = React.useState(false);
  const [newRoleName, setNewRoleName] = React.useState("");
  const { confirm, dialog: confirmDialog } = useConfirm();

  const rolesQuery = useQuery({
    queryKey: ["admin", "roles", list.query],
    queryFn: () => adminApi.listRoles(list.query),
  });

  const permissionsQuery = useQuery({
    queryKey: ["admin", "permissions", selectedRole?.role_id],
    queryFn: () => adminApi.permissions(selectedRole?.role_id),
    enabled: selectedRole !== null,
  });

  // Opening a role seeds the checkboxes from its stored grants.
  function openRole(role: Role) {
    setGranted(new Set(role.permission_ids));
    setSelectedRole(role);
  }

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
  }

  const createRole = useMutation({
    mutationFn: (roleName: string) =>
      adminApi.createRole({ role_name: roleName, permission_ids: [] }),
    onSuccess: () => {
      notify("Role created. Assign its permissions next.", "success");
      setCreating(false);
      setNewRoleName("");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const savePermissions = useMutation({
    mutationFn: (role: Role) =>
      adminApi.updatePermissions(
        role.role_id,
        [...collectIds(permissionsQuery.data ?? [])].map((id) => ({
          id,
          status: granted.has(id),
        })),
      ),
    onSuccess: () => {
      notify("Permissions updated.", "success");
      setSelectedRole(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggleRole = useMutation({
    mutationFn: (role: Role) => adminApi.toggleRole(role.role_id),
    onSuccess: () => {
      notify("Role status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const deleteRole = useMutation({
    mutationFn: (role: Role) => adminApi.deleteRole(role.role_id),
    onSuccess: () => {
      notify("Role deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function togglePermission(node: PermissionNode) {
    setGranted((current) => {
      const next = new Set(current);
      const enabling = !next.has(node.permission_id);

      if (enabling) {
        next.add(node.permission_id);
      } else {
        next.delete(node.permission_id);
        // Removing a parent removes the screens nested under it.
        for (const child of node.children) {
          next.delete(child.permission_id);
        }
      }
      return next;
    });
  }

  const columns: Column<Role>[] = [
    { key: "role_name", header: "Role Name", sortable: true, render: (row) => <span className="font-medium">{row.role_name}</span> },
    { key: "permissions", header: "Permissions", render: (row) => row.permission_ids.length },
    { key: "users", header: "Users", render: (row) => row.user_count },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={`role ${row.role_name}`}
          extra={[{ icon: ShieldCheck, label: `Manage permissions of ${row.role_name}`, onClick: () => openRole(row) }]}
          onDelete={async () => {
            const ok = await confirm({
              title: "Delete Role?",
              consequence: `The role ${row.role_name} will be removed.`,
              confirmLabel: "Delete",
            });
            if (ok) {
              deleteRole.mutate(row);
            }
          }}
          canDelete={row.is_editable}
          deleteBlockedReason="Built-in roles cannot be deleted"
          status={{
            checked: row.is_enabled,
            onChange: async (next) => {
              if (!next) {
                const ok = await confirm({
                  title: "Deactivate Role?",
                  consequence: `Users with the role ${row.role_name} lose the screens it grants until it is reactivated.`,
                  confirmLabel: "Deactivate",
                });
                if (!ok) {
                  return;
                }
              }
              toggleRole.mutate(row);
            },
          }}
        />
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title="Manage Roles"
        description="A role is a named set of console screens. Assign one to each admin user."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "User Management" }, { label: "Manage Roles" }]}
        search={{ value: list.searchInput, onChange: list.setSearchInput, placeholder: "Search roles" }}
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-4 w-4" aria-hidden />
            Add Role
          </Button>
        }
      />

      <DataTable
        columns={columns}
        rows={rolesQuery.data?.roles ?? []}
        rowKey={(row) => row.role_id}
        pagination={rolesQuery.data?.pagination}
        loading={rolesQuery.isLoading}
        noun="roles"
        emptyMessage="No roles have been created yet."
        sortBy={list.sortBy}
        sortDir={list.sortDir}
        onSortChange={list.handleSortChange}
        onPageChange={list.setPage}
        onPageSizeChange={list.handlePageSizeChange}
      />

      {confirmDialog}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add role</DialogTitle>
            <DialogDescription>
              Create the role first, then choose which screens it can open.
            </DialogDescription>
          </DialogHeader>

          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              createRole.mutate(newRoleName.trim());
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="role_name" required>
                Role name
              </Label>
              <Input
                id="role_name"
                value={newRoleName}
                onChange={(event) => setNewRoleName(event.target.value)}
                placeholder="Regional Coordinator"
                required
                minLength={2}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreating(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={createRole.isPending}>
                Create role
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={selectedRole !== null} onOpenChange={(open) => !open && setSelectedRole(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Permissions — {selectedRole?.role_name}</DialogTitle>
            <DialogDescription>
              Tick the console screens this role may open. Unticking a section removes everything
              nested under it.
            </DialogDescription>
          </DialogHeader>

          {permissionsQuery.isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading permissions…</p>
          ) : (
            <div className="space-y-4">
              {(permissionsQuery.data ?? []).map((node) => (
                <Card key={node.permission_id}>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        id={`perm-${node.permission_id}`}
                        checked={granted.has(node.permission_id)}
                        onChange={() => togglePermission(node)}
                        className="h-4 w-4 accent-brand-600"
                      />
                      <label htmlFor={`perm-${node.permission_id}`}>{node.menu_name}</label>
                    </CardTitle>
                  </CardHeader>
                  {node.children.length > 0 ? (
                    <CardContent className="grid gap-2 sm:grid-cols-2">
                      {node.children.map((child) => (
                        <label
                          key={child.permission_id}
                          className="flex items-center gap-2 text-sm text-muted-foreground"
                        >
                          <input
                            type="checkbox"
                            checked={granted.has(child.permission_id)}
                            onChange={() => togglePermission(child)}
                            className="h-4 w-4 accent-brand-600"
                          />
                          {child.menu_name}
                        </label>
                      ))}
                    </CardContent>
                  ) : null}
                </Card>
              ))}
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedRole(null)}>
              Cancel
            </Button>
            <Button
              loading={savePermissions.isPending}
              onClick={() => selectedRole && savePermissions.mutate(selectedRole)}
            >
              Save permissions
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Flatten the permission tree into the full id set the API expects. */
function collectIds(nodes: PermissionNode[]): Set<number> {
  const ids = new Set<number>();
  const walk = (list: PermissionNode[]) => {
    for (const node of list) {
      ids.add(node.permission_id);
      walk(node.children);
    }
  };
  walk(nodes);
  return ids;
}

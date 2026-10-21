"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

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
import { LOOKUP_KINDS, mastersApi } from "@/lib/services/masters";
import type { LookupEntry } from "@/types/api";

interface EntryForm {
  id?: number;
  name: string;
  sort_order: number;
  code: string;
  parent_id: string;
}

const EMPTY_ENTRY: EntryForm = { name: "", sort_order: 0, code: "", parent_id: "" };

export default function MastersPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [kind, setKind] = React.useState<string>(LOOKUP_KINDS[0].kind);
  const [form, setForm] = React.useState<EntryForm | null>(null);
  const [search, setSearch] = React.useState("");
  const { confirm, dialog: confirmDialog } = useConfirm();

  const entriesQuery = useQuery({
    queryKey: ["admin", "lookups", kind],
    queryFn: () => mastersApi.listLookup(kind),
  });

  // Sub-categories hang off a category, so that list is needed for the parent picker.
  const parentsQuery = useQuery({
    queryKey: ["admin", "lookups", "category"],
    queryFn: () => mastersApi.listLookup("category"),
    enabled: kind === "sub-category",
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "lookups", kind] });
  }

  const save = useMutation({
    mutationFn: (values: EntryForm) => {
      const payload: Record<string, unknown> = {
        name: values.name,
        sort_order: values.sort_order,
      };
      if (values.code) {
        payload.code = values.code;
      }
      if (values.parent_id) {
        payload.parent_id = Number(values.parent_id);
      }
      return values.id
        ? mastersApi.updateLookup(kind, { ...payload, id: values.id })
        : mastersApi.createLookup(kind, payload);
    },
    onSuccess: (_data, values) => {
      notify(values.id ? "Entry updated." : "Entry created.", "success");
      setForm(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggle = useMutation({
    mutationFn: (entry: LookupEntry) => mastersApi.toggleLookup(kind, entry.id),
    onSuccess: () => {
      notify("Entry status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (entry: LookupEntry) => mastersApi.deleteLookup(kind, entry.id),
    onSuccess: () => {
      notify("Entry deleted.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const columns: Column<LookupEntry>[] = [
    { key: "name", header: "Name", render: (row) => <span className="font-medium">{row.name}</span> },
    { key: "code", header: "Code", render: (row) => row.code ?? "—" },
    { key: "country_code", header: "Scope", render: (row) => row.country_code ?? "Network-wide" },
    { key: "sort_order", header: "Order By", render: (row) => row.sort_order },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={row.name}
          onEdit={() =>
            setForm({
              id: row.id,
              name: row.name,
              sort_order: row.sort_order,
              code: row.code ?? "",
              parent_id: row.parent_id ? String(row.parent_id) : "",
            })
          }
          onDelete={async () => {
            const ok = await confirm({
              title: "Delete Entry?",
              consequence: `${row.name} will be removed from this list.`,
              confirmLabel: "Delete",
            });
            if (ok) {
              remove.mutate(row);
            }
          }}
          status={{
            checked: row.is_enabled,
            onChange: async (next) => {
              if (!next) {
                const ok = await confirm({
                  title: "Deactivate Entry?",
                  consequence: `${row.name} will no longer be offered in dropdowns.`,
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
      ),
    },
  ];

  const activeKind = LOOKUP_KINDS.find((item) => item.kind === kind);
  const term = search.trim().toLowerCase();
  const rows = (entriesQuery.data ?? []).filter(
    (row) => !term || row.name.toLowerCase().includes(term) || (row.code ?? "").toLowerCase().includes(term),
  );

  return (
    <>
      <PageHeader
        title="Master Entry"
        description="The option lists behind the registration form and the API catalogue."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Master Data" }, { label: "Master Entry" }]}
        search={{ value: search, onChange: setSearch, placeholder: "Search entries" }}
        actions={
          <Button onClick={() => setForm({ ...EMPTY_ENTRY })}>
            <Plus className="h-4 w-4" aria-hidden />
            Add Entry
          </Button>
        }
      />

      <FilterBar>
        <FilterField label="List" htmlFor="kind">
          <Select id="kind" value={kind} onChange={(event) => setKind(event.target.value)}>
            {LOOKUP_KINDS.map((item) => (
              <option key={item.kind} value={item.kind}>
                {item.label}
              </option>
            ))}
          </Select>
        </FilterField>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        loading={entriesQuery.isLoading}
        noun="entries"
        emptyMessage={`No ${activeKind?.label.toLowerCase() ?? "entries"} match.`}
      />

      {confirmDialog}

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {form?.id ? "Edit" : "Add"} {activeKind?.label.toLowerCase()}
            </DialogTitle>
            <DialogDescription>
              Entries appear in the order given below, then alphabetically.
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
              <div className="space-y-2">
                <Label htmlFor="entry-name" required>
                  Name
                </Label>
                <Input
                  id="entry-name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  required
                />
              </div>

              {kind === "sub-category" ? (
                <div className="space-y-2">
                  <Label htmlFor="parent" required>
                    Parent category
                  </Label>
                  <Select
                    id="parent"
                    value={form.parent_id}
                    onChange={(event) => setForm({ ...form, parent_id: event.target.value })}
                    required
                  >
                    <option value="">Select a category</option>
                    {parentsQuery.data?.map((parent) => (
                      <option key={parent.id} value={parent.id}>
                        {parent.name}
                      </option>
                    ))}
                  </Select>
                </div>
              ) : null}

              {kind === "participant-type" ? (
                <div className="space-y-2">
                  <Label htmlFor="entry-code">Code</Label>
                  <Input
                    id="entry-code"
                    value={form.code}
                    onChange={(event) => setForm({ ...form, code: event.target.value })}
                    placeholder="AIP"
                  />
                  <p className="text-xs text-muted-foreground">
                    Used in business rules; changing it affects existing participants.
                  </p>
                </div>
              ) : null}

              <div className="space-y-2">
                <Label htmlFor="sort-order">Sort order</Label>
                <Input
                  id="sort-order"
                  type="number"
                  value={form.sort_order}
                  onChange={(event) =>
                    setForm({ ...form, sort_order: Number(event.target.value) || 0 })
                  }
                />
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  {form.id ? "Save changes" : "Add entry"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

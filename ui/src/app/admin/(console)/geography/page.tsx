"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Database, DatabaseZap, Plus } from "lucide-react";

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
import { Badge } from "@/components/ui/badge";
import { EnabledBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { config } from "@/lib/config";
import { mastersApi } from "@/lib/services/masters";
import type { AdminArea } from "@/types/api";

interface Crumb {
  areaId: number | null;
  label: string;
  level: number;
}

interface AreaForm {
  area_id?: number;
  area_code: string;
  area_name: string;
  area_name_local: string;
}

export default function GeographyPage() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [countryCode, setCountryCode] = React.useState(config.defaultCountry);
  const [trail, setTrail] = React.useState<Crumb[]>([{ areaId: null, label: "Country", level: 0 }]);
  const [form, setForm] = React.useState<AreaForm | null>(null);
  const { confirm, dialog: confirmDialog } = useConfirm();

  const current = trail[trail.length - 1]!;
  const childLevel = current.level + 1;

  const countriesQuery = useQuery({
    queryKey: ["admin", "countries"],
    queryFn: mastersApi.listCountries,
  });

  const country = countriesQuery.data?.find((item) => item.country_code === countryCode);
  const levelLabels = country?.level_labels ?? {};
  const childLabel = levelLabels[String(childLevel)] ?? `Level ${childLevel}`;

  const areasQuery = useQuery({
    queryKey: ["admin", "areas", countryCode, current.areaId],
    queryFn: () =>
      mastersApi.listAreas({
        country_code: countryCode,
        parent_id: current.areaId,
        level: current.areaId ? undefined : 1,
        only_enabled: false,
      }),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "areas"] });
  }

  const save = useMutation({
    mutationFn: (values: AreaForm) => {
      const payload = {
        country_code: countryCode,
        area_code: values.area_code,
        area_name: values.area_name,
        area_name_local: values.area_name_local || null,
        level: childLevel,
        parent_id: current.areaId,
      };
      return values.area_id
        ? mastersApi.updateArea({ ...payload, area_id: values.area_id })
        : mastersApi.createArea(payload);
    },
    onSuccess: (_data, values) => {
      notify(values.area_id ? "Area updated." : `${childLabel} added.`, "success");
      setForm(null);
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggle = useMutation({
    mutationFn: (area: AdminArea) => mastersApi.toggleArea(area.area_id),
    onSuccess: () => {
      notify("Area status updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  const toggleApiData = useMutation({
    mutationFn: (area: AdminArea) =>
      mastersApi.toggleAreaApiData(area.area_id, !area.is_api_data_enabled),
    onSuccess: () => {
      notify("API availability updated.", "success");
      invalidate();
    },
    onError: (error: Error) => notify(error.message, "error"),
  });

  function drillInto(area: AdminArea) {
    setTrail((current) => [
      ...current,
      { areaId: area.area_id, label: area.area_name, level: area.level },
    ]);
  }

  function jumpTo(index: number) {
    setTrail((current) => current.slice(0, index + 1));
  }

  const columns: Column<AdminArea>[] = [
    {
      key: "area_name",
      header: "Name",
      render: (row) => (
        <div>
          <p className="font-medium">{row.area_name}</p>
          {row.area_name_local ? <p className="text-xs text-subtle">{row.area_name_local}</p> : null}
        </div>
      ),
    },
    { key: "area_code", header: "Code", render: (row) => row.area_code },
    { key: "level_label", header: "Tier", render: (row) => row.level_label ?? `Level ${row.level}` },
    { key: "child_count", header: "Children", render: (row) => row.child_count },
    {
      key: "is_api_data_enabled",
      header: "API Data",
      render: (row) => (
        <Badge variant={row.is_api_data_enabled ? "success" : "neutral"}>
          {row.is_api_data_enabled ? "Served" : "Not served"}
        </Badge>
      ),
    },
    { key: "is_enabled", header: "Status", render: (row) => <EnabledBadge enabled={row.is_enabled} /> },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <RowActions
          recordLabel={row.area_name}
          onView={row.level < (country?.level_depth ?? 4) ? () => drillInto(row) : undefined}
          onEdit={() =>
            setForm({
              area_id: row.area_id,
              area_code: row.area_code,
              area_name: row.area_name,
              area_name_local: row.area_name_local ?? "",
            })
          }
          extra={[
            {
              icon: row.is_api_data_enabled ? DatabaseZap : Database,
              label: row.is_api_data_enabled
                ? `Stop serving API data for ${row.area_name}`
                : `Serve API data for ${row.area_name}`,
              onClick: () => toggleApiData.mutate(row),
            },
          ]}
          status={{
            checked: row.is_enabled,
            onChange: async (next) => {
              if (!next) {
                const ok = await confirm({
                  title: "Deactivate Area?",
                  consequence: `${row.area_name} will no longer be offered in address pickers.`,
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

  return (
    <>
      <PageHeader
        title="Geography"
        description="Each member country names its own tiers. Use the view icon to open the level below."
        breadcrumbs={[{ label: "Home", href: "/admin/dashboard" }, { label: "Master Data" }, { label: "Geography" }]}
        actions={
          childLevel <= (country?.level_depth ?? 4) ? (
            <Button onClick={() => setForm({ area_code: "", area_name: "", area_name_local: "" })}>
              <Plus className="h-4 w-4" aria-hidden />
              Add {childLabel}
            </Button>
          ) : undefined
        }
      />

      <FilterBar className="sm:items-center">
        <FilterField label="Country" htmlFor="country">
          <Select
            id="country"
            value={countryCode}
            onChange={(event) => {
              setCountryCode(event.target.value);
              setTrail([{ areaId: null, label: "Country", level: 0 }]);
            }}
          >
            {countriesQuery.data?.map((item) => (
              <option key={item.country_code} value={item.country_code}>
                {item.country_name}
              </option>
            ))}
          </Select>
        </FilterField>

        <nav aria-label="Area path" className="flex flex-wrap items-center gap-1 text-sm sm:mt-7">
          {trail.map((crumb, index) => (
            <React.Fragment key={`${crumb.areaId}-${index}`}>
              {index > 0 ? <ChevronRight className="h-4 w-4 text-subtle" aria-hidden /> : null}
              <button
                type="button"
                onClick={() => jumpTo(index)}
                className={
                  index === trail.length - 1 ? "font-semibold text-ink" : "text-subtle hover:text-brand-bright"
                }
              >
                {crumb.label}
              </button>
            </React.Fragment>
          ))}
        </nav>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={areasQuery.data ?? []}
        rowKey={(row) => row.area_id}
        loading={areasQuery.isLoading}
        noun={childLabel.toLowerCase()}
        emptyMessage={`No ${childLabel.toLowerCase()} records here yet.`}
      />

      {confirmDialog}

      <Dialog open={form !== null} onOpenChange={(open) => !open && setForm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{form?.area_id ? "Edit" : "Add"} {childLabel.toLowerCase()}</DialogTitle>
            <DialogDescription>
              Added under {current.label}. The code should match the national dataset.
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
                <Label htmlFor="area_code" required>
                  Code
                </Label>
                <Input
                  id="area_code"
                  value={form.area_code}
                  onChange={(event) => setForm({ ...form, area_code: event.target.value })}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="area_name" required>
                  Name
                </Label>
                <Input
                  id="area_name"
                  value={form.area_name}
                  onChange={(event) => setForm({ ...form, area_name: event.target.value })}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="area_name_local">Local name</Label>
                <Input
                  id="area_name_local"
                  value={form.area_name_local}
                  onChange={(event) => setForm({ ...form, area_name_local: event.target.value })}
                  placeholder="Name in the national language"
                />
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setForm(null)}>
                  Cancel
                </Button>
                <Button type="submit" loading={save.isPending}>
                  Add {childLabel.toLowerCase()}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

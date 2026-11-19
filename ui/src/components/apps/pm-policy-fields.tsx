"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { adminAppsApi } from "@/lib/services/apps";
import type { PmPolicy } from "@/types/api";

type Kind = "" | "registry" | "use_case";

/** "a, b , a" -> ["a", "b"] */
function codes(text: string): string[] {
  return [...new Set(text.split(",").map((value) => value.trim()).filter(Boolean))];
}

/**
 * The OpenG2P Partner Management access policy an API product asks for: a registry's data
 * scopes or an exchange use case. Approving the product for an app files a policy request in
 * that app's environment's PM; PM's staff decide. Choices come from PM's catalogue when it
 * can be read; other fields of an existing policy (durations, ID types...) are kept.
 */
export function PmPolicyFields({
  value,
  onChange,
}: {
  value: PmPolicy | null | undefined;
  onChange: (value: PmPolicy | null) => void;
}) {
  const catalogueQuery = useQuery({
    queryKey: ["admin", "api-products", "pm-catalogue"],
    queryFn: () => adminAppsApi.pmCatalogue(),
    staleTime: 5 * 60 * 1000,
  });
  const sources = catalogueQuery.data?.sources ?? [];
  const controllers = sources.filter((s) => s.kind === "scopes" && s.data_controller);
  const useCases = sources.filter((s) => s.kind === "use_cases").flatMap((s) => s.items);
  const kind: Kind = value?.use_case !== undefined && value?.use_case !== null ? "use_case" : value ? "registry" : "";
  const scopeChoices = controllers.find((s) => s.data_controller === value?.data_controller)?.items ?? [];
  // Free text while typing; parsed into lists on blur.
  const [scopesText, setScopesText] = React.useState((value?.allowed_data_scopes ?? []).join(", "));
  const [purposesText, setPurposesText] = React.useState((value?.allowed_purposes ?? []).join(", "));

  function setKind(next: Kind) {
    if (next === "") onChange(null);
    else if (next === "registry") onChange({ data_controller: "", allowed_data_scopes: [] });
    else onChange({ use_case: "" });
    setScopesText("");
    setPurposesText("");
  }

  function addScope(id: string) {
    const scopes = codes(`${scopesText},${id}`);
    setScopesText(scopes.join(", "));
    onChange({ ...value, allowed_data_scopes: scopes });
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:col-span-2">
      <div className="flex flex-col gap-2">
        <Label htmlFor="ap-pm-kind">Data access policy</Label>
        <Select id="ap-pm-kind" value={kind} onChange={(event) => setKind(event.target.value as Kind)}>
          <option value="">None: the product only opens APIs at the gateway</option>
          <option value="registry">A registry&apos;s data scopes</option>
          <option value="use_case">An exchange use case</option>
        </Select>
        <p className="text-xs text-subtle">
          Approving this product for an app files this policy for the partner
          {catalogueQuery.data?.backend === "cm"
            ? " in the Consent Manager (a widening waits for AWE approval)"
            : " in Partner Management (its staff decide; UAT may be automatic)"}
          . The partner sees the status under My Apps.
          {catalogueQuery.data && !catalogueQuery.data.enabled ? " No policy backend is configured here." : ""}
          {catalogueQuery.data?.backend === "cm" ? " Use cases are not supported by the Consent Manager." : ""}
          {catalogueQuery.data?.error ? ` Catalogue unavailable: ${catalogueQuery.data.error}` : ""}
        </p>
      </div>

      {kind === "registry" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="ap-pm-controller">Registry (data controller)</Label>
            <Input
              id="ap-pm-controller"
              list="ap-pm-controllers"
              placeholder="e.g. farmer_registry"
              value={value?.data_controller ?? ""}
              onChange={(event) => onChange({ ...value, data_controller: event.target.value.trim() })}
            />
            <datalist id="ap-pm-controllers">
              {controllers.map((s) => (
                <option key={s.data_controller} value={s.data_controller ?? ""}>
                  {s.label}
                </option>
              ))}
            </datalist>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="ap-pm-scopes">Data scopes</Label>
            <Input
              id="ap-pm-scopes"
              placeholder="Comma-separated"
              value={scopesText}
              onChange={(event) => setScopesText(event.target.value)}
              onBlur={() => onChange({ ...value, allowed_data_scopes: codes(scopesText) })}
            />
            {scopeChoices.length ? (
              <div className="flex flex-wrap gap-1">
                {scopeChoices.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className="rounded bg-muted px-1.5 py-0.5 text-xs hover:bg-brand-50"
                    title={item.description ?? item.fields?.join(", ") ?? ""}
                    onClick={() => addScope(item.id)}
                  >
                    + {item.label ?? item.id}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex flex-col gap-2 sm:col-span-2">
            <Label htmlFor="ap-pm-purposes">Purposes (optional)</Label>
            <Input
              id="ap-pm-purposes"
              placeholder="Comma-separated; empty = any"
              value={purposesText}
              onChange={(event) => setPurposesText(event.target.value)}
              onBlur={() => onChange({ ...value, allowed_purposes: codes(purposesText) })}
            />
          </div>
        </div>
      ) : null}

      {kind === "use_case" ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor="ap-pm-use-case">Use case (name@major)</Label>
          <Input
            id="ap-pm-use-case"
            list="ap-pm-use-cases"
            placeholder="e.g. loan-profile@1"
            value={value?.use_case ?? ""}
            onChange={(event) => onChange({ ...value, use_case: event.target.value.trim() })}
          />
          <datalist id="ap-pm-use-cases">
            {useCases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label ?? item.purpose ?? ""}
              </option>
            ))}
          </datalist>
        </div>
      ) : null}

      {kind ? (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(value?.allow_partner_consents)}
            onChange={(event) => onChange({ ...value, allow_partner_consents: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-brand-600"
          />
          <span>
            Partner may present consents it collected itself
            <span className="block text-xs text-subtle">
              The Consent Manager then accepts them; it cannot verify the subject agreed.
            </span>
          </span>
        </label>
      ) : null}
    </div>
  );
}

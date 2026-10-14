/** Support query vocabulary shared by the portal and the console. */

/** Same two types as the reference portal's "Support & Queries" form. */
export const QUERY_TYPES = [
  { value: 1, label: "APIs" },
  { value: 2, label: "Other" },
] as const;

export const QUERY_STATUSES = [
  { value: 0, label: "Open", variant: "warning" },
  { value: 1, label: "In progress", variant: "info" },
  { value: 2, label: "Answered", variant: "success" },
  { value: 3, label: "Closed", variant: "neutral" },
] as const;

export function queryTypeLabel(value: number | null): string {
  return QUERY_TYPES.find((type) => type.value === value)?.label ?? "Other";
}

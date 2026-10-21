"use client";

import * as React from "react";
import Link from "next/link";
import { Eye, SquarePen, Trash2, type LucideIcon } from "lucide-react";

import { StatusToggle } from "@/components/ui/status-toggle";
import { cn } from "@/lib/utils";

const ACTION_BUTTON =
  "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-40";

const TONES = {
  default: "bg-action hover:bg-action-hover",
  danger: "bg-red-600 hover:bg-red-700",
  warning: "bg-amber-600 hover:bg-amber-700",
} as const;

interface IconActionProps {
  icon: LucideIcon;
  /** Tooltip and accessible name. */
  label: string;
  onClick?: () => void;
  /** Render as a link instead of a button. */
  href?: string;
  disabled?: boolean;
  tone?: keyof typeof TONES;
}

/** One 32px square icon button; the only way a table row renders an action. */
export function IconAction({ icon: Icon, label, onClick, href, disabled, tone = "default" }: IconActionProps) {
  const className = cn(ACTION_BUTTON, TONES[tone]);
  if (href && !disabled) {
    return (
      <Link href={href} className={className} title={label} aria-label={label}>
        <Icon className="h-4 w-4" aria-hidden />
      </Link>
    );
  }
  return (
    <button type="button" className={className} title={label} aria-label={label} onClick={onClick} disabled={disabled}>
      <Icon className="h-4 w-4" aria-hidden />
    </button>
  );
}

export interface ExtraAction {
  icon: LucideIcon;
  label: string;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  tone?: keyof typeof TONES;
}

interface RowActionsProps {
  /** Names the record in tooltips and screen-reader labels, e.g. "user Jane Doe". */
  recordLabel: string;
  onView?: () => void;
  viewHref?: string;
  onEdit?: () => void;
  editHref?: string;
  canEdit?: boolean;
  onDelete?: () => void;
  canDelete?: boolean;
  deleteBlockedReason?: string;
  /** Extra actions, shown between edit and delete. */
  extra?: ExtraAction[];
  /** Enable/disable switch, always last. */
  status?: { checked: boolean; onChange: (next: boolean) => void; disabled?: boolean };
}

/**
 * Row actions in a fixed order — view · edit · extras · delete · status —
 * so every admin table reads the same way.
 */
export function RowActions({
  recordLabel,
  onView,
  viewHref,
  onEdit,
  editHref,
  canEdit = true,
  onDelete,
  canDelete = true,
  deleteBlockedReason,
  extra = [],
  status,
}: RowActionsProps) {
  return (
    <div className="flex items-center gap-3">
      {onView || viewHref ? (
        <IconAction icon={Eye} label={`View ${recordLabel}`} onClick={onView} href={viewHref} />
      ) : null}
      {onEdit || editHref ? (
        <IconAction
          icon={SquarePen}
          label={`Edit ${recordLabel}`}
          onClick={onEdit}
          href={editHref}
          disabled={!canEdit}
        />
      ) : null}
      {extra.map((action) => (
        <IconAction key={action.label} {...action} />
      ))}
      {onDelete ? (
        <IconAction
          icon={Trash2}
          label={canDelete ? `Delete ${recordLabel}` : (deleteBlockedReason ?? "Cannot be deleted")}
          onClick={onDelete}
          disabled={!canDelete}
        />
      ) : null}
      {status ? (
        <StatusToggle
          checked={status.checked}
          onChange={status.onChange}
          disabled={status.disabled}
          label={`Active status of ${recordLabel}`}
        />
      ) : null}
    </div>
  );
}

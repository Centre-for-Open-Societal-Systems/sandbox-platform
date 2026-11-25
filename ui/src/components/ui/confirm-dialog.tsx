"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CircleAlert, CircleCheck, CircleX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Tone = "danger" | "warning" | "primary";

const ICONS: Record<Tone, { icon: typeof CircleX; className: string }> = {
  danger: { icon: CircleX, className: "bg-[#FFEBEC] text-[#DA131A]" },
  warning: { icon: CircleAlert, className: "bg-amber-50 text-amber-600" },
  primary: { icon: CircleCheck, className: "bg-[#E5FFF0] text-[#2E7D32]" },
};

export interface ConfirmOptions {
  title: string;
  /** What happens if the user confirms. */
  consequence?: React.ReactNode;
  confirmLabel?: string;
  tone?: Tone;
}

interface ConfirmDialogProps extends ConfirmOptions {
  open: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Centred confirmation card used before deleting or deactivating anything. */
export function ConfirmDialog({
  open,
  title,
  consequence,
  confirmLabel = "Confirm",
  tone = "danger",
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { icon: Icon, className } = ICONS[tone];
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[60] bg-black/40" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-[60] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-[#fafafa] p-6 text-center text-ink shadow-xl">
          <span className={cn("mx-auto flex h-20 w-20 items-center justify-center rounded-full", className)}>
            <Icon className="h-9 w-9" aria-hidden />
          </span>
          <DialogPrimitive.Title className="mt-6 text-xl font-bold">{title}</DialogPrimitive.Title>
          {consequence ? (
            <DialogPrimitive.Description className="mt-4 text-[0.95rem] text-subtle">
              {consequence}
            </DialogPrimitive.Description>
          ) : null}
          <div className="mt-8 flex justify-center gap-4">
            <Button variant="outline" className="min-w-[90px]" onClick={onCancel} disabled={loading}>
              Cancel
            </Button>
            <Button
              variant={tone === "danger" ? "destructive" : "primary"}
              className="min-w-[90px]"
              loading={loading}
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/**
 * `const { confirm, dialog } = useConfirm();` then
 * `if (await confirm({ title: "Delete user?" })) remove.mutate(row);`
 * and render `{dialog}` once in the page.
 */
export function useConfirm() {
  const [state, setState] = React.useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);

  const confirm = React.useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setState({ ...options, resolve })),
    [],
  );

  function close(ok: boolean) {
    state?.resolve(ok);
    setState(null);
  }

  const dialog = (
    <ConfirmDialog
      open={state !== null}
      title={state?.title ?? ""}
      consequence={state?.consequence}
      confirmLabel={state?.confirmLabel}
      tone={state?.tone}
      onConfirm={() => close(true)}
      onCancel={() => close(false)}
    />
  );

  return { confirm, dialog };
}

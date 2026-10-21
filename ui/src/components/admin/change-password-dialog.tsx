"use client";

import * as React from "react";
import { Check, Circle, Eye, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";
import { PASSWORD_RULES, isStrongPassword } from "@/lib/password-rules";
import { adminApi } from "@/lib/services/admin";
import { cn } from "@/lib/utils";

const EMPTY = { current: "", next: "", confirm: "" };

interface ChangePasswordDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after the change; the server has ended every session by then. */
  onChanged: () => void;
}

/** Console "Change Password": the backend signs the admin out everywhere afterwards. */
export function ChangePasswordDialog({ open, onOpenChange, onChanged }: ChangePasswordDialogProps) {
  const { notify } = useToast();
  const [form, setForm] = React.useState(EMPTY);
  const [show, setShow] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;

  function close(next: boolean) {
    if (!next) {
      setForm(EMPTY);
      setError(null);
    }
    onOpenChange(next);
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isStrongPassword(form.next)) {
      setError("The new password does not meet all the rules.");
      return;
    }
    if (form.next !== form.confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await adminApi.changePassword(form.current, form.next);
      notify("Password changed. Please sign in again with the new password.", "success");
      close(false);
      onChanged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to change the password right now.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change Password</DialogTitle>
          <DialogDescription>You will be signed out on every device once it is changed.</DialogDescription>
        </DialogHeader>

        <form id="admin-change-password" onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="admin-current-password" required>
              Current password
            </Label>
            <Input
              id="admin-current-password"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              value={form.current}
              onChange={(event) => setForm({ ...form, current: event.target.value })}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="admin-new-password" required>
              New password
            </Label>
            <div className="relative">
              <Input
                id="admin-new-password"
                type={show ? "text" : "password"}
                autoComplete="new-password"
                value={form.next}
                onChange={(event) => setForm({ ...form, next: event.target.value })}
                className="pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShow((value) => !value)}
                aria-label={show ? "Hide passwords" : "Show passwords"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-slate-600"
              >
                {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
              </button>
            </div>
            <ul className="grid grid-cols-2 gap-1.5" aria-label="Password rules">
              {PASSWORD_RULES.map((rule) => {
                const met = rule.test(form.next);
                return (
                  <li
                    key={rule.label}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium",
                      met ? "bg-brand-50 text-brand-700" : "bg-slate-50 text-slate-500",
                    )}
                  >
                    {met ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Circle className="h-3 w-3" aria-hidden />}
                    {rule.label}
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="admin-confirm-password" required>
              Confirm new password
            </Label>
            <Input
              id="admin-confirm-password"
              type={show ? "text" : "password"}
              autoComplete="new-password"
              value={form.confirm}
              aria-invalid={mismatch}
              onChange={(event) => setForm({ ...form, confirm: event.target.value })}
              required
            />
            {mismatch ? <span className="text-xs text-red-600">Passwords do not match.</span> : null}
          </div>
          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600">
              {error}
            </p>
          ) : null}
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button type="submit" form="admin-change-password" loading={saving}>
            Change password
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

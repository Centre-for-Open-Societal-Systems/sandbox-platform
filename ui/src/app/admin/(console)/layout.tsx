"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, KeyRound, LogOut, UserRound } from "lucide-react";

import { ChangePasswordDialog } from "@/components/admin/change-password-dialog";
import { AdminSidebar } from "@/components/layout/admin-sidebar";
import { useToast } from "@/components/ui/toast";
import { adminApi } from "@/lib/services/admin";
import { useHydrated } from "@/hooks/use-hydrated";
import { adminCan, adminSession } from "@/lib/session";
import { cn, initials } from "@/lib/utils";
import type { AdminSession } from "@/types/api";

const COLLAPSED_KEY = "oan.admin.sidebarCollapsed";

const MOBILE_QUERY = "(max-width: 767px)";

function subscribeMobile(onChange: () => void) {
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useIsMobile() {
  // False on the server and during hydration, so both renders agree.
  return React.useSyncExternalStore(
    subscribeMobile,
    () => window.matchMedia(MOBILE_QUERY).matches,
    () => false,
  );
}

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    // Storage can be unavailable (private mode); the sidebar just starts expanded.
    return false;
  }
}

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { notify } = useToast();
  const isMobile = useIsMobile();
  const hydrated = useHydrated();
  // Session storage only exists in the browser, so read it once hydrated.
  const session = React.useMemo<AdminSession | null>(() => (hydrated ? adminSession.get() : null), [hydrated]);
  // null = follow the stored preference until the user toggles.
  const [collapsedChoice, setCollapsedChoice] = React.useState<boolean | null>(null);
  const collapsed = collapsedChoice ?? (hydrated && readCollapsed());
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [changingPassword, setChangingPassword] = React.useState(false);

  React.useEffect(() => {
    if (hydrated && !session) {
      router.replace("/admin/login");
    }
  }, [hydrated, session, router]);

  // The console palette is light only, like the template it follows.
  React.useEffect(() => {
    const root = document.documentElement;
    const previous = root.dataset.theme;
    root.dataset.theme = "light";
    return () => {
      if (previous) {
        root.dataset.theme = previous;
      } else {
        delete root.dataset.theme;
      }
    };
  }, []);

  function toggleMenu() {
    if (isMobile) {
      setDrawerOpen((open) => !open);
      return;
    }
    const next = !collapsed;
    setCollapsedChoice(next);
    try {
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      // Not persisted; fine.
    }
  }

  async function handleSignOut() {
    try {
      await adminApi.logout();
    } catch {
      // The local session is cleared either way; a failed call must not trap
      // the user in the console.
    }
    adminSession.clear();
    notify("Signed out.", "info");
    router.replace("/admin/login");
  }

  if (!session) {
    return null;
  }

  const displayName = [session.first_name, session.last_name].filter(Boolean).join(" ") || session.email_id || "Administrator";
  const roleLabel = session.is_master ? "Master administrator" : session.role || "Administrator";
  const railCollapsed = collapsed && !isMobile;
  const menuExpanded = isMobile ? drawerOpen : !collapsed;

  return (
    <div
      className={cn(
        "admin-console relative grid h-dvh grid-cols-1 overflow-hidden bg-white transition-[grid-template-columns] duration-200",
        railCollapsed ? "md:grid-cols-[74px_1fr]" : "md:grid-cols-[256px_1fr]",
      )}
    >
      <div
        className={cn(
          "md:h-dvh md:min-h-0",
          "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-[1200] max-md:w-[260px] max-md:max-w-[82vw] max-md:transition-transform max-md:duration-200",
          drawerOpen ? "max-md:translate-x-0 max-md:shadow-[0_12px_40px_rgba(15,25,18,0.35)]" : "max-md:-translate-x-full",
        )}
      >
        <React.Suspense fallback={null}>
          <AdminSidebar
            can={adminCan}
            collapsed={railCollapsed}
            onNavigate={() => setDrawerOpen(false)}
            onClose={isMobile ? () => setDrawerOpen(false) : undefined}
          />
        </React.Suspense>
      </div>

      {drawerOpen ? (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-[1100] bg-[rgba(15,25,18,0.5)] md:hidden"
        />
      ) : null}

      <div className="flex h-dvh min-h-0 min-w-0 flex-col overflow-hidden">
        <header className="relative z-[55] flex shrink-0 items-center justify-between border-b border-[#eef0ee] bg-white px-4 py-3 md:px-7">
          <div className="flex min-w-0 items-center gap-4">
            <button
              type="button"
              onClick={toggleMenu}
              aria-label={menuExpanded ? "Collapse sidebar" : "Expand sidebar"}
              aria-expanded={menuExpanded}
              className="inline-flex items-center justify-center rounded-lg border border-[#d6e4d6] p-1.5 text-brand-bright hover:bg-slate-100"
            >
              <SidebarToggleIcon expanded={menuExpanded} />
            </button>
            <span className="truncate text-[0.98rem] text-slate-700 max-md:max-w-[46vw]">
              Welcome, <strong className="font-semibold text-brand-bright">{displayName}</strong>
            </span>
          </div>

          <UserMenu
            name={displayName}
            role={roleLabel}
            onChangePassword={() => setChangingPassword(true)}
            onSignOut={handleSignOut}
          />
        </header>

        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-7">{children}</main>
      </div>

      <ChangePasswordDialog
        open={changingPassword}
        onOpenChange={setChangingPassword}
        onChanged={() => {
          // The server already ended every session; just drop the local copy.
          adminSession.clear();
          router.replace("/admin/login");
        }}
      />
    </div>
  );
}

function SidebarToggleIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-5 w-5"
      aria-hidden
    >
      <path d="M3 6h11" />
      <path d="M3 12h7" />
      <path d="M3 18h11" />
      <path d={expanded ? "M21 9l-3 3 3 3" : "M18 9l3 3-3 3"} />
    </svg>
  );
}

interface UserMenuProps {
  name: string;
  role: string;
  onChangePassword: () => void;
  onSignOut: () => void;
}

function UserMenu({ name, role, onChangePassword, onSignOut }: UserMenuProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) {
      return;
    }
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-full border border-hairline bg-white py-1.5 pr-2.5 pl-1.5 text-[0.92rem] font-semibold text-ink"
      >
        <span className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-brand-600 text-xs text-white">
          {initials(name)}
        </span>
        <span className="hidden max-w-40 truncate lg:inline">{name}</span>
        <ChevronDown className="hidden h-4 w-4 text-subtle lg:inline" aria-hidden />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute top-[calc(100%+8px)] right-0 z-[56] min-w-[200px] rounded-[10px] border border-hairline bg-white p-1.5 shadow-[0_12px_30px_rgba(0,0,0,0.12)]"
        >
          <p className="px-3 pt-1.5 pb-2 text-xs text-subtle">{role}</p>
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink">
            <UserRound className="h-4 w-4" aria-hidden />
            <span className="truncate">{name}</span>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onChangePassword();
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink hover:bg-surface-soft"
          >
            <KeyRound className="h-4 w-4" aria-hidden />
            Change Password
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={onSignOut}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-700 hover:bg-red-50"
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  ChevronDown,
  FileText,
  Gauge,
  Globe2,
  Layers,
  Leaf,
  MapPinned,
  MessageSquareText,
  ScrollText,
  Settings2,
  Users,
  UsersRound,
  X,
  type LucideIcon,
} from "lucide-react";

import { config } from "@/lib/config";
import { Permission, type PermissionId } from "@/lib/permissions";
import { cn } from "@/lib/utils";

interface NavChild {
  href: string;
  label: string;
  permission?: PermissionId;
}

interface NavItem {
  label: string;
  icon: LucideIcon;
  href?: string;
  permission?: PermissionId;
  children?: NavChild[];
}

interface NavSection {
  caption: string | null;
  items: NavItem[];
}

/**
 * Sidebar structure. Each entry names the permission that gates it, so the
 * menu and the API guard stay in step.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    caption: null,
    items: [{ label: "Dashboard", icon: Gauge, href: "/admin/dashboard" }],
  },
  {
    caption: "Participants",
    items: [
      {
        label: "Manage Participant",
        icon: UsersRound,
        permission: Permission.PARTICIPANT_MANAGEMENT,
        children: [
          { href: "/admin/participants", label: "All Participants", permission: Permission.ALL_PARTICIPANTS },
          { href: "/admin/participants?tab=uat", label: "UAT Participants", permission: Permission.UAT_PARTICIPANTS },
          {
            href: "/admin/participants?tab=uat-pending",
            label: "UAT Approval Pending",
            permission: Permission.UAT_APPROVAL_PENDING,
          },
          {
            href: "/admin/participants?tab=uat-rejected",
            label: "UAT Rejected",
            permission: Permission.UAT_REJECTED_PARTICIPANTS,
          },
          { href: "/admin/participants?tab=prod", label: "Prod Participants", permission: Permission.PROD_PARTICIPANTS },
          {
            href: "/admin/participants?tab=prod-pending",
            label: "Prod Approval Pending",
            permission: Permission.PROD_APPROVAL_PENDING,
          },
          {
            href: "/admin/participants?tab=prod-rejected",
            label: "Prod Rejected",
            permission: Permission.PROD_REJECTED_PARTICIPANTS,
          },
        ],
      },
      { label: "User Queries", icon: MessageSquareText, href: "/admin/queries", permission: Permission.USER_QUERIES },
    ],
  },
  {
    caption: "Catalogue",
    items: [{ label: "API Catalogue", icon: Layers, href: "/admin/products", permission: Permission.API_CATALOGUE }],
  },
  {
    caption: "Administration",
    items: [
      {
        label: "User Management",
        icon: Users,
        permission: Permission.ADMIN_USER_MANAGEMENT,
        children: [
          { href: "/admin/users", label: "Admin Users", permission: Permission.AUM_VIEW_USER_LIST },
          { href: "/admin/roles", label: "Manage Roles", permission: Permission.AUM_MANAGE_ROLES },
        ],
      },
      { label: "CMS", icon: FileText, href: "/admin/content", permission: Permission.CMS },
    ],
  },
  {
    caption: "Master Data",
    items: [
      { label: "Master Entry", icon: Settings2, href: "/admin/masters", permission: Permission.CATEGORY },
      { label: "Geography", icon: MapPinned, href: "/admin/geography", permission: Permission.MANAGE_GEOGRAPHY },
    ],
  },
  {
    caption: "Audit",
    items: [
      {
        label: "Audit Logs",
        icon: ScrollText,
        permission: Permission.AUDIT_LOGS,
        children: [
          { href: "/admin/logs/api-history", label: "API History", permission: Permission.API_HISTORY },
          { href: "/admin/logs/user-tracking", label: "User Tracking", permission: Permission.USER_TRACKING },
        ],
      },
    ],
  },
];

const NAV_CAPTION = "px-3.5 pb-1.5 text-[0.7rem] font-semibold tracking-wide uppercase text-nav-active";
const NAV_ITEM_BASE = "flex w-full items-center gap-3 rounded-lg px-3.5 py-3 text-[0.95rem] font-medium transition-colors";
const NAV_ITEM_ACTIVE = "bg-nav-active font-semibold text-white [&_svg]:text-brand-gold";
const NAV_ITEM_IDLE = "text-ink hover:bg-sidebar-line";

function navItemClass(active: boolean, collapsed: boolean) {
  return cn(NAV_ITEM_BASE, collapsed && "justify-center px-0", active ? NAV_ITEM_ACTIVE : NAV_ITEM_IDLE);
}

interface AdminSidebarProps {
  can: (permission: number) => boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
  /** Shown on the mobile drawer only. */
  onClose?: () => void;
}

export function AdminSidebar({ can, collapsed = false, onNavigate, onClose }: AdminSidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = pathname + (searchParams.toString() ? `?${searchParams.toString()}` : "");

  // A child is active on an exact match; "/admin/products/2" still lights up
  // "/admin/products" because it starts with it.
  const isChildActive = (href: string) =>
    href.includes("?") ? current === href : pathname === href && !searchParams.get("tab");
  const isItemActive = (item: NavItem) =>
    item.href
      ? pathname === item.href || pathname.startsWith(`${item.href}/`)
      : (item.children ?? []).some((child) => isChildActive(child.href) || pathname.startsWith(`${child.href}/`));

  const sections = NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items
      .filter((item) => !item.permission || can(item.permission))
      .map((item) => ({
        ...item,
        children: item.children?.filter((child) => !child.permission || can(child.permission)),
      }))
      .filter((item) => item.href || (item.children && item.children.length > 0)),
  })).filter((section) => section.items.length > 0);

  return (
    <aside className="flex h-full flex-col border-r border-sidebar-line bg-sidebar-bg">
      <div className={cn("flex items-center gap-2.5 pt-6 pb-4", collapsed ? "justify-center px-2.5" : "px-4")}>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-b from-brand-bright to-brand-deep text-white">
          <Leaf className="h-5 w-5" aria-hidden />
        </span>
        {!collapsed ? (
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate font-semibold text-brand-deep">{config.siteName}</span>
            <span className="block text-xs text-subtle">Sandbox console</span>
          </span>
        ) : null}
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="flex h-[34px] w-[34px] items-center justify-center rounded-lg hover:bg-sidebar-line md:hidden"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        ) : null}
      </div>

      <div className={cn("scrollbar-none min-h-0 flex-1 overflow-y-auto pb-6", collapsed ? "px-2.5" : "px-4")}>
        <nav className="flex flex-col gap-4" aria-label="Console">
          {sections.map((section) => (
            <div key={section.caption ?? "main"} className="flex flex-col gap-1.5">
              {section.caption && !collapsed ? <p className={NAV_CAPTION}>{section.caption}</p> : null}
              {section.items.map((item) =>
                item.children ? (
                  collapsed ? (
                    <RailFlyout
                      key={item.label}
                      item={item}
                      active={isItemActive(item)}
                      isChildActive={isChildActive}
                      onNavigate={onNavigate}
                    />
                  ) : (
                    <NavGroup
                      key={item.label}
                      item={item}
                      active={isItemActive(item)}
                      isChildActive={isChildActive}
                      onNavigate={onNavigate}
                    />
                  )
                ) : (
                  <Link
                    key={item.label}
                    href={item.href!}
                    onClick={onNavigate}
                    title={collapsed ? item.label : undefined}
                    aria-current={isItemActive(item) ? "page" : undefined}
                    className={navItemClass(isItemActive(item), collapsed)}
                  >
                    <item.icon className="h-5 w-5 shrink-0" aria-hidden />
                    {!collapsed ? <span className="truncate">{item.label}</span> : (
                      <span className="sr-only">{item.label}</span>
                    )}
                  </Link>
                ),
              )}
            </div>
          ))}

          <div className="border-t border-sidebar-line pt-4">
            <Link href="/" className={navItemClass(false, collapsed)} title={collapsed ? "View public site" : undefined}>
              <Globe2 className="h-5 w-5 shrink-0" aria-hidden />
              {!collapsed ? <span>View public site</span> : <span className="sr-only">View public site</span>}
            </Link>
          </div>
        </nav>
      </div>
    </aside>
  );
}

interface GroupProps {
  item: NavItem;
  active: boolean;
  isChildActive: (href: string) => boolean;
  onNavigate?: () => void;
}

/** Expanded group: follows the route unless the user toggled it. */
function NavGroup({ item, active, isChildActive, onNavigate }: GroupProps) {
  const [override, setOverride] = React.useState<boolean | null>(null);
  const open = override ?? active;

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOverride(!open)}
        className={navItemClass(active, false)}
      >
        <item.icon className="h-5 w-5 shrink-0" aria-hidden />
        <span className="flex-1 truncate text-left">{item.label}</span>
        <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div className="mt-1 ml-4 flex flex-col gap-1 border-l border-[#d5e5d5] pl-3">
          {item.children!.map((child) => {
            const childActive = isChildActive(child.href);
            return (
              <Link
                key={child.href}
                href={child.href}
                onClick={onNavigate}
                aria-current={childActive ? "page" : undefined}
                className={cn(
                  "rounded-lg px-3 py-2 text-[0.9rem] transition-colors",
                  childActive ? "bg-[#dcebdc] font-semibold text-brand-deep" : "text-slate-600 hover:bg-sidebar-line",
                )}
              >
                {child.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/** Collapsed rail: the group's children open in a flyout beside the icon. */
function RailFlyout({ item, active, isChildActive, onNavigate }: GroupProps) {
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const [position, setPosition] = React.useState<{ top: number; left: number } | null>(null);
  const closeTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  function open() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
    }
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setPosition({ top: rect.top, left: rect.right + 8 });
    }
  }

  function scheduleClose() {
    closeTimer.current = setTimeout(() => setPosition(null), 120);
  }

  React.useEffect(() => {
    if (!position) {
      return;
    }
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setPosition(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [position]);

  return (
    <div onMouseEnter={open} onMouseLeave={scheduleClose}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={position !== null}
        aria-label={item.label}
        title={item.label}
        onFocus={open}
        onClick={() => (position ? setPosition(null) : open())}
        className={navItemClass(active, true)}
      >
        <item.icon className="h-5 w-5 shrink-0" aria-hidden />
      </button>
      {position ? (
        <div
          role="menu"
          style={{ top: position.top, left: position.left }}
          className="fixed z-[1150] min-w-[220px] overflow-hidden rounded-xl border border-[#d5e5d5] bg-white shadow-[0_10px_30px_rgba(20,40,25,0.18)]"
          onMouseEnter={open}
          onMouseLeave={scheduleClose}
        >
          <p className="border-b border-[#eef1ee] bg-[#f3faf4] px-4 py-3 text-sm font-semibold text-ink">{item.label}</p>
          <div className="flex flex-col p-1.5">
            {item.children!.map((child) => (
              <Link
                key={child.href}
                role="menuitem"
                href={child.href}
                onClick={() => {
                  setPosition(null);
                  onNavigate?.();
                }}
                className={cn(
                  "rounded-lg px-3 py-2 text-[0.9rem] transition-colors",
                  isChildActive(child.href) ? "bg-[#dcebdc] font-semibold text-brand-deep" : "text-slate-600 hover:bg-sidebar-line",
                )}
              >
                {child.label}
              </Link>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

import { createElement } from "react";
import {
  Boxes,
  CloudSun,
  Landmark,
  Map as MapIcon,
  Sprout,
  Users,
  Wheat,
  type LucideIcon,
} from "lucide-react";

/** Picks an icon from the category name; categories are CMS-managed so match on keywords. */
const CATEGORY_ICONS: Array<[RegExp, LucideIcon]> = [
  [/farmer|registry|identity|profile/i, Users],
  [/land|plot|parcel|geo/i, MapIcon],
  [/crop|season|yield/i, Wheat],
  [/weather|advis|soil|climate/i, CloudSun],
  [/scheme|benefit|subsid|finance|credit|insur/i, Landmark],
  [/input|market|seed|fertili/i, Sprout],
];

export function iconFor(category: string | null | undefined): LucideIcon {
  return CATEGORY_ICONS.find(([pattern]) => pattern.test(category ?? ""))?.[1] ?? Boxes;
}

/** Renders the icon for a category. createElement keeps the lookup from reading as a component made during render. */
export function CategoryIcon({ category, className }: { category: string | null | undefined; className?: string }) {
  return createElement(iconFor(category), { className, "aria-hidden": true });
}

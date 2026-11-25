import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/** Square-cornered status chip, following the admin template's status tones. */
const badgeVariants = cva(
  "inline-flex items-center rounded px-2 py-1 text-[0.7rem] font-semibold leading-4 whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "bg-[#E5E5E5] text-[#7A7A7A]",
        success: "bg-[#E5FFF0] text-[#2E7D32]",
        warning: "bg-[#FFF1CC] text-[#B26A00]",
        danger: "bg-[#FFEBEC] text-[#DA131A]",
        info: "bg-[#DCEBFF] text-[#1A5FA8]",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

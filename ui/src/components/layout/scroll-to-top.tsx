"use client";

import * as React from "react";
import { ArrowUp } from "lucide-react";

import { cn } from "@/lib/utils";

/** Round "back to top" button that appears after scrolling down 300px. */
export function ScrollToTop() {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 300);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <button
      type="button"
      aria-label="Back to top"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      className={cn(
        "fixed bottom-8 right-8 z-50 flex h-11 w-11 items-center justify-center rounded-full bg-brand-gold text-white shadow-[0_2px_10px_rgba(0,0,0,0.2)] transition-all hover:bg-brand-600",
        visible ? "visible opacity-100" : "invisible opacity-0",
      )}
    >
      <ArrowUp className="h-5 w-5" aria-hidden />
    </button>
  );
}

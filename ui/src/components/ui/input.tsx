import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, type = "text", ...props }, ref) {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          "flex h-10 w-full rounded-[10px] border border-hairline bg-white px-4 py-2 text-[0.92rem] text-ink",
          "focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none",
          "placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50",
          "aria-[invalid=true]:border-destructive",
          className,
        )}
        {...props}
      />
    );
  },
);

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-24 w-full rounded-[10px] border border-hairline bg-white px-4 py-2.5 text-[0.92rem] text-ink",
        "focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none",
        "placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50",
        "aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    />
  );
});

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ className, children, ...props }, ref) {
  return (
    <select
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-[10px] border border-hairline bg-white px-4 py-2 text-[0.92rem] text-ink",
          "focus:border-brand-bright focus:shadow-[0_0_0_3px_rgba(37,100,40,0.12)] focus:outline-none",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
});

"use client";

import * as React from "react";
import { FileText, UploadCloud, X } from "lucide-react";

import { cn } from "@/lib/utils";

/** The API's default upload limit (MAX_UPLOAD_MB). */
export const DEFAULT_MAX_MB = 25;

interface FileDropzoneProps {
  id: string;
  /** Extensions the field takes, e.g. [".pdf", ".png"]; checked here and by the API. */
  accept: string[];
  value: File | null;
  onChange: (file: File | null) => void;
  /** Shown under the title, e.g. "PDF, PNG or JPG". */
  hint: string;
  maxMb?: number;
  disabled?: boolean;
  /** Ids of elements describing the field (e.g. its label). */
  describedBy?: string;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Why ``file`` cannot be uploaded to this field, or null when it can. */
export function fileProblem(file: File, accept: string[], maxMb: number): string | null {
  if (!accept.includes(extensionOf(file.name))) {
    return `"${file.name}" is not accepted. Choose a ${accept.join(", ")} file.`;
  }
  if (file.size > maxMb * 1024 * 1024) {
    return `"${file.name}" is ${formatBytes(file.size)}; files up to ${maxMb} MB are accepted.`;
  }
  return null;
}

/**
 * One-file upload: a drop area (click, keyboard or drag and drop) that turns into
 * a file card - name, size, Remove - once a file is chosen. Wrong types and files
 * over the size limit are refused here with a message, before anything is sent.
 */
export function FileDropzone({
  id,
  accept,
  value,
  onChange,
  hint,
  maxMb = DEFAULT_MAX_MB,
  disabled = false,
  describedBy,
}: FileDropzoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [problem, setProblem] = React.useState<string | null>(null);
  const problemId = `${id}-problem`;
  const hintId = `${id}-hint`;

  function choose(file: File | undefined) {
    if (!file) return;
    const issue = fileProblem(file, accept, maxMb);
    setProblem(issue);
    if (!issue) onChange(file);
  }

  function clear() {
    setProblem(null);
    onChange(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  const input = (
    <input
      ref={inputRef}
      id={id}
      type="file"
      accept={accept.join(",")}
      disabled={disabled}
      className="sr-only"
      aria-describedby={[describedBy, hintId, problem ? problemId : null].filter(Boolean).join(" ")}
      aria-invalid={problem ? true : undefined}
      onChange={(event) => choose(event.target.files?.[0])}
    />
  );

  return (
    <div className="flex flex-col gap-1.5">
      {value ? (
        <div className="flex items-center gap-3 rounded-xl border border-hairline bg-white px-4 py-3">
          {input}
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-700">
            <FileText className="h-5 w-5" aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink" title={value.name}>
              {value.name}
            </span>
            <span id={hintId} className="block text-xs text-subtle">
              {formatBytes(value.size)}
            </span>
          </span>
          <label
            htmlFor={id}
            className="cursor-pointer rounded-md px-2 py-1 text-sm font-medium text-nav-active hover:bg-surface-soft"
          >
            Replace
          </label>
          <button
            type="button"
            onClick={clear}
            disabled={disabled}
            aria-label={`Remove ${value.name}`}
            className="rounded-md p-1.5 text-subtle hover:bg-surface-soft hover:text-destructive"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      ) : (
        <label
          htmlFor={id}
          onDragOver={(event) => {
            event.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            if (!disabled) choose(event.dataTransfer.files?.[0]);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors",
            "focus-within:border-brand-bright focus-within:bg-brand-50",
            dragging ? "border-brand-bright bg-brand-50" : "border-hairline bg-surface-soft hover:border-brand-bright",
            problem && "border-destructive",
            disabled && "cursor-not-allowed opacity-60",
          )}
        >
          {input}
          <UploadCloud className="h-7 w-7 text-brand-bright" aria-hidden />
          <span className="text-sm text-ink">
            <span className="font-semibold text-nav-active">Click to upload</span> or drag and drop
          </span>
          <span id={hintId} className="text-xs text-subtle">
            {hint} · up to {maxMb} MB
          </span>
        </label>
      )}
      {problem ? (
        <p id={problemId} role="alert" className="text-xs text-destructive">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

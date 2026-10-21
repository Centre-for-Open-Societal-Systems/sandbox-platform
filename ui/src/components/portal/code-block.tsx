"use client";

import Image from "next/image";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import csharp from "react-syntax-highlighter/dist/esm/languages/prism/csharp";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import php from "react-syntax-highlighter/dist/esm/languages/prism/php";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import { dracula } from "react-syntax-highlighter/dist/esm/styles/prism";

import { cn } from "@/lib/utils";

// Only the grammars the portal shows, to keep the bundle small.
SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("csharp", csharp);
SyntaxHighlighter.registerLanguage("go", go);
SyntaxHighlighter.registerLanguage("java", java);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("php", php);
SyntaxHighlighter.registerLanguage("python", python);

/** Code-sample languages with their icons (as the reference sandbox's language picker). */
export const CODE_LANGUAGES = [
  { id: "curl", label: "cURL", icon: "/assets/languages/curl.webp", grammar: "bash" },
  { id: "python", label: "Python", icon: "/assets/languages/python.webp", grammar: "python" },
  { id: "javascript", label: "Node.js", icon: "/assets/languages/node.webp", grammar: "javascript" },
  { id: "java", label: "Java", icon: "/assets/languages/java.webp", grammar: "java" },
  { id: "go", label: "Go", icon: "/assets/languages/go.webp", grammar: "go" },
  { id: "php", label: "PHP", icon: "/assets/languages/php.webp", grammar: "php" },
  { id: "csharp", label: ".NET", icon: "/assets/languages/net.webp", grammar: "csharp" },
] as const;

/** Prism grammar for a code-sample language id (``curl`` → ``bash``). */
export function grammarFor(languageId: string): string {
  return CODE_LANGUAGES.find((item) => item.id === languageId)?.grammar ?? "bash";
}

/** Syntax-highlighted, read-only code (Dracula theme, like the reference sandbox). */
export function CodeBlock({
  code,
  language,
  className,
  wrap = false,
}: {
  code: string;
  language: string;
  className?: string;
  /** Wrap long lines (for commands) instead of scrolling sideways. */
  wrap?: boolean;
}) {
  return (
    <div className={cn("overflow-auto rounded-xl bg-[#282a36] text-xs", className)}>
      <SyntaxHighlighter
        language={language}
        style={dracula}
        wrapLongLines={wrap}
        customStyle={{ margin: 0, padding: "1rem", background: "transparent", fontSize: "0.75rem", lineHeight: 1.6 }}
        codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

/** Row of language tiles with icons; the chosen one is outlined in green. */
export function LanguagePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="scrollbar-none flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Code language">
      {CODE_LANGUAGES.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.id)}
            className={cn(
              "flex w-[72px] shrink-0 flex-col items-center gap-1.5 rounded-xl border-2 px-2 pt-2.5 pb-2 transition-colors",
              active
                ? "border-brand-bright bg-surface-soft shadow-sm"
                : "border-transparent bg-[#f1f8ea] hover:border-brand-200",
            )}
          >
            <span className="flex h-8 w-12 items-center justify-center">
              <Image src={item.icon} alt="" width={48} height={32} unoptimized className="h-auto max-h-8 w-auto max-w-12" />
            </span>
            <span className={cn("text-[0.72rem] font-semibold", active ? "text-nav-active" : "text-slate-600")}>
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

"use client";

import * as React from "react";
import { Lock, Mail } from "lucide-react";

import { cn, formatDateTime } from "@/lib/utils";
import type { SupportMessage } from "@/types/api";

/**
 * A ticket's conversation, oldest first, like a chat: the viewer's own messages on the
 * right, the other side on the left, status events centred, staff notes marked.
 */
export function TicketThread({
  messages,
  viewer,
  className,
}: {
  messages: SupportMessage[];
  viewer: "participant" | "admin";
  className?: string;
}) {
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages.length]);

  return (
    <ol className={cn("flex flex-col gap-3", className)} aria-label="Conversation">
      {messages.map((message) => (
        <Message key={message.message_id} message={message} viewer={viewer} />
      ))}
      <div ref={end} />
    </ol>
  );
}

function Message({ message, viewer }: { message: SupportMessage; viewer: "participant" | "admin" }) {
  if (message.author_type === "system") {
    return (
      <li className="text-center text-xs text-subtle">
        {message.body} · {formatDateTime(message.added_date)}
      </li>
    );
  }

  const mine = message.author_type === viewer;
  const staff = message.author_type === "admin";
  const who = mine
    ? "You"
    : staff
      ? `${message.author_name || "Support"} · OAN team`
      : message.author_name || "Participant";

  return (
    <li className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl border px-3.5 py-2.5 text-sm",
          message.is_internal
            ? "border-amber-300 bg-amber-50"
            : staff
              ? "border-brand-bright/20 bg-brand-50"
              : "border-hairline bg-white",
        )}
      >
        <p className="flex flex-wrap items-center gap-x-1.5 text-xs font-semibold text-slate-600">
          {message.is_internal ? <Lock className="h-3 w-3 text-amber-700" aria-hidden /> : null}
          <span>{who}</span>
          {message.is_internal ? <span className="text-amber-700">· Internal note (not shown to the user)</span> : null}
        </p>
        <p className="mt-1 break-words whitespace-pre-wrap text-ink">{message.body}</p>
        <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-subtle">
          {formatDateTime(message.added_date)}
          {message.channel === "email" ? (
            <span className="inline-flex items-center gap-0.5">
              <Mail className="h-3 w-3" aria-hidden /> by email
            </span>
          ) : null}
          {staff && !message.is_internal && message.notified_date ? (
            <span className="inline-flex items-center gap-0.5" title={`Emailed ${formatDateTime(message.notified_date)}`}>
              <Mail className="h-3 w-3" aria-hidden /> emailed
            </span>
          ) : null}
        </p>
      </div>
    </li>
  );
}

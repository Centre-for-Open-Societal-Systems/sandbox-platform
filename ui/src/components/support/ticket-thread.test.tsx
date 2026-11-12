import * as React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TicketThread } from "@/components/support/ticket-thread";
import type { SupportMessage } from "@/types/api";

function message(partial: Partial<SupportMessage> & Pick<SupportMessage, "message_id" | "author_type" | "body">): SupportMessage {
  return {
    author_name: null,
    is_internal: false,
    channel: "portal",
    notified_date: null,
    added_date: "2026-11-12T09:00:00Z",
    ...partial,
  };
}

const MESSAGES: SupportMessage[] = [
  message({ message_id: 1, author_type: "participant", author_name: "Abebe", body: "Token fails" }),
  message({ message_id: 2, author_type: "admin", author_name: "Sara", body: "Send the error", notified_date: "2026-11-12T09:05:00Z" }),
  message({ message_id: 3, author_type: "admin", author_name: "Sara", body: "Duplicate of the outage", is_internal: true }),
  message({ message_id: 4, author_type: "system", body: "Status changed to Closed." }),
];

afterEach(cleanup);

describe("TicketThread", () => {
  it("shows the participant their own messages as 'You' and the team as the OAN team", () => {
    render(<TicketThread messages={MESSAGES.slice(0, 2)} viewer="participant" />);

    expect(screen.getByText("You")).toBeTruthy();
    expect(screen.getByText("Sara · OAN team")).toBeTruthy();
    expect(screen.getByText("emailed")).toBeTruthy();
  });

  it("marks staff notes and shows the participant by name to the console", () => {
    render(<TicketThread messages={MESSAGES} viewer="admin" />);

    expect(screen.getByText("Abebe")).toBeTruthy();
    expect(screen.getByText(/Internal note/)).toBeTruthy();
    expect(screen.getByText(/Status changed to Closed\./)).toBeTruthy();
  });
});

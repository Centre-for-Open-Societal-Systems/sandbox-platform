import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { type LookupItem, type LookupPage, SearchableMultiSelect } from "@/components/ui/searchable-multi-select";

const PARTNERS: LookupItem[] = [
  { id: 1, label: "Abay Bank", hint: "abay@example.org" },
  { id: 2, label: "Coop Bank" },
];

beforeAll(() => {
  // jsdom has neither; the component uses them for paging and scrolling.
  class NoopObserver {
    observe() {}
    disconnect() {}
  }
  vi.stubGlobal("IntersectionObserver", NoopObserver);
  Element.prototype.scrollIntoView = () => {};
});

afterEach(cleanup);

function Harness({ initial = [], onChange }: { initial?: LookupItem[]; onChange?: (items: LookupItem[]) => void }) {
  const [client] = React.useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  const [value, setValue] = React.useState<LookupItem[]>(initial);
  const fetchPage = React.useCallback(
    async (search: string, page: number): Promise<LookupPage> => ({
      rows: PARTNERS.filter((item) => item.label.toLowerCase().includes(search.toLowerCase())),
      page,
      has_more: false,
    }),
    [],
  );
  return (
    <QueryClientProvider client={client}>
      <SearchableMultiSelect
        id="partners"
        queryKey={["partners"]}
        fetchPage={fetchPage}
        value={value}
        onChange={(items) => {
          setValue(items);
          onChange?.(items);
        }}
        placeholder="All partners"
        noun="partners"
        searchPlaceholder="Search partners"
      />
    </QueryClientProvider>
  );
}

function trigger() {
  return screen.getByRole("button", { name: /partners/i, expanded: false });
}

describe("SearchableMultiSelect", () => {
  it("puts the cursor in the search box when it opens", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("All partners"));

    const search = screen.getByRole("searchbox", { name: "Search partners" });
    await waitFor(() => expect(document.activeElement).toBe(search));
    expect(await screen.findByRole("option", { name: /Abay Bank/ })).toBeDefined();
  });

  it("opens with the arrow key and chooses with Enter", async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    const search = await screen.findByRole("searchbox", { name: "Search partners" });
    await screen.findByRole("option", { name: /Abay Bank/ });

    fireEvent.keyDown(search, { key: "ArrowDown" });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(onChange).toHaveBeenLastCalledWith([PARTNERS[0]]);
    expect(screen.getByRole("option", { name: /Abay Bank/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("closes with Escape from the search box", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("All partners"));
    const search = await screen.findByRole("searchbox", { name: "Search partners" });

    fireEvent.keyDown(search, { key: "Escape" });
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("removes one chosen item, or clears them all", async () => {
    const onChange = vi.fn();
    render(<Harness initial={PARTNERS} onChange={onChange} />);
    expect(screen.getByText("2 partners selected")).toBeDefined();

    fireEvent.click(screen.getByText("2 partners selected"));
    fireEvent.click(await screen.findByRole("button", { name: "Remove Abay Bank" }));
    expect(onChange).toHaveBeenLastCalledWith([PARTNERS[1]]);

    fireEvent.click(screen.getByRole("button", { name: "Clear selected partners" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("filters the options by the search text", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      render(<Harness />);
      fireEvent.click(screen.getByText("All partners"));
      fireEvent.change(screen.getByRole("searchbox", { name: "Search partners" }), { target: { value: "coop" } });
      await act(async () => {
        vi.advanceTimersByTime(400);
      });
      await waitFor(() => expect(screen.queryByRole("option", { name: /Abay Bank/ })).toBeNull());
      expect(screen.getByRole("option", { name: /Coop Bank/ })).toBeDefined();
    } finally {
      vi.useRealTimers();
    }
  });
});

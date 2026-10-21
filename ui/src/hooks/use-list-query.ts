"use client";

import * as React from "react";

import { DEFAULT_PAGE_SIZE } from "@/lib/config";
import type { ListQuery } from "@/types/api";

interface UseListQueryOptions {
  limit?: number;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  filters?: Record<string, unknown>;
}

/**
 * Shared grid state: paging, search, sort and filters.
 *
 * The search term is debounced into `query` so typing does not fire a request
 * per keystroke, while the input itself stays responsive.
 */
export function useListQuery(options: UseListQueryOptions = {}) {
  const [page, setPage] = React.useState(1);
  const [limit, setLimit] = React.useState(options.limit ?? DEFAULT_PAGE_SIZE);
  const [searchInput, setSearchInput] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [sortBy, setSortBy] = React.useState(options.sortBy);
  const [sortDir, setSortDir] = React.useState<"asc" | "desc">(options.sortDir ?? "desc");
  const [filters, setFilters] = React.useState<Record<string, unknown>>(options.filters ?? {});

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = React.useMemo<ListQuery>(
    () => ({ page, limit, search, sort_by: sortBy, sort_dir: sortDir, ...filters }),
    [page, limit, search, sortBy, sortDir, filters],
  );

  const handleSortChange = React.useCallback((field: string, direction: "asc" | "desc") => {
    setSortBy(field);
    setSortDir(direction);
    setPage(1);
  }, []);

  const handlePageSizeChange = React.useCallback((next: number) => {
    setLimit(next);
    setPage(1);
  }, []);

  const setFilter = React.useCallback((key: string, value: unknown) => {
    setFilters((current) => {
      const next = { ...current };
      if (value === undefined || value === null || value === "") {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
    setPage(1);
  }, []);

  const resetFilters = React.useCallback(() => {
    setFilters(options.filters ?? {});
    setSearchInput("");
    setPage(1);
  }, [options.filters]);

  return {
    query,
    filters,
    page,
    limit,
    sortBy,
    sortDir,
    searchInput,
    setSearchInput,
    setPage,
    setFilter,
    resetFilters,
    handleSortChange,
    handlePageSizeChange,
  };
}

"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Loader2 } from "lucide-react";

import { Pagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";
import type { Pagination as PaginationMeta } from "@/types/api";

export interface Column<T> {
  /** Stable key, also used as the sort field when `sortable` is set. */
  key: string;
  header: string;
  render: (row: T, index: number) => React.ReactNode;
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  pagination?: PaginationMeta;
  loading?: boolean;
  emptyMessage?: string;
  /** Plural noun for the pagination summary, e.g. "participants". */
  noun?: string;
  /** Prepend a "Sr. No." column that keeps counting across pages. */
  serial?: boolean;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  onSortChange?: (field: string, direction: "asc" | "desc") => void;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (limit: number) => void;
}

/**
 * Admin table in the registry-portal style: mint header, striped rows, no row
 * borders, pagination underneath.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  pagination,
  loading = false,
  emptyMessage = "Nothing to show yet.",
  noun,
  serial = true,
  sortBy,
  sortDir = "desc",
  onSortChange,
  onPageChange,
  onPageSizeChange,
}: DataTableProps<T>) {
  const offset = pagination ? (pagination.page - 1) * pagination.limit : 0;
  const allColumns: Column<T>[] = serial
    ? [
        {
          key: "__serial",
          header: "Sr. No.",
          className: "w-20",
          render: (_row, index) => `${offset + index + 1}.`,
        },
        ...columns,
      ]
    : columns;

  function handleSort(column: Column<T>) {
    if (!column.sortable || !onSortChange) {
      return;
    }
    const nextDirection = sortBy === column.key && sortDir === "desc" ? "asc" : "desc";
    onSortChange(column.key, nextDirection);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="table-scroll rounded-xl border border-table-head bg-white">
        <table className="w-full min-w-max text-left text-sm text-ink">
          <thead className="bg-table-head">
            <tr>
              {allColumns.map((column) => {
                const sorted = column.sortable && sortBy === column.key;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={sorted ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
                    className={cn(
                      "px-5 py-3 font-semibold whitespace-nowrap",
                      column.sortable && "cursor-pointer select-none",
                      column.className,
                    )}
                    onClick={() => handleSort(column)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {column.header}
                      {sorted ? (
                        sortDir === "desc" ? (
                          <ArrowDown className="h-3.5 w-3.5" aria-hidden />
                        ) : (
                          <ArrowUp className="h-3.5 w-3.5" aria-hidden />
                        )
                      ) : null}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={allColumns.length} className="px-5 py-10 text-center">
                  <span className="inline-flex items-center gap-2 text-subtle">
                    <Loader2 className="h-5 w-5 animate-spin text-brand-bright" aria-hidden />
                    Loading{noun ? ` ${noun}` : ""}…
                  </span>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={allColumns.length} className="px-5 py-10 text-center text-subtle">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={rowKey(row)} className="odd:bg-white even:bg-[#fafafa]">
                  {allColumns.map((column) => (
                    <td key={column.key} className={cn("px-5 py-3.5 align-middle", column.className)}>
                      {column.render(row, index)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pagination ? (
        <Pagination
          meta={pagination}
          noun={noun}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      ) : null}
    </div>
  );
}

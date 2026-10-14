"use client";

import * as React from "react";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Request/response fields as the reference sandbox's collapsible tree: a
 * dashed guide line with a dashed connector into each field, then
 * "name · type · Required". Objects and arrays of objects expand to show their
 * own fields. Stored path/header/query parameters use the same row style.
 */

type JsonSchema = {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  required?: string[];
  description?: string;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  enum?: unknown[];
  format?: string;
};

interface Node {
  path: string;
  name: string;
  type: string;
  required: boolean;
  description: string | null;
  children: Node[];
}

const MAX_DEPTH = 8;

function typeLabel(schema: JsonSchema): string {
  const variants = schema.anyOf ?? schema.oneOf;
  if (variants?.length) {
    return variants.map(typeLabel).filter((label) => label !== "null").join(" | ") || "any";
  }
  const base = Array.isArray(schema.type) ? schema.type.join(" | ") : (schema.type ?? (schema.properties ? "object" : "any"));
  if (base === "array" && schema.items) {
    return `array[${typeLabel(schema.items)}]`;
  }
  return schema.format ? `${base} (${schema.format})` : base;
}

/** The schema whose ``properties`` hold a field's children, if any. */
function objectOf(schema: JsonSchema): JsonSchema | null {
  const target = schema.type === "array" && schema.items ? schema.items : schema;
  return (
    [target, ...(target.anyOf ?? []), ...(target.oneOf ?? [])].find((item) => item.properties) ?? null
  );
}

function buildNodes(schema: JsonSchema, parent = "", depth = 0): Node[] {
  const object = objectOf(schema);
  if (!object?.properties || depth > MAX_DEPTH) {
    return [];
  }
  const required = new Set(object.required ?? []);
  return Object.entries(object.properties).map(([name, child]) => {
    const path = parent ? `${parent}.${name}` : name;
    return {
      path,
      name,
      type: typeLabel(child),
      required: required.has(name),
      description: child.description ?? (child.enum ? `One of: ${child.enum.join(", ")}` : null),
      children: buildNodes(child, path, depth + 1),
    };
  });
}

function collectPaths(nodes: Node[], into: string[] = []): string[] {
  for (const node of nodes) {
    if (node.children.length) {
      into.push(node.path);
      collectPaths(node.children, into);
    }
  }
  return into;
}

export function SchemaFields({ schema, empty = "No fields documented." }: { schema: unknown; empty?: string }) {
  const nodes = React.useMemo(
    () => (schema && typeof schema === "object" ? buildNodes(schema as JsonSchema) : []),
    [schema],
  );
  const expandable = React.useMemo(() => collectPaths(nodes), [nodes]);
  // Top-level objects start open so the shape is visible at a glance.
  const [open, setOpen] = React.useState<Set<string>>(
    () => new Set(nodes.filter((node) => node.children.length).map((node) => node.path)),
  );

  if (nodes.length === 0) {
    return <p className="rounded-lg border border-[#e6e6e6] bg-[#f8f8f8] px-4 py-3 text-sm text-subtle">{empty}</p>;
  }

  const allOpen = expandable.every((path) => open.has(path));

  function toggle(path: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  return (
    <div className="rounded-lg border border-[#e6e6e6] bg-[#f8f8f8] px-3 py-3">
      {expandable.length > 0 ? (
        <div className="mb-1 flex justify-end">
          <button
            type="button"
            onClick={() => setOpen(allOpen ? new Set() : new Set(expandable))}
            className="text-xs font-semibold text-brand-bright hover:underline"
          >
            {allOpen ? "Collapse all" : "Expand all"}
          </button>
        </div>
      ) : null}
      <Tree nodes={nodes} open={open} onToggle={toggle} />
    </div>
  );
}

function Tree({ nodes, open, onToggle }: { nodes: Node[]; open: Set<string>; onToggle: (path: string) => void }) {
  return (
    <ul className="ml-3 border-l border-dashed border-slate-400">
      {nodes.map((node) => {
        const expandable = node.children.length > 0;
        const expanded = expandable && open.has(node.path);
        return (
          <li key={node.path} className="relative py-1.5">
            {/* dashed connector from the guide line into the row */}
            <span aria-hidden className="absolute top-[1.2rem] left-0 w-4 border-t border-dashed border-slate-400" />
            <div className="ml-5">
              <FieldRow
                name={node.name}
                type={node.type}
                required={node.required}
                description={node.description}
                expandable={expandable}
                expanded={expanded}
                onToggle={() => onToggle(node.path)}
              />
              {expanded ? (
                <div className="mt-1">
                  <Tree nodes={node.children} open={open} onToggle={onToggle} />
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function FieldRow({
  name,
  type,
  required,
  description,
  expandable = false,
  expanded = false,
  onToggle,
}: {
  name: string;
  type: string;
  required: boolean;
  description: string | null;
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const label = (
    <>
      {expandable ? (
        <ChevronRight
          className={cn("h-3.5 w-3.5 shrink-0 text-brand-bright transition-transform", expanded && "rotate-90")}
          aria-hidden
        />
      ) : null}
      <span className="font-mono text-[0.82rem] font-semibold break-all text-ink">{name}</span>
    </>
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-0.5 rounded-md py-0.5">
        {expandable ? (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="-ml-1 flex items-center gap-1 rounded px-1 hover:bg-white"
          >
            {label}
          </button>
        ) : (
          <span className="flex items-center gap-1">{label}</span>
        )}
        <span className="font-mono text-xs text-slate-500 italic">{type}</span>
        {required ? <span className="text-xs font-semibold text-[#4f9d12]">Required</span> : null}
      </div>
      {description ? <p className="mt-0.5 max-w-prose text-xs leading-relaxed text-subtle">{description}</p> : null}
    </div>
  );
}

/** Stored parameters look like ``{name: {required, schema: {type}, description, value}}``. */
export function ParamFields({ params }: { params: Record<string, unknown> | null | undefined }) {
  const rows = Object.entries(params ?? {}).map(([name, spec]) => {
    const value = (spec && typeof spec === "object" ? spec : {}) as {
      required?: boolean;
      is_required?: boolean;
      type?: string;
      schema?: JsonSchema;
      description?: string;
    };
    return {
      name,
      type: value.type ?? (value.schema ? typeLabel(value.schema) : "string"),
      required: Boolean(value.required ?? value.is_required),
      description: value.description ?? null,
    };
  });
  if (rows.length === 0) {
    return null;
  }
  return (
    <div className="rounded-lg border border-[#e6e6e6] bg-[#f8f8f8] px-3 py-3">
      <ul className="ml-3 border-l border-dashed border-slate-400">
        {rows.map((row) => (
          <li key={row.name} className="relative py-1.5">
            <span aria-hidden className="absolute top-[1.2rem] left-0 w-4 border-t border-dashed border-slate-400" />
            <div className="ml-5">
              <FieldRow name={row.name} type={row.type} required={row.required} description={row.description} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

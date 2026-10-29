"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { Fragment, useMemo } from "react";

import type { BOQLine } from "@/lib/types";
import { fmtInrDec, fmtQty } from "@/lib/inr";
import { cn } from "@/lib/cn";

type EditField = "qty" | "rate";

export function BOQGrid({
  lines,
  onEdit,
  onInspect,
}: {
  lines: BOQLine[];
  onEdit: (line: BOQLine, field: EditField) => void;
  onInspect: (line: BOQLine) => void;
}) {
  const columns = useMemo(() => buildColumns(onEdit, onInspect), [onEdit, onInspect]);
  const table = useReactTable({
    data: lines,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  // Compute per-element subtotals once, keyed on element.
  const subtotals = useMemo(() => {
    const m: Record<string, number> = {};
    for (const ln of lines) m[ln.element] = (m[ln.element] ?? 0) + (ln.amount ?? 0);
    return m;
  }, [lines]);

  const rows = table.getRowModel().rows;

  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
      <table className="min-w-full text-sm">
        <thead className="bg-zinc-50 dark:bg-zinc-800">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className={cn(
                    "px-3 py-2 font-medium text-zinc-500 text-left",
                    (h.column.columnDef.meta as { align?: string } | undefined)?.align === "right" && "text-right",
                  )}
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>

        <tbody>
          {rows.map((row, i) => {
            const prev = i === 0 ? null : rows[i - 1].original;
            const line = row.original;
            const groupBreak = prev === null || prev.element !== line.element;
            return (
              <Fragment key={row.id}>
                {groupBreak && (
                  <tr className="bg-zinc-100/60 dark:bg-zinc-800/60">
                    <td
                      colSpan={columns.length}
                      className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-600 dark:text-zinc-300"
                    >
                      {line.element.replace(/_/g, " ")}
                    </td>
                  </tr>
                )}
                <tr
                  className={cn(
                    "border-t border-zinc-100 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40",
                    line.is_overridden && "bg-amber-50/50 dark:bg-amber-950/30",
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={cn(
                        "px-3 py-1.5 align-top",
                        (cell.column.columnDef.meta as { align?: string } | undefined)?.align === "right" && "text-right",
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
                {/* Subtotal row — only after the last line of each element block */}
                {(i === rows.length - 1 || rows[i + 1].original.element !== line.element) && (
                  <tr className="bg-zinc-50 dark:bg-zinc-900/60">
                    <td
                      colSpan={columns.length - 1}
                      className="px-3 py-1.5 text-right text-xs font-medium uppercase text-zinc-500"
                    >
                      subtotal — {line.element.replace(/_/g, " ")}
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold">
                      {fmtInrDec(subtotals[line.element] ?? 0)}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ----------------------------------------------------------- column helper */

const col = createColumnHelper<BOQLine>();

function buildColumns(onEdit: (ln: BOQLine, f: EditField) => void, onInspect: (ln: BOQLine) => void) {
  return [
    col.accessor("seq", {
      header: "Seq",
      cell: (ctx) => <span className="font-mono text-xs text-zinc-500">{ctx.getValue()}</span>,
    }),
    col.accessor("description", {
      header: "Description",
      cell: (ctx) => {
        const ln = ctx.row.original;
        return (
          <div className="max-w-md">
            <div className="text-zinc-900 dark:text-zinc-100">{ctx.getValue()}</div>
            {ln.is_overridden && (
              <span className="mt-0.5 inline-block rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900">
                Overridden
              </span>
            )}
          </div>
        );
      },
    }),
    col.accessor("unit", {
      header: "Unit",
      cell: (ctx) => <span className="text-zinc-500">{ctx.getValue()}</span>,
    }),
    col.accessor("qty", {
      header: "Qty",
      meta: { align: "right" },
      cell: (ctx) => (
        <EditableCell
          label={fmtQty(ctx.getValue())}
          onEdit={() => onEdit(ctx.row.original, "qty")}
        />
      ),
    }),
    col.accessor("rate", {
      header: "Rate (INR)",
      meta: { align: "right" },
      cell: (ctx) => {
        const v = ctx.getValue();
        return (
          <EditableCell
            label={v != null ? fmtInrDec(v) : "—"}
            onEdit={() => onEdit(ctx.row.original, "rate")}
          />
        );
      },
    }),
    col.accessor("amount", {
      header: "Amount (INR)",
      meta: { align: "right" },
      cell: (ctx) => {
        const v = ctx.getValue();
        return (
          <span className="font-medium">{v != null ? fmtInrDec(v) : "—"}</span>
        );
      },
    }),
    col.display({
      id: "trace",
      header: "",
      meta: { align: "right" },
      cell: (ctx) => (
        <button
          type="button"
          onClick={() => onInspect(ctx.row.original)}
          className="text-xs font-medium text-blue-600 hover:underline"
          aria-label={`Show formula trace for ${ctx.row.original.description}`}
        >
          Trace
        </button>
      ),
    }),
  ];
}

function EditableCell({ label, onEdit }: { label: string; onEdit: () => void }) {
  return (
    <button
      type="button"
      onClick={onEdit}
      className="w-full rounded px-1 py-0.5 text-right transition-colors hover:bg-blue-50 focus-visible:bg-blue-50 focus-visible:outline-none dark:hover:bg-blue-950 dark:focus-visible:bg-blue-950"
      title="Click to override"
    >
      {label}
    </button>
  );
}

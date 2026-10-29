"use client";

import { cn } from "@/lib/cn";
import { fmtInr, fmtInrCompact, fmtInrDec, fmtPct } from "@/lib/inr";
import type { Estimate } from "@/lib/types";

export function TotalsBar({
  estimate,
  builtupM2,
  overriddenCount,
}: {
  estimate: Estimate | null;
  builtupM2: number | null;
  overriddenCount: number;
}) {
  const total = estimate?.total_cost ?? 0;
  const costPerM2 =
    builtupM2 && builtupM2 > 0 ? total / builtupM2 : null;
  const totalsByElement: Record<string, number> =
    (estimate?.totals_by_element as Record<string, number> | null) ?? {};
  const subtotal: number = Object.values(totalsByElement).reduce(
    (s, v) => s + v,
    0,
  );

  // ~12% markup assumption on raw subtotal for the preliminary badge band.
  return (
    <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-zinc-200 p-5 dark:border-zinc-800">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            Total (preliminary, AACE Class 4/5)
          </div>
          <div className="mt-1 flex items-end gap-3">
            <div className="text-3xl font-semibold">{fmtInrCompact(total)}</div>
            <div className="pb-1 text-sm text-zinc-500">
              ({fmtInr(total)})
            </div>
          </div>
          {costPerM2 && (
            <div className="mt-1 text-sm">
              <span className="rounded-md bg-zinc-100 px-2 py-0.5 font-medium text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                {fmtInrDec(costPerM2)} / m²
              </span>
              <span className="ml-2 text-zinc-500">
                on {builtupM2!.toLocaleString("en-IN")} m² built-up
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-6">
          <Stat label="Subtotal" value={fmtInr(subtotal)} />
          <Stat label="Markup" value={fmtInr(Math.max(total - subtotal, 0))} />
          {overriddenCount > 0 && (
            <Stat
              label="Overrides"
              value={`${overriddenCount}`}
              highlight="amber"
            />
          )}
        </div>
      </div>

      {/* Element share bars */}
      {total > 0 && (
        <div className="divide-y divide-zinc-100 px-5 py-3 dark:divide-zinc-800">
          {Object.entries(totalsByElement)
            .sort((a, b) => b[1] - a[1])
            .map(([el, amt]) => {
              const pct = (amt / total) * 100;
              return (
                <div key={el} className="flex items-center gap-3 py-1.5 text-sm">
                  <div className="w-32 shrink-0 capitalize text-zinc-600 dark:text-zinc-300">
                    {el.replace(/_/g, " ")}
                  </div>
                  <div className="h-2 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-blue-600"
                      style={{ width: `${pct.toFixed(1)}%` }}
                    />
                  </div>
                  <div className="w-28 shrink-0 text-right text-xs text-zinc-500">
                    {fmtInrCompact(amt)}{" "}
                    <span className="ml-1 text-zinc-400">({fmtPct(pct)})</span>
                  </div>
                </div>
              );
            })}
        </div>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: "amber";
}) {
  return (
    <div className="text-right">
      <div
        className={cn(
          "text-xs uppercase tracking-wide",
          highlight === "amber" ? "text-amber-700 dark:text-amber-400" : "text-zinc-500",
        )}
      >
        {label}
      </div>
      <div className={cn("text-sm font-medium", highlight === "amber" && "text-amber-700 dark:text-amber-300")}>
        {value}
      </div>
    </div>
  );
}

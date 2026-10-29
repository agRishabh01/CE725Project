"use client";

import { Overlay } from "@/components/overlay";
import { Button } from "@/components/ui/button";
import type { BOQLine } from "@/lib/types";
import { fmtInr, fmtQty } from "@/lib/inr";

export function TraceDrawer({
  line,
  onClose,
}: {
  line: BOQLine | null;
  onClose: () => void;
}) {
  const open = line !== null;
  return (
    <Overlay open={open} onClose={onClose}>
      <aside
        className="fixed inset-y-0 right-0 w-full max-w-md bg-white shadow-xl overflow-y-auto dark:bg-zinc-900"
        role="dialog"
        aria-label="Formula trace"
      >
        <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-5 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Why this quantity?</h2>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
              ✕
            </Button>
          </div>
          {line && (
            <p className="mt-1 text-xs text-zinc-500 capitalize">
              {line.element.replace(/_/g, " ")} · seq {line.seq}
            </p>
          )}
        </header>

        {line && (
          <div className="space-y-5 p-5 text-sm">
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500">
                Description
              </div>
              <p className="mt-1">{line.description}</p>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <Stat label="Qty" value={`${fmtQty(line.qty)} ${line.unit}`} />
              <Stat
                label="Rate"
                value={line.rate != null ? `${fmtInr(line.rate)} / ${line.unit}` : "—"}
              />
              <Stat
                label="Amount"
                value={line.amount != null ? fmtInr(line.amount) : "—"}
              />
            </div>

            {line.formula_trace ? (
              <div className="space-y-3 rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">
                    Rule
                  </div>
                  <code className="mt-1 inline-block rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
                    {line.formula_trace.rule_id} v{line.formula_trace.version}
                  </code>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">
                    Formula
                  </div>
                  <pre className="mt-1 overflow-x-auto rounded bg-zinc-100 p-2 text-xs text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
                    {line.formula_trace.formula}
                  </pre>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">
                    Inputs
                  </div>
                  <dl className="mt-1 divide-y divide-zinc-200 rounded border border-zinc-200 text-xs dark:divide-zinc-800 dark:border-zinc-800">
                    {Object.entries(line.formula_trace.inputs).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-2 px-3 py-1.5">
                        <dt className="text-zinc-500">{k}</dt>
                        <dd className="text-right font-mono">{String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                {line.formula_trace.source && (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                      Source
                    </div>
                    <p className="mt-1 text-xs text-zinc-500">
                      {line.formula_trace.source}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-zinc-500 italic">
                No formula trace recorded for this line.
              </p>
            )}

            {line.is_overridden && (
              <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
                <div className="font-medium text-amber-900 dark:text-amber-100">
                  Overridden
                </div>
                {line.override_reason && (
                  <p className="mt-1 text-amber-900 dark:text-amber-200">
                    “{line.override_reason}”
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </aside>
    </Overlay>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-0.5 font-medium">{value}</div>
    </div>
  );
}

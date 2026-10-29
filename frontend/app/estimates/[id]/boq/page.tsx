"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, use } from "react";
import { useSearchParams } from "next/navigation";

import { BOQGrid } from "@/components/boq-grid";
import { OverrideModal } from "@/components/override-modal";
import { RunProgress } from "@/components/run-progress";
import { useToast } from "@/components/toast";
import { TotalsBar } from "@/components/totals-bar";
import { TraceDrawer } from "@/components/trace-drawer";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { BOQLine, Estimate } from "@/lib/types";

type EditTarget = { line: BOQLine; field: "qty" | "rate" };

export default function BOQPage({ params }: PageProps<"/estimates/[id]/boq">) {
  const { id } = use(params);
  const sp = useSearchParams();
  const autostart = sp.get("autorun") === "1";

  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [lines, setLines] = useState<BOQLine[]>([]);
  const [builtup, setBuiltup] = useState<number | null>(null);
  const [queueCount, setQueueCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  const [inspecting, setInspecting] = useState<BOQLine | null>(null);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [e, l] = await Promise.all([api.getEstimate(id), api.listBOQ(id)]);
        if (cancelled) return;
        setEstimate(e);
        setLines(l);
        try {
          const p = await api.getEstimateParams(id);
          if (!cancelled && p.inputs.builtup_area_m2) {
            setBuiltup(p.inputs.builtup_area_m2 as number);
          }
        } catch {
          /* ok — happens on fresh estimates */
        }
        try {
          const q = await api.listMappingQueue(id);
          if (!cancelled) setQueueCount(q.length);
        } catch {
          /* ok */
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, refreshTick]);

  const onEdit = useCallback((line: BOQLine, field: "qty" | "rate") => {
    setEditing({ line, field });
  }, []);
  const onInspect = useCallback((line: BOQLine) => setInspecting(line), []);

  const onApplied = useCallback((updated: BOQLine) => {
    setLines((prev) => prev.map((ln) => (ln.id === updated.id ? updated : ln)));
    // Totals changed in the backend — refresh the estimate alone.
    api.getEstimate(id).then(setEstimate).catch(() => undefined);
    toast.success(
      "Line overridden",
      `${updated.description.slice(0, 60)}${updated.description.length > 60 ? "…" : ""}`,
    );
  }, [id, toast]);

  const overriddenCount = lines.filter((ln) => ln.is_overridden).length;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10">
      <header className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Estimate</h1>
          <p className="mt-1 font-mono text-xs text-zinc-500">{id}</p>
        </div>
        <div className="flex items-center gap-2">
          {queueCount > 0 && (
            <Link
              href={`/estimates/${id}/mapping`}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 text-sm font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200 dark:hover:bg-amber-900"
            >
              Review {queueCount} mapping{queueCount === 1 ? "" : "s"}
            </Link>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRefreshTick((t) => t + 1)}
          >
            Refresh
          </Button>
          <Link
            href={`/estimates/${id}/summary`}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-zinc-300 bg-white px-3 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Summary
          </Link>
          <a
            href={api.exportUrl(id, "xlsx")}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 items-center gap-2 rounded-md bg-zinc-100 px-3 text-sm font-medium text-zinc-900 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-700"
          >
            Export .xlsx
          </a>
        </div>
      </header>

      <RunProgress
        estimateId={id}
        autostart={autostart}
        onComplete={() => setRefreshTick((t) => t + 1)}
      />

      <TotalsBar
        estimate={estimate}
        builtupM2={builtup}
        overriddenCount={overriddenCount}
      />

      <Card>
        <h2 className="mb-4 text-lg font-semibold">BOQ lines</h2>
        {loading ? (
          <div className="space-y-3" aria-busy="true" aria-live="polite">
            <Skeleton className="h-5 w-1/3" />
            <SkeletonText lines={6} />
          </div>
        ) : lines.length === 0 ? (
          <div className="rounded-md border border-dashed border-zinc-300 p-8 text-center">
            <p className="text-sm text-zinc-500">
              No BOQ lines yet. Start a run to compute quantities.
            </p>
            {!autostart && (
              <a
                href="?autorun=1"
                className="mt-3 inline-block text-sm font-medium text-blue-600 underline"
              >
                Run now
              </a>
            )}
          </div>
        ) : (
          <BOQGrid lines={lines} onEdit={onEdit} onInspect={onInspect} />
        )}
      </Card>

      <TraceDrawer line={inspecting} onClose={() => setInspecting(null)} />

      <OverrideModal
        estimateId={id}
        line={editing?.line ?? null}
        focusField={editing?.field ?? "qty"}
        onClose={() => setEditing(null)}
        onApplied={onApplied}
      />
    </div>
  );
}

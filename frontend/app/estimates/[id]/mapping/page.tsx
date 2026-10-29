"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, use } from "react";

import { useToast } from "@/components/toast";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton, SkeletonText } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtInrDec, fmtQty } from "@/lib/inr";
import type { MappingProposal } from "@/lib/types";
import { cn } from "@/lib/cn";

export default function MappingPage({ params }: PageProps<"/estimates/[id]/mapping">) {
  const { id } = use(params);
  const toast = useToast();
  const [queue, setQueue] = useState<MappingProposal[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const q = await api.listMappingQueue(id);
      setQueue(q);
      setIdx((prev) => Math.min(prev, Math.max(q.length - 1, 0)));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const current = queue[idx] ?? null;

  const accept = useCallback(
    async (candidateIndex: number) => {
      if (!current) return;
      const cand = current.top_candidates[candidateIndex];
      if (!cand) return;
      setActing(true);
      setError(null);
      try {
        await api.acceptMapping(id, current.id, cand.rate_item_id);
        setQueue((prev) => prev.filter((p) => p.id !== current.id));
        setIdx((prev) => Math.min(prev, Math.max(queue.length - 2, 0)));
        toast.success("Accepted", `${cand.item_no} applied to the BOQ line`);
      } catch (e) {
        const msg = (e as Error).message;
        setError(msg);
        toast.error("Couldn’t accept match", msg);
      } finally {
        setActing(false);
      }
    },
    [current, id, queue.length, toast],
  );

  const skip = useCallback(async () => {
    if (!current) return;
    setActing(true);
    setError(null);
    try {
      await api.skipMapping(id, current.id);
      setQueue((prev) => prev.filter((p) => p.id !== current.id));
      setIdx((prev) => Math.min(prev, Math.max(queue.length - 2, 0)));
      toast.push({ tone: "info", title: "Skipped", message: "Line left with its engine rate" });
    } catch (e) {
      const msg = (e as Error).message;
      setError(msg);
      toast.error("Couldn’t skip", msg);
    } finally {
      setActing(false);
    }
  }, [current, id, queue.length, toast]);

  // Keyboard shortcuts: 1/2/3 accept Nth candidate, S skip, J/K navigate.
  const actingRef = useRef(acting);
  actingRef.current = acting;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (actingRef.current) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)
        return;
      if (e.key === "1" || e.key === "2" || e.key === "3") {
        e.preventDefault();
        accept(Number(e.key) - 1);
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        skip();
      } else if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setIdx((i) => Math.min(i + 1, queue.length - 1));
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setIdx((i) => Math.max(i - 1, 0));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [accept, skip, queue.length]);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Rate mapping review</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Confirm the DSR item for each low-confidence BOQ line. Keyboard:
            <kbd className="mx-1 rounded border border-zinc-300 bg-white px-1 text-xs">1</kbd>
            <kbd className="mx-0.5 rounded border border-zinc-300 bg-white px-1 text-xs">2</kbd>
            <kbd className="mx-1 rounded border border-zinc-300 bg-white px-1 text-xs">3</kbd>
            to accept, <kbd className="mx-1 rounded border border-zinc-300 bg-white px-1 text-xs">S</kbd> skip,
            <kbd className="mx-1 rounded border border-zinc-300 bg-white px-1 text-xs">J/K</kbd> navigate.
          </p>
        </div>
        <Link href={`/estimates/${id}/boq`}>
          <Button variant="secondary">Back to BOQ</Button>
        </Link>
      </header>

      <QueueStatus loading={loading} total={queue.length} idx={idx} error={error} />

      {loading ? (
        <Card>
          <Skeleton className="h-5 w-2/3" />
          <SkeletonText lines={4} className="mt-4" />
        </Card>
      ) : current ? (
        <Card>
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500">
                BOQ line {idx + 1} of {queue.length}
              </div>
              <h2 className="mt-0.5 text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {current.boq_description}
              </h2>
              <div className="mt-1 text-xs text-zinc-500">
                {current.boq_element.replace(/_/g, " ")} · {fmtQty(current.boq_qty)} {current.boq_unit}
              </div>
            </div>
            <ConfidencePill confidence={current.confidence} strategy={current.strategy} />
          </div>

          {current.reason && (
            <p className="mb-4 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-300">
              <span className="font-medium">Why so uncertain:</span> {current.reason}
            </p>
          )}

          <ol className="space-y-2">
            {current.top_candidates.map((c, i) => (
              <li key={c.rate_item_id}>
                <button
                  type="button"
                  onClick={() => accept(i)}
                  disabled={acting}
                  className={cn(
                    "block w-full rounded-md border p-3 text-left transition-colors",
                    "border-zinc-200 hover:border-blue-400 hover:bg-blue-50 dark:border-zinc-800 dark:hover:bg-blue-950",
                    acting && "cursor-not-allowed opacity-50",
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <kbd className="flex h-6 w-6 items-center justify-center rounded border border-zinc-300 bg-white text-xs font-semibold text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                        {i + 1}
                      </kbd>
                      <code className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs font-mono text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100">
                        {c.item_no}
                      </code>
                      <span className="text-xs text-zinc-500">{c.chapter}</span>
                    </div>
                    <div className="text-right text-xs text-zinc-500">
                      score {c.score.toFixed(2)}
                    </div>
                  </div>
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{c.description}</p>
                  <div className="mt-1 text-xs">
                    <span className="font-medium">{fmtInrDec(c.rate)}</span>
                    <span className="text-zinc-500"> / {c.unit}</span>
                  </div>
                </button>
              </li>
            ))}
          </ol>

          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" onClick={skip} disabled={acting}>
              Skip ({queue.length - 1} to go)
            </Button>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIdx((i) => Math.max(i - 1, 0))}
                disabled={idx === 0}
              >
                ← Prev
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIdx((i) => Math.min(i + 1, queue.length - 1))}
                disabled={idx === queue.length - 1}
              >
                Next →
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <Card>
          <h2 className="text-lg font-semibold">Queue empty</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Every low-confidence match has been resolved. You can return to the BOQ.
          </p>
          <div className="mt-4">
            <Link href={`/estimates/${id}/boq`}>
              <Button>Back to BOQ</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function QueueStatus({
  loading,
  total,
  idx,
  error,
}: {
  loading: boolean;
  total: number;
  idx: number;
  error: string | null;
}) {
  const resolved = total === 0 ? 0 : idx;
  const pct = total === 0 ? 100 : Math.min((resolved / Math.max(resolved + total, 1)) * 100, 100);
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between text-sm">
        <div>
          {loading ? "Loading queue…" : total === 0 ? "Nothing to review." : `${total} pending`}
        </div>
        <div className="text-xs text-zinc-500">{Math.round(pct)}% through this batch</div>
      </div>
      <div className="mt-2 h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div
          className="h-full rounded-full bg-emerald-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {error && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-900">
          {error}
        </div>
      )}
    </section>
  );
}

function ConfidencePill({ confidence, strategy }: { confidence: number; strategy: string }) {
  const pct = Math.round(confidence * 100);
  const colour =
    pct >= 60
      ? "bg-amber-100 text-amber-900"
      : "bg-red-100 text-red-900";
  return (
    <div className="text-right">
      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colour}`}>
        {pct}% confidence
      </span>
      <div className="mt-1 text-[10px] uppercase tracking-wide text-zinc-500">
        via {strategy}
      </div>
    </div>
  );
}

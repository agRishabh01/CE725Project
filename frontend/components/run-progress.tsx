"use client";

import { useEffect, useRef, useState } from "react";

import { api, streamRunEvents } from "@/lib/api";
import type { RunEvent } from "@/lib/types";

type Phase = "idle" | "starting" | "streaming" | "done" | "error";

export function RunProgress({
  estimateId,
  autostart,
  onComplete,
}: {
  estimateId: string;
  autostart: boolean;
  onComplete?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!autostart || started.current) return;
    started.current = true;

    const ac = new AbortController();
    (async () => {
      try {
        setPhase("starting");
        const run = await api.startRun(estimateId);
        setPhase("streaming");
        for await (const ev of streamRunEvents(run.run_id, ac.signal)) {
          setEvents((prev) => [...prev, ev]);
          if (ev.step === "stream_end") break;
        }
        setPhase("done");
        onComplete?.();
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError((e as Error).message);
        setPhase("error");
      }
    })();

    return () => ac.abort();
  }, [autostart, estimateId, onComplete]);

  if (phase === "idle" && !autostart) return null;

  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">Agent run</h2>
        <StatusPill phase={phase} />
      </header>
      <ol className="space-y-1.5">
        {events.map((ev, i) => (
          <EventRow key={i} ev={ev} />
        ))}
        {phase === "starting" && (
          <li className="text-sm text-zinc-500">Starting run…</li>
        )}
      </ol>
      {error && (
        <p className="mt-3 text-sm text-red-600">Error: {error}</p>
      )}
    </section>
  );
}

function EventRow({ ev }: { ev: RunEvent }) {
  const icon =
    ev.status === "completed" ? "✓" : ev.status === "failed" ? "✗" : "·";
  const colour =
    ev.status === "completed"
      ? "text-emerald-600"
      : ev.status === "failed"
        ? "text-red-600"
        : "text-blue-600";
  return (
    <li className="flex items-start gap-3 text-sm">
      <span className={`${colour} mt-0.5 font-mono`}>{icon}</span>
      <div className="flex-1">
        <span className="font-medium capitalize">{ev.step.replace(/_/g, " ")}</span>
        {ev.message && <span className="text-zinc-500"> — {ev.message}</span>}
        {ev.data && Object.keys(ev.data).length > 0 && (
          <pre className="mt-1 overflow-x-auto rounded bg-zinc-50 p-2 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            {JSON.stringify(ev.data, null, 2)}
          </pre>
        )}
      </div>
    </li>
  );
}

function StatusPill({ phase }: { phase: Phase }) {
  const label =
    phase === "idle"
      ? "idle"
      : phase === "starting"
        ? "starting"
        : phase === "streaming"
          ? "running"
          : phase === "done"
            ? "done"
            : "error";
  const colour =
    phase === "done"
      ? "bg-emerald-100 text-emerald-900"
      : phase === "error"
        ? "bg-red-100 text-red-900"
        : "bg-blue-100 text-blue-900";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colour}`}>
      {label}
    </span>
  );
}

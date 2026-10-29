"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ProjectCard } from "@/components/project-card";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtInrCompact } from "@/lib/inr";
import type { ProjectSummary } from "@/lib/types";

export default function Home() {
  const [summaries, setSummaries] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjectSummaries()
      .then(setSummaries)
      .catch((e) => setError((e as Error).message));
  }, []);

  const totals = computeTotals(summaries);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-10">
      <section className="flex items-end justify-between gap-6">
        <div>
          <h1 className="text-3xl font-semibold">Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Preliminary BOQ + element-wise cost estimates in under five minutes.
          </p>
        </div>
        <Link href="/estimates/new" aria-label="Create a new estimate">
          <Button>+ New estimate</Button>
        </Link>
      </section>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100"
        >
          Couldn’t reach the API: {error}
          <div className="mt-1 text-xs">
            Is <code>uvicorn api.main:app</code> running on{" "}
            <code>{process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000"}</code>?
          </div>
        </div>
      )}

      {totals && (
        <section
          className="grid grid-cols-2 gap-3 sm:grid-cols-4"
          aria-label="Portfolio summary"
        >
          <Stat label="Projects" value={String(totals.projects)} />
          <Stat label="Estimates" value={String(totals.estimates)} />
          <Stat
            label="Portfolio total"
            value={totals.portfolioTotal > 0 ? fmtInrCompact(totals.portfolioTotal) : "—"}
          />
          <Stat
            label="Median cost / m²"
            value={totals.medianCostPerM2 ? `₹${totals.medianCostPerM2.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}
          />
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">Recent projects</h2>
        {summaries === null && !error && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        )}
        {summaries && summaries.length === 0 && (
          <Card>
            <CardTitle>No projects yet</CardTitle>
            <CardDescription>
              Start a new estimate — the wizard takes a minute, and the engine
              computes a priced BOQ you can edit.
            </CardDescription>
            <div className="mt-4">
              <Link href="/estimates/new">
                <Button>Create your first estimate</Button>
              </Link>
            </div>
          </Card>
        )}
        {summaries && summaries.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {summaries.map((s) => (
              <ProjectCard key={s.id} project={s} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function computeTotals(summaries: ProjectSummary[] | null) {
  if (!summaries) return null;
  const estimates = summaries.reduce((n, s) => n + s.estimate_count, 0);
  const portfolioTotal = summaries.reduce(
    (sum, s) => sum + (s.latest_total_inr ?? 0),
    0,
  );
  const perM2 = summaries
    .map((s) => s.latest_cost_per_m2)
    .filter((x): x is number => x != null)
    .sort((a, b) => a - b);
  const medianCostPerM2 =
    perM2.length === 0
      ? null
      : perM2.length % 2 === 0
        ? (perM2[perM2.length / 2 - 1] + perM2[perM2.length / 2]) / 2
        : perM2[(perM2.length - 1) / 2];
  return {
    projects: summaries.length,
    estimates,
    portfolioTotal,
    medianCostPerM2,
  };
}

"use client";

import Link from "next/link";
import { useEffect, useState, use } from "react";

import { Card } from "@/components/ui/card";
import { SkeletonText } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtInr, fmtInrCompact, fmtInrDec, fmtPct } from "@/lib/inr";
import type { Benchmark, Estimate, Gate2Report } from "@/lib/types";

type ElementShare = { element: string; amount: number; pct: number };

const INDIAN_BENCHMARKS: Record<string, { label: string; low: number; high: number; unit: string }> = {
  concrete_m3_per_m2: { label: "Concrete", low: 0.12, high: 0.3, unit: "m³/m²" },
  steel_kg_per_m2: { label: "Steel", low: 10, high: 50, unit: "kg/m²" },
  cost_per_m2_basic: { label: "Cost / m² (basic)", low: 10000, high: 14000, unit: "₹/m²" },
  cost_per_m2_standard: { label: "Cost / m² (standard)", low: 13000, high: 18000, unit: "₹/m²" },
  cost_per_m2_premium: { label: "Cost / m² (premium)", low: 18000, high: 28000, unit: "₹/m²" },
};

export default function SummaryPage({ params }: PageProps<"/estimates/[id]/summary">) {
  const { id } = use(params);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [bench, setBench] = useState<Benchmark | null>(null);
  const [gate2, setGate2] = useState<Gate2Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [spec, setSpec] = useState<"basic" | "standard" | "premium">("standard");

  useEffect(() => {
    (async () => {
      try {
        const [e, b, g] = await Promise.all([
          api.getEstimate(id),
          api.getBenchmarks(id).catch(() => null),
          api.getGate2Report().catch(() => null),
        ]);
        setEstimate(e);
        setBench(b);
        setGate2(g);
        try {
          const p = await api.getEstimateParams(id);
          const level = p.inputs.spec_level;
          if (level === "basic" || level === "standard" || level === "premium") {
            setSpec(level);
          }
        } catch {
          /* ok */
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const totalsByElement = (estimate?.totals_by_element ?? {}) as Record<string, number>;
  const total = estimate?.total_cost ?? 0;
  const shares: ElementShare[] = Object.entries(totalsByElement)
    .map(([element, amount]) => ({
      element,
      amount,
      pct: total > 0 ? (amount / total) * 100 : 0,
    }))
    .sort((a, b) => b.amount - a.amount);

  const costPerM2Benchmark = INDIAN_BENCHMARKS[`cost_per_m2_${spec}`];

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-10">
      <header className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold">Summary</h1>
          <p className="mt-1 font-mono text-xs text-zinc-500">{id}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/estimates/${id}/boq`}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            Back to BOQ
          </Link>
          <a
            href={api.exportUrl(id, "xlsx")}
            target="_blank"
            rel="noreferrer"
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            Export .xlsx
          </a>
        </div>
      </header>

      {loading ? (
        <SkeletonText lines={6} />
      ) : (
        <>
          <section
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
            aria-label="Key metrics"
          >
            <Metric label="Total (preliminary)" value={fmtInrCompact(total)} sub={fmtInr(total)} />
            <Metric
              label="Cost / m²"
              value={bench ? `₹${bench.cost_per_m2.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}
              sub={bench ? `on ${bench.builtup_m2.toLocaleString("en-IN")} m²` : undefined}
            />
            <Metric
              label="Concrete / m²"
              value={bench?.concrete_m3_per_m2 != null ? `${bench.concrete_m3_per_m2.toFixed(3)} m³` : "—"}
            />
            <Metric
              label="Steel / m²"
              value={bench?.steel_kg_per_m2 != null ? `${bench.steel_kg_per_m2.toFixed(1)} kg` : "—"}
            />
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Benchmark gauges</h2>
            <div className="grid gap-3 sm:grid-cols-3">
              <Gauge
                label="Concrete / m²"
                unit="m³/m²"
                value={bench?.concrete_m3_per_m2 ?? null}
                low={INDIAN_BENCHMARKS.concrete_m3_per_m2.low}
                high={INDIAN_BENCHMARKS.concrete_m3_per_m2.high}
                format={(v) => v.toFixed(3)}
              />
              <Gauge
                label="Steel / m²"
                unit="kg/m²"
                value={bench?.steel_kg_per_m2 ?? null}
                low={INDIAN_BENCHMARKS.steel_kg_per_m2.low}
                high={INDIAN_BENCHMARKS.steel_kg_per_m2.high}
                format={(v) => v.toFixed(1)}
              />
              <Gauge
                label={`Cost / m² (${spec})`}
                unit="₹/m²"
                value={bench?.cost_per_m2 ?? null}
                low={costPerM2Benchmark.low}
                high={costPerM2Benchmark.high}
                format={(v) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Element shares</h2>
            <Card>
              <ol className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {shares.map((s) => (
                  <li key={s.element} className="flex items-center gap-3 py-2 text-sm">
                    <div className="w-36 shrink-0 capitalize">
                      {s.element.replace(/_/g, " ")}
                    </div>
                    <div className="h-2 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-blue-600"
                        style={{ width: `${s.pct.toFixed(1)}%` }}
                      />
                    </div>
                    <div className="w-32 shrink-0 text-right text-xs">
                      <span className="font-medium">{fmtInrCompact(s.amount)}</span>
                      <span className="ml-1 text-zinc-500">({fmtPct(s.pct)})</span>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </section>

          {gate2 && (
            <section>
              <h2 className="mb-3 text-lg font-semibold">Validation (Gate 2)</h2>
              <Gate2Panel report={gate2} />
            </section>
          )}
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- */

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </Card>
  );
}

function Gauge({
  label,
  unit,
  value,
  low,
  high,
  format,
}: {
  label: string;
  unit: string;
  value: number | null;
  low: number;
  high: number;
  format: (v: number) => string;
}) {
  const inBand = value != null && value >= low && value <= high;
  const span = high - low;
  const extended = { lo: low - span * 0.3, hi: high + span * 0.3 };
  const pct =
    value == null
      ? 0
      : Math.min(100, Math.max(0, ((value - extended.lo) / (extended.hi - extended.lo)) * 100));
  const lowPct = ((low - extended.lo) / (extended.hi - extended.lo)) * 100;
  const highPct = ((high - extended.lo) / (extended.hi - extended.lo)) * 100;

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
          <div className="mt-1 text-xl font-semibold">
            {value != null ? format(value) : "—"}
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase",
            value == null && "bg-zinc-100 text-zinc-500",
            value != null && inBand && "bg-emerald-100 text-emerald-900",
            value != null && !inBand && "bg-amber-100 text-amber-900",
          )}
        >
          {value == null ? "n/a" : inBand ? "in band" : "outside"}
        </span>
      </div>
      <div className="relative mt-5 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800" aria-hidden="true">
        <div
          className="absolute inset-y-0 rounded-full bg-emerald-200 dark:bg-emerald-900"
          style={{ left: `${lowPct}%`, width: `${highPct - lowPct}%` }}
        />
        {value != null && (
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-zinc-900 shadow dark:border-zinc-900 dark:bg-zinc-100"
            style={{ left: `${pct}%` }}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-zinc-400">
        <span>{format(low)}</span>
        <span>{format(high)}</span>
      </div>
      <div className="mt-0.5 text-[10px] text-zinc-500">
        typical Indian band {format(low)}–{format(high)} {unit}
      </div>
    </Card>
  );
}

function Gate2Panel({ report }: { report: Gate2Report }) {
  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">Overall</div>
          <div className="mt-1">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-semibold uppercase",
                report.passed
                  ? "bg-emerald-100 text-emerald-900"
                  : "bg-red-100 text-red-900",
              )}
            >
              {report.passed ? "Gate 2 PASS" : "Gate 2 FAIL"}
            </span>
          </div>
        </div>
        <div className="text-right text-xs text-zinc-500">
          <div>
            median total variance:{" "}
            <span className="font-medium">{report.median_total_abs_pct}%</span> / 20%
          </div>
          <div>
            median element wtd:{" "}
            <span className="font-medium">{report.median_element_weighted_pct}%</span> / 20%
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-zinc-50 text-left dark:bg-zinc-800">
            <tr>
              <th className="px-3 py-2 font-medium">Case</th>
              <th className="px-3 py-2 font-medium">Split</th>
              <th className="px-3 py-2 text-right font-medium">Expected</th>
              <th className="px-3 py-2 text-right font-medium">Computed</th>
              <th className="px-3 py-2 text-right font-medium">Δ total</th>
              <th className="px-3 py-2 text-right font-medium">Δ element wtd</th>
            </tr>
          </thead>
          <tbody>
            {report.cases.map((c) => (
              <tr key={c.case_id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="px-3 py-2">
                  <div className="font-medium">{c.case_id}</div>
                  <div className="text-xs text-zinc-500">{c.source}</div>
                </td>
                <td className="px-3 py-2 text-xs capitalize text-zinc-500">
                  {c.split.replace("_", " ")}
                </td>
                <td className="px-3 py-2 text-right">{fmtInrDec(c.expected_total_inr)}</td>
                <td className="px-3 py-2 text-right">{fmtInrDec(c.computed_total_inr)}</td>
                <td
                  className={cn(
                    "px-3 py-2 text-right font-medium",
                    Math.abs(c.total_delta_pct) <= 20 ? "text-emerald-700" : "text-red-700",
                  )}
                >
                  {c.total_delta_pct >= 0 ? "+" : ""}
                  {c.total_delta_pct}%
                </td>
                <td
                  className={cn(
                    "px-3 py-2 text-right font-medium",
                    c.element_weighted_abs_error_pct <= 20
                      ? "text-emerald-700"
                      : "text-red-700",
                  )}
                >
                  {c.element_weighted_abs_error_pct}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

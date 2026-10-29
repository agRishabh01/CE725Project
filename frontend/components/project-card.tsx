"use client";

import Link from "next/link";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { fmtInrCompact, fmtInrDec } from "@/lib/inr";
import type { ProjectSummary } from "@/lib/types";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const latestEstimateId = project.series[project.series.length - 1]?.estimate_id;
  const href = latestEstimateId
    ? `/estimates/${latestEstimateId}/boq`
    : `/estimates/new?project=${project.id}`;

  const sparkData = project.series
    .filter((p) => p.cost_per_m2 != null)
    .map((p, i) => ({
      i,
      value: p.cost_per_m2 ?? 0,
      total: p.total_inr ?? 0,
    }));

  return (
    <Link
      href={href}
      className="group block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
      aria-label={`Open latest estimate for ${project.name}`}
    >
      <Card className="h-full transition-colors group-hover:border-zinc-400 dark:group-hover:border-zinc-600">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-semibold text-zinc-900 dark:text-zinc-50">
              {project.name}
            </h3>
            <p className="mt-0.5 truncate text-xs text-zinc-500">
              {(project.use_type ?? "—").replace(/_/g, " ")} ·{" "}
              {project.location ?? "—"}
            </p>
          </div>
          <div className="text-right text-xs text-zinc-400">
            {project.estimate_count} est.
          </div>
        </div>

        {project.latest_total_inr != null ? (
          <div className="mt-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Latest total</div>
            <div className="mt-0.5 text-lg font-semibold">
              {fmtInrCompact(project.latest_total_inr)}
            </div>
            {project.latest_cost_per_m2 != null && (
              <div className="mt-0.5 text-xs text-zinc-500">
                {fmtInrDec(project.latest_cost_per_m2)} / m²
              </div>
            )}
          </div>
        ) : (
          <div className="mt-4 text-sm text-zinc-500">No estimates yet.</div>
        )}

        {sparkData.length >= 2 ? (
          <div className="mt-4 h-10" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Tooltip
                  cursor={false}
                  wrapperStyle={{ outline: "none" }}
                  contentStyle={{ fontSize: 11, padding: "4px 8px" }}
                  labelFormatter={() => ""}
                  formatter={(_v, _n, p) => [
                    `${fmtInrDec(Number(p.payload.value))} / m²`,
                    "cost/m²",
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : project.estimate_count > 0 ? (
          <div className="mt-4 h-10 text-[11px] text-zinc-400">
            Add a second estimate to see cost/m² trend
          </div>
        ) : null}

        <div className="mt-3 text-[11px] text-zinc-400">
          created {new Date(project.created_at).toLocaleDateString("en-IN")}
        </div>
      </Card>
    </Link>
  );
}

"use client";

import { cn } from "@/lib/cn";

export type Step = { id: string; label: string };

export function Stepper({
  steps,
  currentId,
}: {
  steps: Step[];
  currentId: string;
}) {
  const currentIndex = steps.findIndex((s) => s.id === currentId);
  return (
    <ol
      className="flex items-center gap-3 overflow-x-auto"
      aria-label={`Wizard progress: step ${currentIndex + 1} of ${steps.length}`}
    >
      {steps.map((step, i) => {
        const state: "done" | "current" | "pending" =
          i < currentIndex ? "done" : i === currentIndex ? "current" : "pending";
        return (
          <li key={step.id} className="flex items-center gap-3">
            <div
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold border",
                state === "done" && "bg-zinc-900 text-white border-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 dark:border-zinc-100",
                state === "current" && "bg-blue-700 text-white border-blue-700",
                state === "pending" && "bg-white text-zinc-500 border-zinc-300 dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-400",
              )}
              aria-current={state === "current" ? "step" : undefined}
              aria-label={`${step.label}, ${state}`}
            >
              <span aria-hidden="true">{state === "done" ? "✓" : i + 1}</span>
            </div>
            <span
              className={cn(
                "text-sm whitespace-nowrap",
                state === "current" ? "font-medium text-zinc-900 dark:text-zinc-50" : "text-zinc-600 dark:text-zinc-400",
              )}
            >
              {step.label}
            </span>
            {i < steps.length - 1 && (
              <div className="h-px w-6 bg-zinc-300 dark:bg-zinc-700" aria-hidden="true" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

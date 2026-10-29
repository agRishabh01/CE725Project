"use client";

import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}

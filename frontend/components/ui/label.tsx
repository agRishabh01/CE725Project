"use client";

import type { LabelHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Label({ className, children, ...rest }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5",
        className,
      )}
      {...rest}
    >
      {children}
    </label>
  );
}

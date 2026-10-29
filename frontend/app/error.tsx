"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface in dev console; W23 wires Sentry.
    // eslint-disable-next-line no-console
    console.error("Caught by error boundary:", error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center px-4 py-10 text-center">
      <div className="text-xs font-semibold uppercase tracking-wide text-red-600">Error</div>
      <h1 className="mt-2 text-3xl font-semibold">Something broke on this page</h1>
      <p className="mt-2 max-w-md text-sm text-zinc-600 dark:text-zinc-400">
        {error.message ||
          "We hit an unexpected problem. The error has been logged; try again, or go back."}
      </p>
      {error.digest && (
        <code className="mt-3 inline-block rounded bg-zinc-100 px-2 py-1 text-xs font-mono text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
          id {error.digest}
        </code>
      )}
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Try again
        </button>
        <Link
          href="/"
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}

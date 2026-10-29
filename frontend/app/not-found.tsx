import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center px-4 py-10 text-center">
      <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">404</div>
      <h1 className="mt-2 text-3xl font-semibold">Page not found</h1>
      <p className="mt-2 max-w-md text-sm text-zinc-600 dark:text-zinc-400">
        The estimate or project you’re looking for doesn’t exist, or you don’t have access.
      </p>
      <div className="mt-6 flex gap-3">
        <Link
          href="/"
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Back to dashboard
        </Link>
        <Link
          href="/estimates/new"
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Start a new estimate
        </Link>
      </div>
    </div>
  );
}

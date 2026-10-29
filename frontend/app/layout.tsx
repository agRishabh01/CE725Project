import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/toast";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CE 725 BOQ",
  description: "AI-Assisted BOQ and Cost Estimation",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-zinc-900 focus:px-3 focus:py-1.5 focus:text-sm focus:font-medium focus:text-white dark:focus:bg-zinc-100 dark:focus:text-zinc-900"
        >
          Skip to main content
        </a>
        <ToastProvider>
          <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
              <Link
                href="/"
                className="flex items-center gap-2 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
                aria-label="CE 725 BOQ home"
              >
                <span className="h-6 w-6 rounded bg-zinc-900 dark:bg-zinc-100" aria-hidden="true" />
                <span className="font-semibold">CE 725 BOQ</span>
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900 dark:bg-amber-900 dark:text-amber-100">
                  Preliminary
                </span>
              </Link>
              <nav className="flex items-center gap-4 text-sm" aria-label="Primary">
                <Link
                  href="/"
                  className="rounded px-2 py-1 text-zinc-600 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 dark:text-zinc-400 dark:hover:text-zinc-50"
                >
                  Dashboard
                </Link>
                <Link
                  href="/estimates/new"
                  className="rounded-md bg-zinc-900 px-3 py-1.5 font-medium text-white hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
                >
                  New estimate
                </Link>
              </nav>
            </div>
          </header>
          <main id="main" className="flex-1">
            {children}
          </main>
        </ToastProvider>
      </body>
    </html>
  );
}

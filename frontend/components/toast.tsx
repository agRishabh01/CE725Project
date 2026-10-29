"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

type ToastTone = "info" | "success" | "warning" | "error";

type Toast = {
  id: number;
  tone: ToastTone;
  title: string;
  message?: string;
  timeoutMs?: number;
};

type ToastApi = {
  push: (t: Omit<Toast, "id">) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
};

const Ctx = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [stack, setStack] = useState<Toast[]>([]);

  const push = useCallback<ToastApi["push"]>((t) => {
    const id = Date.now() + Math.random();
    setStack((s) => [...s, { ...t, id }]);
  }, []);

  const api: ToastApi = {
    push,
    success: (title, message) => push({ tone: "success", title, message }),
    error: (title, message) => push({ tone: "error", title, message, timeoutMs: 7000 }),
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2"
      >
        {stack.map((t) => (
          <ToastItem
            key={t.id}
            toast={t}
            onDismiss={() => setStack((s) => s.filter((x) => x.id !== t.id))}
          />
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(Ctx);
  if (!api) throw new Error("useToast must be used inside <ToastProvider>");
  return api;
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, toast.timeoutMs ?? 4000);
    return () => clearTimeout(t);
  }, [onDismiss, toast.timeoutMs]);

  const tone: Record<ToastTone, string> = {
    info: "border-zinc-300 bg-white text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100",
    success: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-100",
    warning: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100",
    error: "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-100",
  };

  return (
    <div
      role={toast.tone === "error" ? "alert" : "status"}
      className={cn(
        "pointer-events-auto rounded-md border p-3 shadow-md",
        tone[toast.tone],
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <div className="text-sm font-medium">{toast.title}</div>
          {toast.message && (
            <div className="mt-0.5 text-xs opacity-90">{toast.message}</div>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="ml-2 rounded px-1 text-sm opacity-60 hover:opacity-100"
          aria-label="Dismiss notification"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

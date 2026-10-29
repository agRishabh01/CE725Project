"use client";

import { useEffect, useState } from "react";

import { Overlay } from "@/components/overlay";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import type { BOQLine } from "@/lib/types";

export function OverrideModal({
  estimateId,
  line,
  focusField,
  onClose,
  onApplied,
}: {
  estimateId: string;
  line: BOQLine | null;
  focusField: "qty" | "rate";
  onClose: () => void;
  onApplied: (updated: BOQLine) => void;
}) {
  const open = line !== null;
  const [qty, setQty] = useState<string>("");
  const [rate, setRate] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!line) return;
    setQty(String(line.qty));
    setRate(line.rate != null ? String(line.rate) : "");
    setReason("");
    setError(null);
  }, [line]);

  async function onSave() {
    if (!line) return;
    setSubmitting(true);
    setError(null);
    try {
      const qtyNum = qty === "" ? undefined : Number(qty);
      const rateNum = rate === "" ? undefined : Number(rate);
      if (qtyNum !== undefined && !Number.isFinite(qtyNum)) throw new Error("qty must be a number");
      if (rateNum !== undefined && !Number.isFinite(rateNum)) throw new Error("rate must be a number");
      if (reason.trim().length < 3)
        throw new Error("reason must be at least 3 characters (audit trail)");

      const updated = await api.patchBOQLine(estimateId, line.id, {
        qty: qtyNum,
        rate: rateNum,
        override_reason: reason.trim(),
      });
      onApplied(updated);
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Overlay open={open} onClose={submitting ? () => {} : onClose}>
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl dark:bg-zinc-900"
          role="dialog"
          aria-label="Override quantity or rate"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <h2 className="text-base font-semibold">Override line</h2>
          <p className="mt-0.5 text-xs text-zinc-500">
            Changes are flagged on the BOQ and recorded with a reason.
          </p>

          {line && (
            <div className="mt-3 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-800">
              <div className="font-medium text-zinc-900 dark:text-zinc-100">
                {line.description}
              </div>
              <div className="mt-0.5 text-zinc-500">
                {line.element.replace(/_/g, " ")} · seq {line.seq} · unit {line.unit}
              </div>
            </div>
          )}

          <div className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="o-qty">Qty</Label>
              <Input
                id="o-qty"
                type="number"
                inputMode="decimal"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                autoFocus={focusField === "qty"}
              />
            </div>
            <div>
              <Label htmlFor="o-rate">Rate (INR)</Label>
              <Input
                id="o-rate"
                type="number"
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                autoFocus={focusField === "rate"}
              />
            </div>
          </div>

          <div className="mt-3">
            <Label htmlFor="o-reason">Reason</Label>
            <textarea
              id="o-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              placeholder="Why does this line differ from the engine's number?"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </div>

          {error && (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-900">
              {error}
            </div>
          )}

          <div className="mt-5 flex items-center justify-end gap-2">
            <Button variant="ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={submitting}>
              {submitting ? "Saving…" : "Save override"}
            </Button>
          </div>
        </div>
      </div>
    </Overlay>
  );
}

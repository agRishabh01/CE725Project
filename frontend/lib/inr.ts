// Indian number format helpers (lakh/crore via Intl).

const _fmtInr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const _fmtInrDecimal = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const _fmtQty = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 3,
});
const _fmtPct = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export const fmtInr = (n: number): string => _fmtInr.format(n);
export const fmtInrDec = (n: number): string => _fmtInrDecimal.format(n);
export const fmtQty = (n: number): string => _fmtQty.format(n);
export const fmtPct = (n: number): string => `${_fmtPct.format(n)}%`;

/** Compact lakh/crore for big totals: 45,35,970 → "₹45.36 L", 4,53,59,699 → "₹4.54 Cr". */
export function fmtInrCompact(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)} L`;
  return _fmtInr.format(n);
}

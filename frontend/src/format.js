const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

export const money = (v) => (v == null ? null : inr.format(v));

export function months(v) {
  if (v == null) return null;
  if (v < 1) return `${Math.round(v * 30)} days`;
  return `${Number.isInteger(v) ? v : v.toFixed(1)} month${v === 1 ? "" : "s"}`;
}

export const percent = (v) => (v == null ? null : `${v}%`);

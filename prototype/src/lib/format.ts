// Number formats (§16.7). Shared by server pages and client charts.
export type Formattable = { state?: string; value: string | number | null; unit: string };

export function sar(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (abs >= 1e9) return `${sign}SAR ${(abs / 1e9).toFixed(2)}bn`;
  if (abs >= 1e6) return `${sign}SAR ${(abs / 1e6).toFixed(1)}m`;
  if (abs >= 1e3) return `${sign}SAR ${(abs / 1e3).toFixed(0)}k`;
  return `${sign}SAR ${abs.toFixed(0)}`;
}

export function pct(v: number, decimals = 1): string {
  return `${v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(decimals)}%`;
}

// The true minus sign (U+2212), as everywhere else on screen (§16.7); a value that rounds to zero shows no sign.
const minus = (v: number) => (v < 0 && Math.abs(v) >= 0.05 ? "−" : "");

export function formatNumber(v: number, unit: string): string {
  switch (unit) {
    case "SAR": return sar(v);
    case "ratio": return pct(v);
    case "percent": return `${minus(v)}${Math.abs(v).toFixed(1)}%`;
    case "days": return `${Math.round(v)} days`;
    case "x": return `${minus(v)}${Math.abs(v).toFixed(1)}x`;
    case "count": return `${minus(v)}${Math.abs(v).toFixed(1)}`;
    default: return String(v);
  }
}

export function formatValue(k: Formattable): string {
  if (k.state === "needs_data") return "Needs data";
  if (k.state === "not_applicable") return "Not applicable";
  if (k.state === "n.m." || k.value === null) return "n.m.";
  return formatNumber(Number(k.value), k.unit);
}

export function monthLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
}

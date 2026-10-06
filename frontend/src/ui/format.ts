// Number formatting for scientific readouts (SI units, tabular digits).

const nf = (d: number) =>
  new Intl.NumberFormat("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });

export function num(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : nf(digits).format(v);
}

/** Volume in m³ as "8.50 × 10⁶" (value part only). */
export function sci(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return v === 0 ? "0" : "—";
  const e = Math.floor(Math.log10(Math.abs(v)));
  const m = v / 10 ** e;
  const sup = String(e)
    .split("")
    .map((c) => "⁰¹²³⁴⁵⁶⁷⁸⁹"["0123456789".indexOf(c)] ?? (c === "-" ? "⁻" : c))
    .join("");
  return `${m.toFixed(digits)} × 10${sup}`;
}

export function duration(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export function lonLat(lon: number, lat: number): string {
  const ew = lon >= 0 ? "E" : "W";
  const ns = lat >= 0 ? "N" : "S";
  return `${Math.abs(lat).toFixed(5)}° ${ns}, ${Math.abs(lon).toFixed(5)}° ${ew}`;
}

import type { RiskLevel } from "./api";

export const LEVEL_COLOR: Record<RiskLevel, string> = {
  NORMAL: "#4f9d69",
  WATCH: "#edc948",
  WARNING: "#e8a33d",
  CRITICAL: "#d1495b",
  UNKNOWN: "#6c7a89",
};

// Temperature stops (°C → colour), diverging blue → red
export const TEMP_STOPS: [number, string][] = [
  [-30, "#313695"], [-15, "#4575b4"], [0, "#74add1"], [10, "#abd9e9"],
  [18, "#fee090"], [25, "#fdae61"], [32, "#f46d43"], [40, "#d73027"],
];

export function tempColor(t: number | null | undefined): string {
  if (t == null) return "#6c7a89";
  if (t <= TEMP_STOPS[0][0]) return TEMP_STOPS[0][1];
  for (let i = 1; i < TEMP_STOPS.length; i++) {
    if (t <= TEMP_STOPS[i][0]) return TEMP_STOPS[i][1];
  }
  return TEMP_STOPS[TEMP_STOPS.length - 1][1];
}

export function fmt(v: number | null | undefined, digits = 1, unit = ""): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(digits)}${unit}`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

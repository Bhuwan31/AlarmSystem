"use client";

import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { fmt, tempColor } from "@/lib/colors";

interface PointWeather {
  lat: number; lon: number; elevation_m: number | null; observed_at: string | null;
  current: {
    temperature_c: number | null; apparent_temp_c: number | null; humidity_pct: number | null; dew_point_c: number | null;
    pressure_hpa: number | null; precipitation_mm: number | null; cloud_cover_pct: number | null;
    wind_speed_kmh: number | null; wind_dir_deg: number | null; wind_gust_kmh: number | null; is_day: number | null;
  };
  air_flow: { label: string; height_m: number | null; speed_kmh: number | null; direction_deg: number | null; temperature_c?: number | null }[];
  outlook_24h: { t: string; temperature_c: number; humidity_pct: number; wind_kmh: number; precip_mm: number }[];
  daily: { date: string; tmax_c: number; tmin_c: number }[];
  heat: { level: "NONE" | "HOT" | "HEATWAVE" | "EXTREME_HEAT"; advice: string; max_temp_3d_c: number | null };
  source: string;
}

const HEAT_STYLE: Record<PointWeather["heat"]["level"], [string, string]> = {
  NONE: ["#e7f4ea", "#1e6b35"], HOT: ["#fff4d6", "#8a5a00"], HEATWAVE: ["#fde2cc", "#a8380f"], EXTREME_HEAT: ["#f8d0d3", "#8b0f1a"],
};
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const compass = (deg: number | null) => (deg == null ? "—" : COMPASS[Math.round(deg / 45) % 8]);

export default function LocationPanel({ lng, lat, onClose }: { lng: number; lat: number; onClose: () => void }) {
  const { data, error, isLoading } = useSWR<PointWeather>(`/api/v1/weather/point?lat=${lat.toFixed(3)}&lon=${lng.toFixed(3)}`, fetcher);
  const c = data?.current;

  return (
    <div className="space-y-3 text-sm text-slate-800">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold">Selected location — now</div>
          <div className="text-xs text-slate-500">{lat.toFixed(3)}°, {lng.toFixed(3)}° · {data?.elevation_m != null ? `${Math.round(data.elevation_m)} m elevation` : "…"}</div>
        </div>
        <button onClick={onClose} className="rounded-md bg-slate-100 px-2 py-1 text-xs hover:bg-slate-200">Close ✕</button>
      </div>

      {isLoading && <p className="text-slate-500">Loading current conditions…</p>}
      {error && <p className="text-red-700">Could not load weather for this place.</p>}

      {c && data && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Tile label="Temperature" value={fmt(c.temperature_c, 1, " °C")} sub={`feels like ${fmt(c.apparent_temp_c, 1, " °C")}`} accent={tempColor(c.temperature_c)} />
            <Tile label="Humidity" value={fmt(c.humidity_pct, 0, " %")} sub={`dew point ${fmt(c.dew_point_c, 1, " °C")}`} />
            <Tile label="Wind (10 m)" value={`${fmt(c.wind_speed_kmh, 0, " km/h")} ${compass(c.wind_dir_deg)}`} sub={`gusts ${fmt(c.wind_gust_kmh, 0, " km/h")}`} />
            <Tile label="Pressure / cloud" value={fmt(c.pressure_hpa, 0, " hPa")} sub={`cloud ${fmt(c.cloud_cover_pct, 0, " %")} · rain ${fmt(c.precipitation_mm, 1, " mm")}`} />
          </div>

          <div className="rounded-lg p-2.5" style={{ background: HEAT_STYLE[data.heat.level][0], color: HEAT_STYLE[data.heat.level][1] }}>
            <div className="text-xs font-semibold">Heat: {data.heat.level.replace("_", " ")} · max next 3 days {fmt(data.heat.max_temp_3d_c, 0, " °C")}</div>
            <div className="text-xs">{data.heat.advice}</div>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-slate-600">Air flow through this place (surface → jet stream)</div>
            <table className="w-full text-xs">
              <tbody>
                {data.air_flow.map((a) => (
                  <tr key={a.label} className="border-t border-slate-100">
                    <td className="py-1 pr-2 text-slate-500">{a.label}{a.height_m != null && a.label.includes("hPa") ? ` (~${(a.height_m / 1000).toFixed(1)} km)` : ""}</td>
                    <td className="w-6">
                      {a.direction_deg != null && (
                        <svg width="16" height="16" viewBox="0 0 16 16" style={{ transform: `rotate(${a.direction_deg + 180}deg)` }} aria-label={`towards ${compass((a.direction_deg + 180) % 360)}`}>
                          <path d="M8 1 L12 7 H9 V15 H7 V7 H4 Z" fill="#24305e" />
                        </svg>
                      )}
                    </td>
                    <td className="tabular-nums">{fmt(a.speed_kmh, 0, " km/h")}</td>
                    <td className="text-slate-500">from {compass(a.direction_deg)}</td>
                    <td className="text-right tabular-nums text-slate-500">{a.temperature_c != null ? fmt(a.temperature_c, 0, "°") : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-slate-600">Next 24 hours</div>
            <Spark values={data.outlook_24h.map((o) => o.temperature_c)} color="#d7301f" label="Temperature °C" />
            <Spark values={data.outlook_24h.map((o) => o.humidity_pct)} color="#2b8cbe" label="Humidity %" />
            <Spark values={data.outlook_24h.map((o) => o.wind_kmh)} color="#5b3fa6" label="Wind km/h" />
          </div>

          <p className="text-[11px] text-slate-400">The map shows this place in 3D with real terrain. {data.source}. Observed {data.observed_at} UTC.</p>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2" style={accent ? { borderLeft: `4px solid ${accent}` } : undefined}>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-base font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-slate-500">{sub}</div>}
    </div>
  );
}

function Spark({ values, color, label }: { values: number[]; color: string; label: string }) {
  if (!values.length) return null;
  const w = 260, h = 34, lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 3 - ((v - lo) / span) * (h - 6)}`).join(" ");
  return (
    <div className="mb-1 flex items-center gap-2">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="max-w-full" role="img" aria-label={`${label} from ${lo.toFixed(0)} to ${hi.toFixed(0)}`}>
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2" />
      </svg>
      <div className="w-20 text-[10px] text-slate-500">{label}<br />{lo.toFixed(0)}–{hi.toFixed(0)}</div>
    </div>
  );
}

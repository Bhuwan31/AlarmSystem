"use client";

import Link from "next/link";
import { useMemo } from "react";
import useSWR from "swr";

import { PageHeader, Panel, Stat } from "@/components/ui";
import { fetcher, type FC, type GridProps } from "@/lib/api";
import { fmt, tempColor } from "@/lib/colors";
import { useWeatherSummary } from "@/lib/hooks";

// Reference places for a quick national picture (coordinates of city centres)
const PLACES: [string, number, number][] = [
  ["Kathmandu", 27.7172, 85.324], ["Pokhara", 28.2096, 83.9856], ["Biratnagar", 26.4525, 87.2718], ["Birgunj", 27.0104, 84.877],
  ["Janakpur", 26.7288, 85.9263], ["Bharatpur", 27.6833, 84.4333], ["Butwal", 27.7006, 83.4483], ["Nepalgunj", 28.05, 81.6167],
  ["Dhangadhi", 28.6833, 80.6], ["Jumla", 29.2747, 82.1838], ["Namche Bazaar", 27.8069, 86.714],
];
const HEAT: Record<string, string> = { NONE: "text-emerald-300", HOT: "text-amber-300", HEATWAVE: "text-orange-400", EXTREME_HEAT: "text-red-400" };

interface Point {
  elevation_m: number;
  current: { temperature_c: number; apparent_temp_c: number; humidity_pct: number; wind_speed_kmh: number; precipitation_mm: number; cloud_cover_pct: number };
  heat: { level: string; max_temp_3d_c: number | null };
}

function PlaceCard({ name, lat, lon }: { name: string; lat: number; lon: number }) {
  const { data } = useSWR<Point>(`/api/v1/weather/point?lat=${lat}&lon=${lon}`, fetcher, { refreshInterval: 15 * 60_000 });
  const c = data?.current;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex items-baseline justify-between">
        <div className="font-semibold">{name}</div>
        <div className="text-[11px] text-slate-400">{data ? `${Math.round(data.elevation_m)} m` : ""}</div>
      </div>
      {c ? (
        <>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums" style={{ color: tempColor(c.temperature_c) }}>{fmt(c.temperature_c, 0, "°")}</span>
            <span className="text-xs text-slate-400">feels {fmt(c.apparent_temp_c, 0, "°")}</span>
          </div>
          <div className="mt-1 text-xs text-slate-400">💧 {fmt(c.humidity_pct, 0, "%")} · 💨 {fmt(c.wind_speed_kmh, 0, " km/h")} · ☁ {fmt(c.cloud_cover_pct, 0, "%")}</div>
          <div className={`mt-1 text-xs font-semibold ${HEAT[data.heat.level] ?? ""}`}>Heat: {data.heat.level.replace("_", " ")} · max {fmt(data.heat.max_temp_3d_c, 0, "°")} next 3 days</div>
        </>
      ) : <div className="mt-2 text-sm text-slate-400">Loading…</div>}
    </div>
  );
}

export default function WeatherPage() {
  const { data: s } = useWeatherSummary();
  const { data: grid } = useSWR<FC<GridProps>>("/api/v1/weather/grid?grid=nepal", fetcher, { refreshInterval: 60_000 });
  const extremes = useMemo(() => {
    const f = (grid?.features ?? []).filter((x) => x.properties.temperature_c != null);
    const by = (k: keyof GridProps, desc = true) => [...f].sort((a, b) => ((b.properties[k] as number) - (a.properties[k] as number)) * (desc ? 1 : -1)).slice(0, 5);
    return { hot: by("tmax_3d_c"), cold: by("temperature_c", false), windy: by("wind_speed_kmh"), wet: by("rain_24h_forecast_mm"),
             heatCells: f.filter((x) => (x.properties.tmax_3d_c ?? 0) >= 35).length, total: f.length };
  }, [grid]);
  const cell = (x: { geometry: { coordinates: [number, number] } }) => `${x.geometry.coordinates[1].toFixed(2)}°N ${x.geometry.coordinates[0].toFixed(2)}°E`;

  return (
    <div className="space-y-4">
      <PageHeader title="Weather & heat" subtitle="Model data from Open-Meteo for the deployment area. Heat status uses the next 3 days' maximum temperature (thresholds are configurable assumptions)."
                  actions={<Link href="/map" className="text-sm text-sky-300 hover:underline">Open 3D map →</Link>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Average temperature" value={fmt(s?.t_avg, 1, " °C")} sub={`${fmt(s?.t_min, 0, "°")} to ${fmt(s?.t_max, 0, "°")}`} />
        <Stat label="Max wind / gust" value={fmt(s?.wind_max, 0, " km/h")} sub={`gusts ${fmt(s?.gust_max, 0, " km/h")}`} />
        <Stat label="Max rain next 24 h" value={fmt(s?.rain24_max, 1, " mm")} />
        <Stat label="Average humidity" value={fmt(s?.rh_avg, 0, " %")} />
        <Stat label="Heat-risk cells (≥35 °C)" value={`${extremes.heatCells} / ${extremes.total}`} sub="next 3 days" />
      </div>
      <Panel title="Conditions in main towns">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {PLACES.map(([n, la, lo]) => <PlaceCard key={n} name={n} lat={la} lon={lo} />)}
        </div>
      </Panel>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {([["Hottest next 3 days", extremes.hot, "tmax_3d_c", "°C"], ["Coldest now", extremes.cold, "temperature_c", "°C"],
           ["Windiest now", extremes.windy, "wind_speed_kmh", " km/h"], ["Most rain next 24 h", extremes.wet, "rain_24h_forecast_mm", " mm"]] as const).map(([title, list, key, unit]) => (
          <Panel key={title} title={title}>
            <ul className="space-y-1 text-sm">
              {list.map((x, i) => <li key={i} className="flex justify-between"><span className="text-slate-400">{cell(x)}</span><span className="tabular-nums">{fmt(x.properties[key] as number, 1, unit)}</span></li>)}
            </ul>
          </Panel>
        ))}
      </div>
    </div>
  );
}

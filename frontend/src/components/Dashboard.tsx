"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { RiskLevel } from "@/lib/api";
import { ago, fmt, LEVEL_COLOR } from "@/lib/colors";
import { RAMPS, rampCss } from "@/lib/field";
import { useMapData, useStatus, useWarnings, useWeatherSummary } from "@/lib/hooks";
import { DEFAULT_FILTERS, MINI_LAYERS } from "@/lib/layers";
import MapExplorer from "./MapExplorer";
import { LevelBadge, Notice, Panel, Stat, StatusDot } from "./ui";

const WeatherGlobe = dynamic(() => import("./WeatherGlobe"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-sm text-slate-500">Loading globe…</div>,
});
const LEVELS: RiskLevel[] = ["CRITICAL", "WARNING", "WATCH", "NORMAL", "UNKNOWN"];

export default function Dashboard() {
  const data = useMapData();
  const { rivers, rain } = data;
  const { data: summary, error: apiError } = useWeatherSummary();
  const { data: status } = useStatus();
  const { data: warnings } = useWarnings();
  const [full, setFull] = useState(false);

  const levelCounts = useMemo(() => {
    const c: Record<RiskLevel, number> = { CRITICAL: 0, WARNING: 0, WATCH: 0, NORMAL: 0, UNKNOWN: 0 };
    rivers?.features.forEach((f) => (c[f.properties.risk_level] += 1));
    return c;
  }, [rivers]);
  const topRivers = useMemo(() => [...(rivers?.features ?? [])]
    .filter((f) => f.properties.ratio_to_warning != null)
    .sort((a, b) => (b.properties.ratio_to_warning ?? 0) - (a.properties.ratio_to_warning ?? 0)).slice(0, 10), [rivers]);
  const topRain = useMemo(() => [...(rain?.features ?? [])]
    .filter((f) => f.properties.rain_24h_mm != null)
    .sort((a, b) => (b.properties.rain_24h_mm ?? 0) - (a.properties.rain_24h_mm ?? 0)).slice(0, 8), [rain]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-xl font-semibold sm:text-2xl">Operations overview</h1>
        <span className="text-xs text-slate-400">Weather updated {ago(summary?.observed_at)}</span>
      </div>
      {apiError && <Notice kind="error">Cannot reach the AMHEWS API ({apiError.message}). Showing last loaded data.</Notice>}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <section className="space-y-4">
          <button onClick={() => setFull(true)} aria-label="Open full-screen 3D weather map"
                  className="group relative block h-[340px] w-full overflow-hidden rounded-xl border border-white/10 bg-[#e9f1f7] text-left sm:h-[420px]">
            {!full && <WeatherGlobe mode="mini" {...data} layers={MINI_LAYERS} filters={DEFAULT_FILTERS} />}
            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between bg-gradient-to-b from-white/90 to-transparent p-3 text-slate-800">
              <div>
                <div className="text-sm font-semibold">Live weather — world view, Nepal border</div>
                <div className="text-xs text-slate-600">Temperature · wind flow · rivers</div>
              </div>
              <span className="rounded-md bg-slate-900/80 px-2 py-1 text-xs text-white group-hover:bg-slate-900">⤢ Full screen</span>
            </div>
            <TempLegend className="pointer-events-none absolute bottom-3 left-3" />
          </button>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Avg temperature" value={fmt(summary?.t_avg, 1, " °C")} sub={`${fmt(summary?.t_min, 0, "°")} to ${fmt(summary?.t_max, 0, "°")}`} />
            <Stat label="Max wind / gust" value={fmt(summary?.wind_max, 0, " km/h")} sub={`gusts ${fmt(summary?.gust_max, 0, " km/h")}`} />
            <Stat label="Max rain forecast 24 h" value={fmt(summary?.rain24_max, 1, " mm")} sub={`now ${fmt(summary?.precip_max, 1, " mm/h")}`} />
            <Stat label="Avg humidity" value={fmt(summary?.rh_avg, 0, " %")} sub={`${summary?.n ?? 0} grid cells`} />
          </div>

          <Panel title="Rivers closest to warning level" note={<Link href="/rivers" className="text-sky-300 hover:underline">All rivers →</Link>}>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-slate-400">
                <tr><th className="py-1">Station</th><th>Level</th><th className="hidden sm:table-cell">Warning</th><th>Index</th><th>Risk</th><th className="hidden md:table-cell">Updated</th></tr>
              </thead>
              <tbody>
                {topRivers.map(({ properties: p }) => (
                  <tr key={p.id} className="border-t border-white/5">
                    <td className="py-1.5 pr-2"><Link href={`/stations/${p.id}`} className="font-medium hover:underline">{p.name}</Link><div className="text-xs text-slate-400">{p.basin} · {p.trend?.toLowerCase()}</div></td>
                    <td className="pr-2 tabular-nums">{fmt(p.value, 2, " m")}</td>
                    <td className="hidden pr-2 tabular-nums sm:table-cell">{fmt(p.warning_level, 2, " m")}</td>
                    <td className="pr-2 tabular-nums">{fmt(p.ratio_to_warning, 2)}</td>
                    <td><LevelBadge level={p.risk_level} /></td>
                    <td className="hidden text-xs text-slate-400 md:table-cell">{ago(p.observed_at)}</td>
                  </tr>
                ))}
                {!topRivers.length && <tr><td colSpan={6} className="py-3 text-slate-400">Waiting for gauge data…</td></tr>}
              </tbody>
            </table>
          </Panel>
        </section>

        <section className="space-y-4">
          <Panel title="River risk now" note={`${rivers?.features.length ?? 0} river reaches assessed`}>
            <div className="grid grid-cols-5 gap-2">
              {LEVELS.map((l) => (
                <Link key={l} href={`/rivers?level=${l}`} className="rounded-lg bg-white/5 p-2 text-center hover:bg-white/10">
                  <div className="text-2xl font-semibold tabular-nums" style={{ color: LEVEL_COLOR[l] }}>{levelCounts[l]}</div>
                  <div className="text-[10px] tracking-wide text-slate-400">{l}</div>
                </Link>
              ))}
            </div>
          </Panel>

          <Panel title="Warnings" note={<Link href="/warnings" className="text-sky-300 hover:underline">Manage →</Link>}>
            {warnings?.length ? (
              <ul className="space-y-2">
                {warnings.slice(0, 5).map((w) => (
                  <li key={w.id} className="rounded-lg border border-white/10 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium">{w.station_name}</div>
                      <div className="flex gap-1"><LevelBadge level={w.level} /><span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px]">{w.status}</span></div>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">{w.reasons.join(" · ")}</p>
                  </li>
                ))}
                {warnings.length > 5 && <li className="text-xs text-slate-400">+{warnings.length - 5} more on the Warnings page</li>}
              </ul>
            ) : <p className="text-sm text-slate-400">No active or proposed warnings.</p>}
          </Panel>

          <Panel title="Heaviest rain, last 24 h" note={<Link href="/rain" className="text-sky-300 hover:underline">All rain gauges →</Link>}>
            <ul className="space-y-1 text-sm">
              {topRain.map(({ properties: p }) => (
                <li key={p.id} className="flex justify-between border-t border-white/5 py-1">
                  <Link href={`/stations/${p.id}`} className="hover:underline">{p.name} <span className="text-xs text-slate-400">{p.district}</span></Link>
                  <span className="tabular-nums">{fmt(p.rain_24h_mm, 1, " mm")}</span>
                </li>
              ))}
              {!topRain.length && <li className="text-slate-400">Waiting for rain data…</li>}
            </ul>
          </Panel>

          <Panel title="Data sources" note={<Link href="/sources" className="text-sky-300 hover:underline">Details →</Link>}>
            <ul className="space-y-1.5 text-sm">
              {status?.map((s) => (
                <li key={s.code} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2"><StatusDot state={s.state} />{s.name}</span>
                  <span className="text-xs text-slate-400">{s.state === "ok" ? ago(s.last_success_at) : s.state.replace("_", " ")}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </section>
      </div>

      {full && (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Full-screen 3D weather map">
          <MapExplorer onClose={() => setFull(false)} />
        </div>
      )}
    </div>
  );
}

function TempLegend({ className = "" }: { className?: string }) {
  const r = RAMPS.temperature;
  return (
    <div className={`w-56 rounded-md bg-white/85 px-2 py-1 text-[10px] text-slate-700 ${className}`}>
      <div className="mb-0.5">Temperature °C</div>
      <div className="h-2 rounded" style={{ background: rampCss(r) }} />
      <div className="flex justify-between"><span>{r[0][0]}</span><span>0</span><span>{r.at(-1)![0]}</span></div>
    </div>
  );
}

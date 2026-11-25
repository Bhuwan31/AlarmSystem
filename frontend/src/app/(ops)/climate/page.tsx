"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { Button, inputCls, Notice, PageHeader, Panel } from "@/components/ui";
import WeatherCard from "@/components/WeatherCard";
import { fetcher } from "@/lib/api";

interface Ext { date: string; value: number }
interface Summary {
  days: number; from: string | null; to: string | null; temp_mean_c: number | null; tmax_mean_c: number | null; tmin_mean_c: number | null;
  hottest: Ext | null; coldest: Ext | null; precip_total_mm: number | null; rain_days: number; wettest: Ext | null; snow_total_cm: number;
  strongest_gust: Ext | null; humidity_mean_pct: number | null; hot_days_35c: number; frost_days: number; flags: string[];
}
interface Day {
  date: string; code: number | null; tmax_c: number | null; tmin_c: number | null; tmean_c: number | null; feels_max_c: number | null;
  precip_mm: number | null; snow_cm: number | null; precip_hours: number | null; wind_max_kmh: number | null; gust_max_kmh: number | null;
  wind_dir_deg: number | null; humidity_pct: number | null; uv_max: number | null;
}
interface PlaceMonth {
  lat: number; lon: number; elevation_m: number | null; timezone: string; today: string; days: Day[];
  past_30d: Summary; next_16d: Summary; same_period_last_year: Summary | null; source: string;
}
interface City { name: string; country: string; region: string; lat: number; lon: number; past_30d: Summary; next_7d: Summary }
interface Place { name: string; lat: number; lon: number }

const FLAG: Record<string, [string, string]> = {
  heat: ["🔥 Heat", "bg-orange-500/20 text-orange-200"], heavy_rain: ["🌧 Heavy rain", "bg-sky-500/20 text-sky-200"],
  storm_wind: ["💨 Storm wind", "bg-violet-500/20 text-violet-200"], severe_cold: ["❄ Severe cold", "bg-cyan-500/20 text-cyan-100"],
  snow: ["🌨 Snow", "bg-slate-300/20 text-slate-100"], dry_spell: ["☀ Dry spell", "bg-amber-500/20 text-amber-200"],
};
const REGIONS = ["All", "Asia", "Europe", "Africa", "North America", "South America", "Oceania"];
const SORTS: Record<string, [string, (c: City) => number]> = {
  flags: ["Most alerts", (c) => c.past_30d.flags.length * 10 + c.next_7d.flags.length],
  rain: ["Wettest", (c) => c.past_30d.precip_total_mm ?? -1],
  hot: ["Hottest", (c) => c.past_30d.hottest?.value ?? -99],
  cold: ["Coldest", (c) => -(c.past_30d.coldest?.value ?? 99)],
  wind: ["Windiest", (c) => c.past_30d.strongest_gust?.value ?? -1],
  dry: ["Driest", (c) => -(c.past_30d.precip_total_mm ?? 9999)],
};

const n = (v: number | null | undefined, d = 0, u = "") => (v == null ? "—" : `${v.toFixed(d)}${u}`);
const day = (s: string | null | undefined) => (s ? new Date(`${s}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—");

function sky(code: number | null): string {
  if (code == null) return "—";
  if (code === 0) return "☀ Clear";
  if (code <= 2) return "🌤 Partly cloudy";
  if (code === 3) return "☁ Overcast";
  if (code <= 48) return "🌫 Fog";
  if (code <= 57) return "🌦 Drizzle";
  if (code <= 67) return "🌧 Rain";
  if (code <= 77) return "🌨 Snow";
  if (code <= 82) return "🌦 Showers";
  if (code <= 86) return "🌨 Snow showers";
  return "⛈ Thunderstorm";
}

function Flags({ flags, empty = "" }: { flags: string[]; empty?: string }) {
  if (!flags.length) return <span className="text-xs text-slate-500">{empty}</span>;
  return <span className="flex flex-wrap gap-1">{flags.map((f) => <span key={f} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${FLAG[f]?.[1] ?? "bg-white/10"}`}>{FLAG[f]?.[0] ?? f}</span>)}</span>;
}

export default function ClimatePage() {
  return <Suspense fallback={null}><Climate /></Suspense>;
}

function Climate() {
  const params = useSearchParams();
  const router = useRouter();
  const lat = Number(params.get("lat")), lon = Number(params.get("lon"));
  const place: Place = params.get("lat") && Number.isFinite(lat) && Number.isFinite(lon)
    ? { name: params.get("name") || `${lat.toFixed(2)}°, ${lon.toFixed(2)}°`, lat, lon }
    : { name: "Kathmandu, Nepal", lat: 27.71, lon: 85.32 };
  const detail = useRef<HTMLDivElement>(null);
  const [date, setDate] = useState<string | null>(null);

  const select = (p: Place, scroll = true) => {
    router.replace(`/climate?lat=${p.lat.toFixed(3)}&lon=${p.lon.toFixed(3)}&name=${encodeURIComponent(p.name)}`, { scroll: false });
    if (scroll) setTimeout(() => detail.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  return (
    <div className="space-y-4">
      <PageHeader title="30-day weather" subtitle="Any place in the world: the last 30 days, the next 16 days and the same 30 days last year. Plus a world overview of major cities." />
      <PlaceSearch onSelect={select} />
      <div ref={detail} className="scroll-mt-4 space-y-4"><WeatherCard lat={place.lat} lon={place.lon} date={date} onDate={setDate} title={place.name} /><PlaceDetail place={place} /></div>
      <WorldOverview onSelect={select} selected={place} />
    </div>
  );
}

function PlaceSearch({ onSelect }: { onSelect: (p: Place) => void }) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [geoError, setGeoError] = useState<string | null>(null);
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 350); return () => clearTimeout(t); }, [q]);
  const { data, isLoading } = useSWR<{ matches: { name: string; admin1: string | null; country: string | null; lat: number; lon: number }[] }>(
    debounced.length >= 2 ? `/api/v1/geocode?q=${encodeURIComponent(debounced)}` : null, fetcher);

  function myLocation() {
    setGeoError(null);
    if (!navigator.geolocation) { setGeoError("Location is not available in this browser."); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => onSelect({ name: "My location", lat: p.coords.latitude, lon: p.coords.longitude }),
      () => setGeoError("Location permission was denied."), { timeout: 10_000 });
  }

  return (
    <div className="relative max-w-xl">
      <div className="flex gap-2">
        <input className={inputCls} placeholder="Search any city or place in the world, e.g. Lagos, Pokhara, Chicago…" value={q}
               onChange={(e) => setQ(e.target.value)} aria-label="Search a place" />
        <Button onClick={myLocation}>📍 My location</Button>
      </div>
      {geoError && <p className="mt-1 text-xs text-red-300">{geoError}</p>}
      {debounced.length >= 2 && q && (
        <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-white/10 bg-[#0b1f26] text-sm shadow-xl">
          {isLoading && <li className="px-3 py-2 text-slate-400">Searching…</li>}
          {data?.matches.length === 0 && <li className="px-3 py-2 text-slate-400">No place found.</li>}
          {data?.matches.map((m) => {
            const name = [m.name, m.admin1, m.country].filter(Boolean).join(", ");
            return (
              <li key={`${m.lat},${m.lon}`}>
                <button className="w-full px-3 py-2 text-left hover:bg-white/10" onClick={() => { onSelect({ name, lat: m.lat, lon: m.lon }); setQ(""); }}>
                  {name} <span className="text-xs text-slate-500">{m.lat.toFixed(2)}°, {m.lon.toFixed(2)}°</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function PlaceDetail({ place }: { place: Place }) {
  const { data, error, isLoading } = useSWR<PlaceMonth>(`/api/v1/weather/month?lat=${place.lat.toFixed(3)}&lon=${place.lon.toFixed(3)}`, fetcher);
  const [showTable, setShowTable] = useState(false);
  if (error) return <Notice kind="error">Could not load weather for {place.name}: {(error as Error).message}</Notice>;
  if (isLoading || !data) return <Panel title={place.name}><p className="py-10 text-center text-sm text-slate-400">Loading 30 days of weather…</p></Panel>;
  const p = data.past_30d, f = data.next_16d, ly = data.same_period_last_year;
  const rainDiff = ly?.precip_total_mm != null && p.precip_total_mm != null ? p.precip_total_mm - ly.precip_total_mm : null;
  const tempDiff = ly?.tmax_mean_c != null && p.tmax_mean_c != null ? p.tmax_mean_c - ly.tmax_mean_c : null;

  return (
    <Panel title={`📍 ${place.name}`} note={`${data.lat.toFixed(2)}°, ${data.lon.toFixed(2)}° · ${data.elevation_m != null ? `${Math.round(data.elevation_m)} m` : ""} · ${data.timezone}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-400">Last 30 days:</span><Flags flags={p.flags} empty="nothing unusual" />
        <span className="ml-3 text-slate-400">Next 16 days:</span><Flags flags={f.flags} empty="nothing unusual" />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="text-left text-xs text-slate-400">
            <tr><th className="py-1 font-normal"></th><th className="font-normal">Last 30 days<br /><span className="text-[10px]">{day(p.from)} – {day(p.to)}</span></th>
              <th className="font-normal">Next 16 days (forecast)<br /><span className="text-[10px]">{day(f.from)} – {day(f.to)}</span></th>
              <th className="font-normal">Same 30 days last year<br /><span className="text-[10px]">{ly ? `${day(ly.from)} – ${day(ly.to)} ${ly.from?.slice(0, 4)}` : "not available"}</span></th></tr>
          </thead>
          <tbody className="tabular-nums [&_td]:border-t [&_td]:border-white/5 [&_td]:py-1.5">
            <Row label="🌧 Total rain" a={n(p.precip_total_mm, 0, " mm")} b={n(f.precip_total_mm, 0, " mm")} c={n(ly?.precip_total_mm, 0, " mm")}
                 note={rainDiff != null ? `${rainDiff >= 0 ? "+" : ""}${rainDiff.toFixed(0)} mm vs last year` : undefined} />
            <Row label="Rain days (≥1 mm)" a={`${p.rain_days}`} b={`${f.rain_days}`} c={ly ? `${ly.rain_days}` : "—"} />
            <Row label="Wettest day" a={p.wettest ? `${n(p.wettest.value, 0, " mm")} · ${day(p.wettest.date)}` : "—"} b={f.wettest ? `${n(f.wettest.value, 0, " mm")} · ${day(f.wettest.date)}` : "—"}
                 c={ly?.wettest ? `${n(ly.wettest.value, 0, " mm")} · ${day(ly.wettest.date)}` : "—"} />
            <Row label="🌡 Average high / low" a={`${n(p.tmax_mean_c, 1, "°")} / ${n(p.tmin_mean_c, 1, "°")}`} b={`${n(f.tmax_mean_c, 1, "°")} / ${n(f.tmin_mean_c, 1, "°")}`}
                 c={ly ? `${n(ly.tmax_mean_c, 1, "°")} / ${n(ly.tmin_mean_c, 1, "°")}` : "—"}
                 note={tempDiff != null ? `${tempDiff >= 0 ? "+" : ""}${tempDiff.toFixed(1)}° highs vs last year` : undefined} />
            <Row label="Hottest day" a={p.hottest ? `${n(p.hottest.value, 1, "°C")} · ${day(p.hottest.date)}` : "—"} b={f.hottest ? `${n(f.hottest.value, 1, "°C")} · ${day(f.hottest.date)}` : "—"}
                 c={ly?.hottest ? `${n(ly.hottest.value, 1, "°C")} · ${day(ly.hottest.date)}` : "—"} />
            <Row label="Coldest night" a={p.coldest ? `${n(p.coldest.value, 1, "°C")} · ${day(p.coldest.date)}` : "—"} b={f.coldest ? `${n(f.coldest.value, 1, "°C")} · ${day(f.coldest.date)}` : "—"}
                 c={ly?.coldest ? `${n(ly.coldest.value, 1, "°C")} · ${day(ly.coldest.date)}` : "—"} />
            <Row label="Days ≥ 35 °C / frost nights" a={`${p.hot_days_35c} / ${p.frost_days}`} b={`${f.hot_days_35c} / ${f.frost_days}`} c={ly ? `${ly.hot_days_35c} / ${ly.frost_days}` : "—"} />
            <Row label="💨 Strongest gust" a={p.strongest_gust ? `${n(p.strongest_gust.value, 0, " km/h")} · ${day(p.strongest_gust.date)}` : "—"}
                 b={f.strongest_gust ? `${n(f.strongest_gust.value, 0, " km/h")} · ${day(f.strongest_gust.date)}` : "—"}
                 c={ly?.strongest_gust ? `${n(ly.strongest_gust.value, 0, " km/h")} · ${day(ly.strongest_gust.date)}` : "—"} />
            <Row label="💧 Average humidity" a={n(p.humidity_mean_pct, 0, "%")} b={n(f.humidity_mean_pct, 0, "%")} c={n(ly?.humidity_mean_pct, 0, "%")} />
            {(p.snow_total_cm > 0 || f.snow_total_cm > 0) && <Row label="🌨 Snowfall" a={n(p.snow_total_cm, 0, " cm")} b={n(f.snow_total_cm, 0, " cm")} c={n(ly?.snow_total_cm, 0, " cm")} />}
          </tbody>
        </table>
      </div>

      <div className="mt-4"><MonthChart days={data.days} today={data.today} /></div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-slate-500">{data.source} Flags use indicative thresholds (e.g. heat: a day ≥ 40 °C or 3+ days ≥ 35 °C; heavy rain: a day ≥ 50 mm).</p>
        <Button variant="ghost" onClick={() => setShowTable(!showTable)}>{showTable ? "Hide" : "Show"} day-by-day table</Button>
      </div>
      {showTable && (
        <div className="mt-2 max-h-[420px] overflow-auto">
          <table className="w-full min-w-[720px] text-xs tabular-nums">
            <thead className="sticky top-0 bg-[#0b1a20] text-left text-slate-400">
              <tr>{["Date", "Sky", "High", "Low", "Feels max", "Rain", "Rain hours", "Snow", "Wind max", "Gust", "Humidity", "UV"].map((h) => <th key={h} className="px-1 py-1 font-normal">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.days.map((d) => (
                <tr key={d.date} className={`border-t border-white/5 ${d.date === data.today ? "bg-sky-500/15" : d.date > data.today ? "text-slate-400" : ""}`}>
                  <td className="px-1 py-1">{day(d.date)}{d.date === data.today ? " (today)" : d.date > data.today ? " ·f" : ""}</td>
                  <td className="px-1">{sky(d.code)}</td><td className="px-1">{n(d.tmax_c, 1, "°")}</td><td className="px-1">{n(d.tmin_c, 1, "°")}</td>
                  <td className="px-1">{n(d.feels_max_c, 1, "°")}</td><td className="px-1">{n(d.precip_mm, 1, " mm")}</td><td className="px-1">{n(d.precip_hours, 0, " h")}</td>
                  <td className="px-1">{n(d.snow_cm, 1, " cm")}</td><td className="px-1">{n(d.wind_max_kmh, 0, " km/h")}</td><td className="px-1">{n(d.gust_max_kmh, 0, " km/h")}</td>
                  <td className="px-1">{n(d.humidity_pct, 0, "%")}</td><td className="px-1">{n(d.uv_max, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-slate-500">·f = forecast</p>
        </div>
      )}
    </Panel>
  );
}

function Row({ label, a, b, c, note }: { label: string; a: string; b: string; c: string; note?: string }) {
  return (
    <tr>
      <td className="pr-3 text-slate-300">{label}</td>
      <td className="pr-3 font-medium">{a}{note && <div className="text-[10px] font-normal text-slate-400">{note}</div>}</td>
      <td className="pr-3 text-slate-300">{b}</td>
      <td className="text-slate-400">{c}</td>
    </tr>
  );
}

/** Daily highs and lows (lines) with rain (bars); the forecast part is dashed and shaded. */
function MonthChart({ days, today }: { days: Day[]; today: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 900, H = 260, padL = 40, padR = 44, padT = 14, padB = 28;
  const temps = days.flatMap((d) => [d.tmax_c, d.tmin_c]).filter((v): v is number => v != null);
  if (temps.length < 4) return <p className="py-8 text-center text-sm text-slate-400">Not enough data to draw a chart.</p>;
  let lo = Math.min(...temps), hi = Math.max(...temps);
  const pad = (hi - lo || 4) * 0.15; lo = Math.floor(lo - pad); hi = Math.ceil(hi + pad);
  const rainMax = Math.max(10, ...days.map((d) => d.precip_mm ?? 0));
  const step = (W - padL - padR) / days.length;
  const x = (i: number) => padL + step * (i + 0.5);
  const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const yr = (mm: number) => (mm / rainMax) * (H - padT - padB) * 0.6;
  const ti = days.findIndex((d) => d.date === today);
  const line = (key: "tmax_c" | "tmin_c", from: number, to: number) => days.slice(from, to + 1)
    .map((d, j) => (d[key] == null ? "" : `${j && days[from + j - 1]?.[key] != null ? "L" : "M"}${x(from + j).toFixed(1)},${y(d[key] as number).toFixed(1)}`)).join(" ");
  const split = ti >= 0 ? ti : days.length - 1;
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const h = hover != null ? days[hover] : null;

  return (
    <div className="relative">
      <div className="mb-1 flex flex-wrap gap-4 text-[11px] text-slate-400">
        <span><span className="mr-1 inline-block h-0.5 w-4 bg-red-400 align-middle" />Daily high</span>
        <span><span className="mr-1 inline-block h-0.5 w-4 bg-sky-300 align-middle" />Daily low</span>
        <span><span className="mr-1 inline-block h-2 w-3 bg-blue-500/60 align-middle" />Rain (mm, right axis)</span>
        <span>Dashed / shaded = forecast</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Daily temperature and rain for 47 days"
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
             const i = Math.floor((((e.clientX - r.left) / r.width) * W - padL) / step);
             setHover(i >= 0 && i < days.length ? i : null);
           }}>
        {ti >= 0 && <rect x={x(ti) - step / 2} y={padT} width={W - padR - (x(ti) - step / 2)} height={H - padT - padB} fill="rgba(148,163,184,0.07)" />}
        {ticks.map((v) => (
          <g key={v}>
            <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="rgba(255,255,255,0.07)" />
            <text x={padL - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#94a3b8">{v.toFixed(0)}°</text>
          </g>
        ))}
        <text x={W - padR + 6} y={H - padB} fontSize="10" fill="#60a5fa">0</text>
        <text x={W - padR + 6} y={H - padB - yr(rainMax) + 4} fontSize="10" fill="#60a5fa">{rainMax.toFixed(0)} mm</text>
        {days.map((d, i) => (d.precip_mm ? (
          <rect key={d.date} x={x(i) - step * 0.35} width={step * 0.7} y={H - padB - yr(d.precip_mm)} height={yr(d.precip_mm)}
                fill={i >= split && ti >= 0 ? "rgba(59,130,246,0.35)" : "rgba(59,130,246,0.65)"} />
        ) : null))}
        <path d={line("tmax_c", 0, split)} fill="none" stroke="#f87171" strokeWidth="2" />
        <path d={line("tmin_c", 0, split)} fill="none" stroke="#7dd3fc" strokeWidth="2" />
        {ti >= 0 && <>
          <path d={line("tmax_c", split, days.length - 1)} fill="none" stroke="#f87171" strokeWidth="2" strokeDasharray="5 4" />
          <path d={line("tmin_c", split, days.length - 1)} fill="none" stroke="#7dd3fc" strokeWidth="2" strokeDasharray="5 4" />
          <line x1={x(ti)} x2={x(ti)} y1={padT} y2={H - padB} stroke="#e2e8f0" strokeDasharray="2 3" />
          <text x={x(ti) + 4} y={padT + 10} fontSize="11" fill="#e2e8f0">today</text>
        </>}
        {days.map((d, i) => (i % 7 === 0 ? <text key={d.date} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="#94a3b8">{day(d.date)}</text> : null))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke="rgba(255,255,255,0.35)" />}
      </svg>
      {h && (
        <div className="pointer-events-none absolute top-6 rounded-md border border-white/10 bg-[#0b1f26]/95 px-2.5 py-1.5 text-xs shadow-lg"
             style={{ left: `${Math.min(75, (x(hover!) / W) * 100)}%` }}>
          <div className="font-semibold">{day(h.date)}{h.date === today ? " · today" : h.date > today ? " · forecast" : ""}</div>
          <div>{sky(h.code)}</div>
          <div>High {n(h.tmax_c, 1, "°")} · Low {n(h.tmin_c, 1, "°")}</div>
          <div>Rain {n(h.precip_mm, 1, " mm")} · Gust {n(h.gust_max_kmh, 0, " km/h")}</div>
          <div>Humidity {n(h.humidity_pct, 0, "%")}</div>
        </div>
      )}
    </div>
  );
}

function WorldOverview({ onSelect, selected }: { onSelect: (p: Place) => void; selected: Place }) {
  const { data, error, isLoading } = useSWR<{ generated_at: string; cities: City[]; source: string }>("/api/v1/weather/world-month", fetcher,
    { refreshInterval: 3 * 3600_000 });
  const [region, setRegion] = useState("All");
  const [sort, setSort] = useState("flags");
  const rows = useMemo(() => (data?.cities ?? []).filter((c) => region === "All" || c.region === region)
    .sort((a, b) => SORTS[sort][1](b) - SORTS[sort][1](a)), [data, region, sort]);
  const flagged = (data?.cities ?? []).filter((c) => c.past_30d.flags.length || c.next_7d.flags.length).length;

  return (
    <Panel title="🌍 World: last 30 days and next 7 days" note={data ? `${data.cities.length} cities · ${flagged} with alerts · updated ${new Date(data.generated_at).toLocaleString()}` : undefined}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {REGIONS.map((r) => (
          <button key={r} onClick={() => setRegion(r)} className={`rounded-full px-2.5 py-1 text-xs ${region === r ? "bg-sky-500/25 text-sky-100" : "bg-white/5 text-slate-300 hover:bg-white/10"}`}>{r}</button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-xs text-slate-400">Sort
          <select className={`${inputCls} w-auto`} value={sort} onChange={(e) => setSort(e.target.value)}>
            {Object.entries(SORTS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </label>
      </div>
      {error && <Notice kind="error">World overview unavailable: {(error as Error).message}</Notice>}
      {isLoading && <p className="py-6 text-center text-sm text-slate-400">Loading world cities…</p>}
      {data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm tabular-nums">
            <thead className="text-left text-xs text-slate-400">
              <tr>
                <th className="py-1 font-normal">City</th><th className="font-normal">Rain 30 d</th><th className="font-normal">Rain days</th>
                <th className="font-normal">Avg high / low</th><th className="font-normal">Hottest</th><th className="font-normal">Coldest</th>
                <th className="font-normal">Max gust</th><th className="font-normal">Last 30 days</th><th className="font-normal">Next 7 days</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const p = c.past_30d;
                const active = Math.abs(selected.lat - c.lat) < 0.05 && Math.abs(selected.lon - c.lon) < 0.05;
                return (
                  <tr key={c.name} onClick={() => onSelect({ name: `${c.name}, ${c.country}`, lat: c.lat, lon: c.lon })}
                      className={`cursor-pointer border-t border-white/5 hover:bg-white/5 ${active ? "bg-sky-500/10" : ""}`}>
                    <td className="py-1.5 pr-2"><span className="font-medium">{c.name}</span> <span className="text-xs text-slate-500">{c.country}</span></td>
                    <td className="pr-2">{n(p.precip_total_mm, 0, " mm")}</td>
                    <td className="pr-2">{p.rain_days}</td>
                    <td className="pr-2">{n(p.tmax_mean_c, 0, "°")} / {n(p.tmin_mean_c, 0, "°")}</td>
                    <td className="pr-2">{n(p.hottest?.value, 1, "°")}</td>
                    <td className="pr-2">{n(p.coldest?.value, 1, "°")}</td>
                    <td className="pr-2">{n(p.strongest_gust?.value, 0, " km/h")}</td>
                    <td className="pr-2"><Flags flags={p.flags} empty="—" /></td>
                    <td><Flags flags={c.next_7d.flags} empty="—" /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-slate-500">Click a city for its full 30-day view. {data.source}. Search above for any other place.</p>
        </div>
      )}
    </Panel>
  );
}

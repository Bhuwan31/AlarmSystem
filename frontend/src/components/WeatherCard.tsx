"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { fetcher } from "@/lib/api";

interface Hour {
  t: string; temp_c: number | null; feels_c: number | null; humidity_pct: number | null; precip_prob: number | null; precip_mm: number | null;
  code: number | null; wind_kmh: number | null; wind_dir_deg: number | null; gust_kmh: number | null; is_day: number | null;
}
interface Day {
  date: string; code: number | null; tmax_c: number | null; tmin_c: number | null; precip_prob: number | null; precip_mm: number | null;
  wind_max_kmh: number | null; wind_dir_deg: number | null; sunrise: string | null; sunset: string | null; uv_max: number | null;
}
interface DayCard {
  lat: number; lon: number; name: string | null; timezone: string; today: string; start: string; end: string; min_date: string; max_date: string;
  current: { time: string; temp_c: number | null; feels_c: number | null; humidity_pct: number | null; precip_mm: number | null; code: number | null;
    wind_kmh: number | null; wind_dir_deg: number | null; is_day: number | null };
  days: Day[]; hours: Hour[]; source: string;
}
type Tab = "temp" | "precip" | "wind";

/** WMO weather code → words and icon kind. */
export function describe(code: number | null, day = true): [string, IconKind] {
  if (code == null) return ["—", "cloud"];
  if (code === 0) return [day ? "Sunny" : "Clear", day ? "sun" : "moon"];
  if (code === 1) return [day ? "Mostly sunny" : "Mostly clear", day ? "sun" : "moon"];
  if (code === 2) return ["Partly cloudy", day ? "partly" : "partly-night"];
  if (code === 3) return ["Cloudy", "cloud"];
  if (code <= 48) return ["Fog", "fog"];
  if (code <= 57) return [code >= 56 ? "Freezing drizzle" : "Drizzle", "drizzle"];
  if (code <= 67) return [code === 65 ? "Heavy rain" : code >= 66 ? "Freezing rain" : "Rain", "rain"];
  if (code <= 77) return [code === 75 ? "Heavy snow" : "Snow", "snow"];
  if (code <= 82) return [code === 82 ? "Violent showers" : "Showers", day ? "showers" : "rain"];
  if (code <= 86) return ["Snow showers", "snow"];
  return [code >= 96 ? "Thunderstorm with hail" : "Thunderstorm", "thunder"];
}

const dayName = (d: string, style: "short" | "long" = "short") => new Date(`${d}T12:00:00Z`).toLocaleDateString("en", { weekday: style, timeZone: "UTC" });
const hourOf = (t: string) => Number(t.slice(11, 13));
const clock = (h: number, m = 0) => `${h % 12 || 12}${m ? `:${String(m).padStart(2, "0")}` : ":00"} ${h < 12 ? "AM" : "PM"}`;
const shortClock = (h: number) => `${h % 12 || 12} ${h < 12 ? "AM" : "PM"}`;
/** Local date as YYYY-MM-DD, optionally `plus` days ahead. */
export const todayIso = (plus = 0) => { const d = new Date(Date.now() + plus * 86400000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const addDays = (d: string, n: number) => new Date(Date.parse(`${d}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);

/** Google-style weather card: now, an hourly temperature / rain / wind chart and 8 days. `date` = first day shown. */
export default function WeatherCard({ lat, lon, date, onDate, title }: {
  lat: number; lon: number; date: string | null; onDate: (d: string | null) => void; title?: string;
}) {
  const q = `/api/v1/weather/day?lat=${lat.toFixed(3)}&lon=${lon.toFixed(3)}${date ? `&date=${date}` : ""}`;
  const { data, error, isLoading } = useSWR<DayCard>(q, fetcher, { keepPreviousData: true });
  const [sel, setSel] = useState(0);
  const [selKey, setSelKey] = useState(q);
  const [tab, setTab] = useState<Tab>("temp");
  const [hover, setHover] = useState<number | null>(null);
  const [unit, setUnit] = useState<"C" | "F">("C");
  if (selKey !== q) { setSelKey(q); setSel(0); setHover(null); }   // new place or date → back to the first day

  const t = (c: number | null | undefined) => (c == null ? null : unit === "C" ? c : c * 9 / 5 + 32);
  const deg = (c: number | null | undefined) => { const v = t(c); return v == null ? "—" : `${Math.round(v)}°`; };

  if (!data) {
    return <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">{error ? "Could not load the weather card." : "Loading weather…"}</div>;
  }

  const day = data.days[Math.min(sel, data.days.length - 1)];
  const isToday = day?.date === data.today;
  const nowHour = hourOf(data.current.time ?? "T00");
  // 24 hours: from the current hour when looking at today (like a phone's weather), otherwise midnight to midnight.
  const firstIdx = Math.max(0, data.hours.findIndex((h) => h.t.startsWith(day?.date ?? "") && (!isToday || hourOf(h.t) >= nowHour)));
  const hours = data.hours.slice(firstIdx, firstIdx + 24);
  const focusHour = hover != null ? hours[hover] : isToday ? null : hours.find((h) => hourOf(h.t) === 14) ?? hours[12];

  const shown = focusHour
    ? { temp: focusHour.temp_c, code: focusHour.code, isDay: focusHour.is_day !== 0, prob: focusHour.precip_prob, mm: focusHour.precip_mm,
        hum: focusHour.humidity_pct, wind: focusHour.wind_kmh, dir: focusHour.wind_dir_deg, when: `${dayName(focusHour.t.slice(0, 10), "long")} ${clock(hourOf(focusHour.t))}` }
    : { temp: data.current.temp_c, code: data.current.code, isDay: data.current.is_day !== 0, prob: hours[0]?.precip_prob ?? null, mm: data.current.precip_mm,
        hum: data.current.humidity_pct, wind: data.current.wind_kmh, dir: data.current.wind_dir_deg,
        when: `${dayName(data.today, "long")} ${clock(nowHour, Number((data.current.time ?? "").slice(14, 16)) || 0)}` };
  const [words, icon] = describe(shown.code, shown.isDay);
  const placeName = title ?? data.name ?? `${data.lat.toFixed(2)}°, ${data.lon.toFixed(2)}°`;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 text-slate-800 shadow-sm sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5 text-sm">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[#4285f4]" />
          <span className="truncate font-semibold" title={placeName}>{placeName}</span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <label className="sr-only" htmlFor={`wx-date-${lat}-${lon}`}>Start date</label>
          <input id={`wx-date-${lat}-${lon}`} type="date" value={date ?? data.start} min={data.min_date} max={addDays(data.max_date, -7)}
            onChange={(e) => onDate(e.target.value || null)} className="rounded-md border border-slate-300 bg-white px-1.5 py-1 text-slate-800" />
          {date && date !== data.today && <button onClick={() => onDate(null)} className="rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-100">Today</button>}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <WxIcon kind={icon} size={64} />
          <div className="flex items-start">
            <span className="text-5xl font-normal leading-none tabular-nums">{t(shown.temp) == null ? "—" : Math.round(t(shown.temp)!)}</span>
            <span className="ml-1 flex items-center gap-1 text-sm">
              {(["C", "F"] as const).map((u, i) => (
                <span key={u} className="flex items-center gap-1">
                  {i > 0 && <span className="h-4 w-px bg-slate-300" />}
                  <button onClick={() => setUnit(u)} className={unit === u ? "font-semibold text-slate-900" : "text-slate-500 hover:underline"}>°{u}</button>
                </span>
              ))}
            </span>
          </div>
          <div className="text-xs leading-5 text-slate-500">
            <div>Precipitation: {shown.prob != null ? `${shown.prob}%` : `${shown.mm ?? 0} mm`}</div>
            <div>Humidity: {shown.hum != null ? `${Math.round(shown.hum)}%` : "—"}</div>
            <div>Wind: {shown.wind != null ? `${Math.round(shown.wind)} km/h` : "—"}{shown.dir != null && <Arrow deg={shown.dir} size={11} className="ml-1 inline" />}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl">Weather</div>
          <div className="text-sm text-slate-500">{shown.when}</div>
          <div className="text-sm text-slate-500">{words}</div>
        </div>
      </div>

      <div className="mt-3 flex gap-4 border-b border-slate-200 text-sm" role="tablist">
        {([["temp", "Temperature"], ["precip", "Precipitation"], ["wind", "Wind"]] as [Tab, string][]).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`-mb-px border-b-[3px] pb-1.5 ${tab === k ? "border-[#f9ab00] font-medium text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"}`}>{label}</button>
        ))}
      </div>

      <HourChart hours={hours} tab={tab} unit={unit} toUnit={t} hover={hover} onHover={setHover} />

      <div className="-mx-1 mt-2 overflow-x-auto">
        <div className="grid min-w-[360px] grid-cols-8 gap-0.5 px-1">
          {data.days.map((d, i) => {
            const [w, k] = describe(d.code);
            return (
              <button key={d.date} onClick={() => { setSel(i); setHover(null); }} title={`${d.date}: ${w}`}
                className={`flex flex-col items-center rounded-lg px-0.5 py-1.5 text-sm ${i === sel ? "bg-slate-100" : "hover:bg-slate-50"}`}>
                <span className={d.date === data.today ? "font-semibold" : ""}>{dayName(d.date)}</span>
                <span className="text-[10px] text-slate-400">{d.date.slice(5).replace("-", "/")}</span>
                <WxIcon kind={k} size={34} />
                <span className="whitespace-nowrap text-xs"><span className="text-slate-800">{deg(d.tmax_c)}</span> <span className="text-slate-400">{deg(d.tmin_c)}</span></span>
              </button>
            );
          })}
        </div>
      </div>

      {day && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
          <span>{dayName(day.date, "long")} {day.date}</span>
          <span>Rain {day.precip_mm ?? 0} mm{day.precip_prob != null ? ` · chance ${day.precip_prob}%` : ""}</span>
          <span>Max wind {Math.round(day.wind_max_kmh ?? 0)} km/h</span>
          {day.uv_max != null && <span>UV {day.uv_max.toFixed(0)}</span>}
          {day.sunrise && <span>☀ {day.sunrise.slice(11)} – {day.sunset?.slice(11)}</span>}
          {isLoading && <span className="text-sky-600">updating…</span>}
        </div>
      )}
      <p className="mt-1 text-[10px] text-slate-400">{data.source}. Local time ({data.timezone}). {data.start < data.today ? "Past days are model reanalysis, not station records." : ""}</p>
    </div>
  );
}

function HourChart({ hours, tab, unit, toUnit, hover, onHover }: {
  hours: Hour[]; tab: Tab; unit: "C" | "F"; toUnit: (c: number | null) => number | null; hover: number | null; onHover: (i: number | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(480);   // drawn at the real pixel width so labels keep a readable size
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = 128, top = 26, base = 100, n = hours.length;
  const every = W < 700 ? 3 : 2;
  if (!n) return <div className="py-8 text-center text-xs text-slate-400">No hourly data for this day.</div>;
  const x = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W);
  const label = (i: number) => i % every === 0;

  let body: React.ReactNode;
  if (tab === "temp") {
    const v = hours.map((h) => toUnit(h.temp_c) ?? 0);
    const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1;
    const y = (val: number) => base - 8 - ((val - lo) / span) * (base - top - 14);
    const line = v.map((val, i) => `${x(i)},${y(val)}`).join(" ");
    body = (
      <>
        <polygon points={`0,${base} ${line} ${W},${base}`} fill="#fef7e0" />
        <polyline points={line} fill="none" stroke="#f9ab00" strokeWidth="2.5" strokeLinejoin="round" />
        {v.map((val, i) => label(i) && <text key={i} x={Math.min(Math.max(x(i), 10), W - 10)} y={y(val) - 7} textAnchor="middle" fontSize="12"
          fill={i === 0 ? "#3c4043" : "#9aa0a6"} fontWeight={i === 0 ? 700 : 500}>{Math.round(val)}</text>)}
      </>
    );
  } else if (tab === "precip") {
    const useProb = hours.some((h) => h.precip_prob != null);
    const vals = hours.map((h) => (useProb ? h.precip_prob ?? 0 : h.precip_mm ?? 0));
    const max = useProb ? 100 : Math.max(1, ...vals);
    const bw = (W / n) * 0.7;
    body = (
      <>
        {vals.map((val, i) => {
          const h = (val / max) * (base - top - 4);
          return <rect key={i} x={x(i) - bw / 2} y={base - h} width={bw} height={Math.max(h, val > 0 ? 1.5 : 0)} fill="#8ab4f8" rx="1.5" />;
        })}
        {vals.map((val, i) => label(i) && <text key={`t${i}`} x={Math.min(Math.max(x(i), 12), W - 12)} y={base - (val / max) * (base - top - 4) - 5}
          textAnchor="middle" fontSize="11" fill="#5f6368">{useProb ? `${val}%` : `${val.toFixed(1)}`}</text>)}
        {!useProb && <text x={W - 2} y={12} textAnchor="end" fontSize="10" fill="#9aa0a6">mm per hour (no rain-chance data for this date)</text>}
      </>
    );
  } else {
    const max = Math.max(10, ...hours.map((h) => h.wind_kmh ?? 0));
    body = (
      <>
        {hours.map((h, i) => {
          if (!label(i) || h.wind_dir_deg == null) return null;
          const s = 12 + ((h.wind_kmh ?? 0) / max) * 14;
          const cx = Math.min(Math.max(x(i), 16), W - 16);
          return (
            <g key={i}>
              <g transform={`translate(${cx} ${(base + top) / 2 - 4}) rotate(${h.wind_dir_deg + 180}) translate(${-s / 2} ${-s / 2})`}>
                <path d={`M${s / 2} 0 L${s} ${s * 0.55} H${s * 0.62} V${s} H${s * 0.38} V${s * 0.55} H0 Z`} fill="#5f6368" />
              </g>
              <text x={cx} y={base - 2} textAnchor="middle" fontSize="11" fill="#5f6368">{Math.round(h.wind_kmh ?? 0)} km/h</text>
            </g>
          );
        })}
      </>
    );
  }

  return (
    <div ref={box} className="mt-2 w-full">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block" role="img" onMouseLeave={() => onHover(null)}
      aria-label={`${tab === "temp" ? `Temperature °${unit}` : tab === "precip" ? "Precipitation" : "Wind"} for 24 hours from ${hours[0].t.replace("T", " ")}`}>
      {body}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={top - 8} y2={base} stroke="#9aa0a6" strokeDasharray="3 3" />}
      {hours.map((h, i) => label(i) && (
        <text key={h.t} x={Math.min(Math.max(x(i), 14), W - 14)} y={H - 6} textAnchor="middle" fontSize="12" fill="#5f6368">{shortClock(hourOf(h.t))}</text>
      ))}
      {hours.map((h, i) => (
        <rect key={`h${h.t}`} x={x(i) - W / n / 2} y={0} width={W / n} height={H} fill="transparent"
          onMouseEnter={() => onHover(i)} onTouchStart={() => onHover(i)} />
      ))}
    </svg>
    </div>
  );
}

function Arrow({ deg, size, className }: { deg: number; size: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" className={className} style={{ transform: `rotate(${deg + 180}deg)` }} aria-label={`wind from ${Math.round(deg)}°`}>
      <path d="M8 1 L13 8 H9.5 V15 H6.5 V8 H3 Z" fill="currentColor" />
    </svg>
  );
}

type IconKind = "sun" | "moon" | "partly" | "partly-night" | "cloud" | "fog" | "drizzle" | "rain" | "showers" | "snow" | "thunder";

const SUN = "#fbbc04", SUN_EDGE = "#f29900", CLOUD = "#dadce0", CLOUD_DARK = "#bdc1c6", DROP = "#1a73e8";

function Sun({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  // Scalloped disc, like the familiar weather-app sun.
  const pts = Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2, rr = i % 2 ? r : r * 1.12;
    return `${cx + Math.cos(a) * rr},${cy + Math.sin(a) * rr}`;
  }).join(" ");
  return <><polygon points={pts} fill={SUN_EDGE} strokeLinejoin="round" stroke={SUN_EDGE} strokeWidth={r * 0.18} /><circle cx={cx} cy={cy} r={r * 0.92} fill={SUN} /></>;
}
const Cloud = ({ dx = 0, dy = 0, s = 1, fill = CLOUD }: { dx?: number; dy?: number; s?: number; fill?: string }) => (
  <path transform={`translate(${dx} ${dy}) scale(${s})`} fill={fill}
    d="M13 38h23a8 8 0 0 0 1-15.9A11 11 0 0 0 16 19a8.5 8.5 0 0 0-3 19z" />
);
const Moon = ({ cx, cy, r }: { cx: number; cy: number; r: number }) => (
  <path d={`M${cx + r * 0.3} ${cy - r} a${r} ${r} 0 1 0 ${r * 0.7} ${r * 1.55} a${r * 0.8} ${r * 0.8} 0 0 1 ${-r * 0.7} ${-r * 1.55}z`} fill="#aecbfa" stroke="#7baaf7" strokeWidth="1" />
);
const Drops = ({ n = 2, small = false }: { n?: number; small?: boolean }) => (
  <>{Array.from({ length: n }, (_, i) => (
    <path key={i} transform={`translate(${18 + i * 8 - (n - 2) * 4} ${36}) rotate(20)`} fill={DROP}
      d={small ? "M0 0 c1.6 2.6 2.4 3.8 2.4 4.8 a2.4 2.4 0 0 1 -4.8 0 c0 -1 .8 -2.2 2.4 -4.8z" : "M0 0 c2.4 3.6 3.4 5.4 3.4 6.8 a3.4 3.4 0 0 1 -6.8 0 c0 -1.4 1 -3.2 3.4 -6.8z"} />
  ))}</>
);

export function WxIcon({ kind, size = 40 }: { kind: IconKind; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" className="shrink-0">
      {kind === "sun" && <Sun cx={24} cy={24} r={15} />}
      {kind === "moon" && <Moon cx={22} cy={24} r={14} />}
      {(kind === "partly" || kind === "showers") && <><Sun cx={18} cy={17} r={10} /><Cloud dx={4} dy={2} /></>}
      {kind === "partly-night" && <><Moon cx={16} cy={16} r={9} /><Cloud dx={4} dy={2} /></>}
      {kind === "cloud" && <><Cloud dx={-6} dy={-6} s={0.8} fill={CLOUD_DARK} /><Cloud dx={0} dy={2} /></>}
      {kind === "fog" && <><Cloud dx={0} dy={-6} />{[34, 39, 44].map((y) => <rect key={y} x={8} y={y} width={32} height={2.6} rx={1.3} fill={CLOUD_DARK} />)}</>}
      {kind === "drizzle" && <><Cloud dx={0} dy={-6} fill={CLOUD_DARK} /><Drops n={3} small /></>}
      {kind === "rain" && <><Cloud dx={0} dy={-6} fill={CLOUD_DARK} /><Drops n={3} /></>}
      {kind === "showers" && <Drops n={2} />}
      {kind === "snow" && <><Cloud dx={0} dy={-6} />{[[17, 39], [25, 43], [33, 39]].map(([cx, cy]) => <text key={cx} x={cx} y={cy + 3} fontSize="10" textAnchor="middle" fill="#8ab4f8">✱</text>)}</>}
      {kind === "thunder" && <><Cloud dx={0} dy={-6} fill="#9aa0a6" /><path d="M25 30 l-6 9 h5 l-3 8 l9 -11 h-5 l3 -6z" fill={SUN} stroke={SUN_EDGE} strokeWidth="0.8" /></>}
    </svg>
  );
}

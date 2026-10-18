"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";
import useSWR from "swr";

import LineChart, { type Point } from "@/components/LineChart";
import { Button, Empty, LevelBadge, Notice, PageHeader, Panel, Stat } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { ago, fmt, LEVEL_COLOR } from "@/lib/colors";

interface Detail {
  station: { id: number; name: string; kind: string; source_code: string; basin: string | null; district: string | null; lat: number; lon: number;
             elevation_m: number | null; watch_level: number | null; warning_level: number | null; danger_level: number | null; meta: Record<string, unknown> };
  latest: { variable: string; value: number | null; unit: string; observed_at: string; quality: string; quality_reason: string | null }[];
  risk_history: { level: string; confidence: string; reasons: string[]; computed_at: string }[];
  warnings: { id: string; level: string; status: string; source: string; created_at: string }[];
  quality_events: { kind: string; detail: Record<string, unknown>; opened_at: string; closed_at: string | null }[];
  warning_index: number | null;
}

function Station() {
  const { id } = useParams<{ id: string }>();
  const [hours, setHours] = useState(48);
  const { data: d, error } = useSWR<Detail>(`/api/v1/stations/${id}`, fetcher, { refreshInterval: 60_000 });
  const isRain = d?.station.kind.endsWith("rain");
  const variable = isRain ? "rain_1h_mm" : "water_level_m";
  const { data: series } = useSWR<{ t: string; v: number | null }[]>(`/api/v1/stations/${id}/series?variable=${variable}&hours=${hours}`, fetcher, { refreshInterval: 60_000 });

  if (error) return <Notice kind="error">Station not found.</Notice>;
  if (!d) return <p className="text-sm text-slate-400">Loading…</p>;
  const s = d.station;
  const level = d.latest.find((l) => l.variable === "water_level_m");
  const rain24 = d.latest.find((l) => l.variable === "rain_24h_mm");
  const rain1 = d.latest.find((l) => l.variable === "rain_1h_mm");
  const risk = d.risk_history[0];
  const thresholds = [
    s.watch_level != null && { value: +s.watch_level.toFixed(2), label: "watch", color: LEVEL_COLOR.WATCH },
    s.warning_level != null && { value: s.warning_level, label: "warning", color: LEVEL_COLOR.WARNING },
    s.danger_level != null && { value: s.danger_level, label: "danger", color: LEVEL_COLOR.CRITICAL },
  ].filter(Boolean) as { value: number; label: string; color: string }[];

  return (
    <div className="space-y-4">
      <PageHeader title={s.name} subtitle={`${s.basin ?? "—"} basin · ${s.district ?? "—"} · ${s.lat.toFixed(3)}°, ${s.lon.toFixed(3)}° · source ${s.source_code}`}
                  actions={<Link href={isRain ? "/rain" : "/rivers"} className="text-sm text-sky-300 hover:underline">← All {isRain ? "rain gauges" : "rivers"}</Link>} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {isRain ? (
          <>
            <Stat label="Rain last hour" value={fmt(rain1?.value, 1, " mm")} sub={ago(rain1?.observed_at)} />
            <Stat label="Rain last 24 h" value={fmt(rain24?.value, 1, " mm")} sub={rain24?.quality} />
          </>
        ) : (
          <>
            <Stat label="Water level" value={fmt(level?.value, 2, " m")} sub={`${ago(level?.observed_at)} · ${level?.quality ?? "—"}`} />
            <Stat label="Warning / danger level" value={`${fmt(s.warning_level, 2)} / ${fmt(s.danger_level, 2)}`} sub={`watch at ${fmt(s.watch_level, 2, " m")}`} />
            <Stat label="Index to warning" value={fmt(d.warning_index, 2)} sub="1.0 = at warning level" />
            <Stat label="Risk now" value={risk ? <LevelBadge level={risk.level} /> : "—"} sub={risk ? `${risk.confidence} confidence · ${ago(risk.computed_at)}` : "not assessed yet"} />
          </>
        )}
      </div>

      {risk && !isRain && (
        <Panel title="Why this risk level">
          <ul className="list-inside list-disc text-sm text-slate-300">{risk.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </Panel>
      )}

      <Panel title={isRain ? "Rainfall per hour" : "Water level"} note={
        <span className="flex gap-1">{[24, 48, 168].map((h) => <Button key={h} variant={hours === h ? "primary" : "ghost"} className="!px-2 !py-0.5 text-xs" onClick={() => setHours(h)}>{h === 168 ? "7 d" : `${h} h`}</Button>)}</span>}>
        <LineChart points={(series ?? []) as Point[]} unit={isRain ? "mm" : "m"} thresholds={isRain ? [] : thresholds} color={isRain ? "#60a5fa" : "#38bdf8"} />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        {!isRain && (
          <Panel title="Risk history (48 h)" note={`${d.risk_history.length} assessments`}>
            <div className="flex h-8 overflow-hidden rounded" role="img" aria-label="Risk level over time, oldest left">
              {[...d.risk_history].reverse().map((r, i) => <div key={i} className="flex-1" title={`${new Date(r.computed_at).toLocaleString()}: ${r.level}`} style={{ background: LEVEL_COLOR[r.level as keyof typeof LEVEL_COLOR] ?? "#6c7a89" }} />)}
            </div>
            {!d.risk_history.length && <Empty>No assessments yet.</Empty>}
          </Panel>
        )}
        <Panel title="Warnings for this reach">
          {d.warnings.length ? (
            <ul className="space-y-1 text-sm">{d.warnings.map((w) => (
              <li key={w.id} className="flex items-center justify-between border-t border-white/5 py-1">
                <span><LevelBadge level={w.level} /> <span className="text-slate-300">{w.status}</span> <span className="text-xs text-slate-400">{w.source}</span></span>
                <span className="text-xs text-slate-400">{ago(w.created_at)}</span>
              </li>))}
            </ul>
          ) : <Empty>No warnings recorded.</Empty>}
        </Panel>
        <Panel title="Data quality events">
          {d.quality_events.length ? (
            <ul className="space-y-1 text-sm">{d.quality_events.map((e, i) => (
              <li key={i} className="flex justify-between border-t border-white/5 py-1"><span>{e.kind}</span>
                <span className="text-xs text-slate-400">{ago(e.opened_at)}{e.closed_at ? " · closed" : " · open"}</span></li>))}
            </ul>
          ) : <Empty>No data problems recorded.</Empty>}
        </Panel>
      </div>
    </div>
  );
}

export default function StationPage() {
  return <Suspense fallback={<p className="text-sm text-slate-400">Loading…</p>}><Station /></Suspense>;
}

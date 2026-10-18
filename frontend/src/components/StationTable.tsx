"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { FC, RiskLevel, StationProps } from "@/lib/api";
import { ago, fmt } from "@/lib/colors";
import { inputCls, LevelBadge } from "./ui";

const LEVELS: RiskLevel[] = ["CRITICAL", "WARNING", "WATCH", "NORMAL", "UNKNOWN"];
type SortKey = "name" | "index" | "value" | "rain" | "updated";

export default function StationTable({ data, kind, initialLevel }: { data?: FC<StationProps>; kind: "river" | "rain"; initialLevel?: string }) {
  const [q, setQ] = useState("");
  const [basin, setBasin] = useState("");
  const [levels, setLevels] = useState<RiskLevel[]>(initialLevel && LEVELS.includes(initialLevel as RiskLevel) ? [initialLevel as RiskLevel] : LEVELS);
  const [sort, setSort] = useState<SortKey>(kind === "river" ? "index" : "rain");
  const basins = useMemo(() => [...new Set((data?.features ?? []).map((f) => f.properties.basin).filter(Boolean))].sort() as string[], [data]);

  const rows = useMemo(() => {
    const list = (data?.features ?? []).map((f) => f.properties).filter((p) =>
      (!q || `${p.name} ${p.district ?? ""}`.toLowerCase().includes(q.toLowerCase())) &&
      (!basin || p.basin === basin) && (kind === "rain" || levels.includes(p.risk_level)));
    const key: Record<SortKey, (p: StationProps) => number | string> = {
      name: (p) => p.name, index: (p) => -(p.ratio_to_warning ?? -99), value: (p) => -(p.value ?? -9999),
      rain: (p) => -(p.rain_24h_mm ?? -1), updated: (p) => -(p.observed_at ? new Date(p.observed_at).getTime() : 0),
    };
    return list.sort((a, b) => (key[sort](a) < key[sort](b) ? -1 : key[sort](a) > key[sort](b) ? 1 : 0));
  }, [data, q, basin, levels, sort, kind]);

  const th = (k: SortKey, label: string, cls = "") => (
    <th className={`py-2 pr-2 ${cls}`}>
      <button onClick={() => setSort(k)} className={`hover:text-slate-200 ${sort === k ? "text-sky-300" : ""}`} aria-sort={sort === k ? "descending" : undefined}>
        {label}{sort === k ? " ↓" : ""}
      </button>
    </th>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input className={`${inputCls} max-w-xs`} placeholder="Search station or district…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" />
        <select className={`${inputCls} max-w-48`} value={basin} onChange={(e) => setBasin(e.target.value)} aria-label="Basin">
          <option value="">All basins</option>
          {basins.map((b) => <option key={b}>{b}</option>)}
        </select>
        {kind === "river" && (
          <div className="flex flex-wrap gap-1">
            {LEVELS.map((l) => {
              const on = levels.includes(l);
              return (
                <button key={l} onClick={() => setLevels(on ? levels.filter((x) => x !== l) : [...levels, l])} aria-pressed={on} className={on ? "" : "opacity-30"}>
                  <LevelBadge level={l} />
                </button>
              );
            })}
          </div>
        )}
        <span className="ml-auto text-xs text-slate-400">{rows.length} stations</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-white/[0.03] text-left text-xs text-slate-400">
            <tr>
              {th("name", "Station", "pl-3")}
              <th className="py-2 pr-2">Basin / district</th>
              {kind === "river" ? (
                <>{th("value", "Level")}<th className="py-2 pr-2">Warning / danger</th>{th("index", "Index")}<th className="py-2 pr-2">Risk</th></>
              ) : (
                <>{th("value", "Rain 1 h")}{th("rain", "Rain 24 h")}</>
              )}
              {th("updated", "Updated")}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-t border-white/5 hover:bg-white/[0.02]">
                <td className="py-1.5 pl-3 pr-2"><Link href={`/stations/${p.id}`} className="font-medium hover:underline">{p.name}</Link>
                  {p.quality && p.quality !== "GOOD" && <span className="ml-1 text-[10px] text-amber-300">{p.quality}</span>}</td>
                <td className="pr-2 text-slate-400">{p.basin ?? "—"} · {p.district ?? "—"}</td>
                {kind === "river" ? (
                  <>
                    <td className="pr-2 tabular-nums">{fmt(p.value, 2, " m")}</td>
                    <td className="pr-2 tabular-nums text-slate-400">{fmt(p.warning_level, 2)} / {fmt(p.danger_level, 2)}</td>
                    <td className="pr-2 tabular-nums">{fmt(p.ratio_to_warning, 2)}</td>
                    <td className="pr-2"><LevelBadge level={p.risk_level} /></td>
                  </>
                ) : (
                  <>
                    <td className="pr-2 tabular-nums">{fmt(p.value, 1, " mm")}</td>
                    <td className="pr-2 tabular-nums">{fmt(p.rain_24h_mm, 1, " mm")}</td>
                  </>
                )}
                <td className="pr-3 text-xs text-slate-400">{ago(p.observed_at)}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={7} className="p-4 text-slate-400">{data ? "No stations match." : "Loading…"}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

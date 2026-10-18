"use client";

import { useState } from "react";

import type { RiskLevel, SourceStatus } from "@/lib/api";
import { ago, LEVEL_COLOR } from "@/lib/colors";
import { rampCss } from "@/lib/field";
import { LAYER_INFO, type Filters, type LayerKey, type Layers } from "@/lib/layers";
import { WIND_LEGEND } from "@/lib/wind";

const LEVELS: RiskLevel[] = ["CRITICAL", "WARNING", "WATCH", "NORMAL", "UNKNOWN"];
const GROUPS = ["Weather", "Wind", "Water", "Terrain & borders"] as const;
const SOURCE_FOR: Partial<Record<LayerKey, string>> = {
  temperature: "open_meteo", heat: "open_meteo", humidity: "open_meteo", rainForecast: "open_meteo", cloud: "open_meteo",
  windFlow: "open_meteo", windArrows: "open_meteo", riverGauges: "dhm_river", rainGauges: "dhm_rain", satellite: "gpm_imerg",
};

interface Props {
  layers: Layers;
  filters: Filters;
  status?: SourceStatus[];
  onLayers: (l: Layers) => void;
  onFilters: (f: Filters) => void;
}

export default function LayerPanel({ layers, filters, status, onLayers, onFilters }: Props) {
  const [open, setOpen] = useState<LayerKey | null>(null);
  const toggle = (k: LayerKey) => onLayers({ ...layers, [k]: !layers[k] });
  const statusOf = (k: LayerKey) => status?.find((s) => s.code === SOURCE_FOR[k]);

  return (
    <div className="space-y-3 text-sm">
      {GROUPS.map((group) => (
        <section key={group}>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{group}</h3>
          <ul className="space-y-1">
            {LAYER_INFO.filter((l) => l.group === group).map((info) => {
              const st = statusOf(info.key);
              return (
                <li key={info.key} className="rounded-lg border border-slate-200 bg-white">
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <input id={`ly-${info.key}`} type="checkbox" checked={layers[info.key]} onChange={() => toggle(info.key)} className="accent-sky-700" />
                    <label htmlFor={`ly-${info.key}`} className="flex-1 cursor-pointer text-slate-800">{info.label}</label>
                    <button onClick={() => setOpen(open === info.key ? null : info.key)} className="rounded px-1.5 text-xs text-slate-500 hover:bg-slate-100"
                            aria-expanded={open === info.key} aria-label={`Details for ${info.label}`}>
                      {open === info.key ? "▾" : "ⓘ"}
                    </button>
                  </div>
                  {info.ramp && layers[info.key] && (
                    <div className="px-2 pb-1.5">
                      <div className="h-2 rounded" style={{ background: rampCss(info.ramp) }} />
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>{info.ramp[0][0]}</span><span>{info.rampUnit}</span><span>{info.ramp.at(-1)![0]}</span>
                      </div>
                    </div>
                  )}
                  {info.key === "windFlow" && layers.windFlow && (
                    <div className="flex gap-2 px-2 pb-1.5 text-[10px] text-slate-500">
                      {WIND_LEGEND.map(([s, c]) => <span key={s} className="flex items-center gap-1"><span className="inline-block h-0.5 w-4" style={{ background: c }} />{s}+</span>)}
                      <span>km/h</span>
                    </div>
                  )}
                  {open === info.key && (
                    <div className="space-y-1 border-t border-slate-100 px-2 py-2 text-xs text-slate-600">
                      <p>{info.description}</p>
                      <p><span className="text-slate-400">Source:</span> {info.source}</p>
                      <p><span className="text-slate-400">Updates:</span> {info.updates}</p>
                      {st && <p><span className="text-slate-400">Last data:</span> {st.state === "ok" ? ago(st.last_success_at) : st.state.replace("_", " ")}</p>}
                    </div>
                  )}
                  <Filter k={info.key} layers={layers} filters={filters} onFilters={onFilters} />
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Filter({ k, layers, filters, onFilters }: { k: LayerKey; layers: Layers; filters: Filters; onFilters: (f: Filters) => void }) {
  if (!layers[k]) return null;
  if (k === "windFlow" || k === "windArrows") {
    return (
      <label className="flex items-center gap-2 px-2 pb-2 text-xs text-slate-600">
        Min wind
        <input type="range" min={0} max={60} step={5} value={filters.minWindKmh} onChange={(e) => onFilters({ ...filters, minWindKmh: +e.target.value })} className="flex-1 accent-sky-700" />
        <span className="w-14 text-right tabular-nums">{filters.minWindKmh} km/h</span>
      </label>
    );
  }
  if (k === "riverGauges") {
    return (
      <div className="flex flex-wrap gap-1 px-2 pb-2">
        {LEVELS.map((l) => {
          const on = filters.riskLevels.includes(l);
          return (
            <button key={l} onClick={() => onFilters({ ...filters, riskLevels: on ? filters.riskLevels.filter((x) => x !== l) : [...filters.riskLevels, l] })}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${on ? "" : "opacity-30"}`}
                    style={{ background: LEVEL_COLOR[l], color: l === "WATCH" || l === "WARNING" ? "#1a1a1a" : "#fff" }} aria-pressed={on}>
              {l}
            </button>
          );
        })}
      </div>
    );
  }
  if (k === "rainGauges") {
    return (
      <label className="flex items-center gap-2 px-2 pb-2 text-xs text-slate-600">
        Min 24 h rain
        <input type="range" min={0} max={100} step={5} value={filters.minRain24h} onChange={(e) => onFilters({ ...filters, minRain24h: +e.target.value })} className="flex-1 accent-sky-700" />
        <span className="w-12 text-right tabular-nums">{filters.minRain24h} mm</span>
      </label>
    );
  }
  if (k === "riversNepal") {
    return (
      <label className="flex items-center gap-2 px-2 pb-2 text-xs text-slate-600">
        <input type="checkbox" checked={filters.transboundaryOnly} onChange={(e) => onFilters({ ...filters, transboundaryOnly: e.target.checked })} className="accent-sky-700" />
        Only rivers crossing a border
        <span className="ml-auto flex items-center gap-2 text-[10px]">
          <span className="flex items-center gap-1"><span className="inline-block h-1 w-4 bg-[#0a6cff]" />Nepal</span>
          <span className="flex items-center gap-1"><span className="inline-block h-1 w-4 bg-[#7b2cbf]" />cross-border</span>
        </span>
      </label>
    );
  }
  return null;
}

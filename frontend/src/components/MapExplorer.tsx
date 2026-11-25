"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import type { RiskLevel } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/colors";
import { useMapData, useStatus } from "@/lib/hooks";
import { DEFAULT_FILTERS, DEFAULT_LAYERS, type Filters, type Layers } from "@/lib/layers";
import LayerPanel from "./LayerPanel";
import LocationPanel from "./LocationPanel";
import { todayIso } from "./WeatherCard";

const WeatherGlobe = dynamic(() => import("./WeatherGlobe"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center bg-[#e9f1f7] text-sm text-slate-500">Loading 3D map…</div>,
});
const LEVELS: RiskLevel[] = ["CRITICAL", "WARNING", "WATCH", "NORMAL", "UNKNOWN"];

/** Full 3D map with the layers & filters panel and click-a-place details. Fills its positioned parent. */
export default function MapExplorer({ onClose }: { onClose?: () => void }) {
  const data = useMapData();
  const { data: status } = useStatus();
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [focus, setFocus] = useState<{ lng: number; lat: number } | null>(null);
  const [date, setDate] = useState<string | null>(null);   // first day of the weather card; null = today
  const [panelOpen, setPanelOpen] = useState(() => typeof window === "undefined" || window.innerWidth >= 768);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (focus) setFocus(null); else onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus, onClose]);

  return (
    <div className="absolute inset-0 overflow-hidden bg-[#e9f1f7]">
      <WeatherGlobe mode="full" {...data} layers={layers} filters={filters} focus={focus} onPick={(lng, lat) => setFocus({ lng, lat })} />

      <div className="absolute left-3 top-3 z-10 flex max-h-[calc(100%-1.5rem)] w-[320px] max-w-[calc(100%-4.5rem)] flex-col rounded-xl bg-slate-50/95 shadow-lg backdrop-blur">
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
          <button onClick={() => setPanelOpen(!panelOpen)} className="font-semibold text-slate-800" aria-expanded={panelOpen}>
            {panelOpen ? "▾" : "▸"} Layers & filters
          </button>
          {onClose && <button onClick={onClose} className="rounded-md bg-slate-200 px-2 py-1 text-xs text-slate-800 hover:bg-slate-300">Close ✕</button>}
        </div>
        {panelOpen && (
          <div className="overflow-y-auto p-3">
            <LayerPanel layers={layers} filters={filters} status={status} onLayers={setLayers} onFilters={setFilters} />
            <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-slate-600">
              <span className="font-semibold">River gauge colour:</span>
              {LEVELS.map((l) => <span key={l} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: LEVEL_COLOR[l] }} />{l}</span>)}
            </div>
          </div>
        )}
      </div>

      <div className="absolute left-1/2 top-3 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs text-slate-800 shadow-lg max-sm:left-auto max-sm:right-3 max-sm:translate-x-0">
        <label htmlFor="map-date" className="font-semibold">📅 Weather date</label>
        <input id="map-date" type="date" value={date ?? todayIso()} max={todayIso(15 - 7)} onChange={(e) => setDate(e.target.value || null)}
          className="rounded border border-slate-300 bg-white px-1 py-0.5" />
        {date && <button onClick={() => setDate(null)} className="rounded border border-slate-300 px-1.5 py-0.5 hover:bg-slate-100">Today</button>}
      </div>

      {!focus && (
        <div className="pointer-events-none absolute bottom-10 left-1/2 z-10 -translate-x-1/2 rounded-full bg-slate-900/80 px-4 py-2 text-center text-xs text-white">
          Pick a date above, then click anywhere to see that place&apos;s weather card · click a river or gauge for details
        </div>
      )}

      {focus && (
        <div className="absolute bottom-3 right-3 top-3 z-10 w-[460px] max-w-[calc(100%-1.5rem)] overflow-y-auto rounded-xl bg-white/95 p-3 shadow-lg backdrop-blur max-sm:top-auto max-sm:h-[55%]">
          <LocationPanel lng={focus.lng} lat={focus.lat} date={date} onDate={setDate} onClose={() => setFocus(null)} />
        </div>
      )}
    </div>
  );
}

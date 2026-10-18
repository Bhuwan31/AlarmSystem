"use client";

import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, ImageSource, Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

import type { FC, GridProps, StationProps } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/colors";
import { buildGrid, RAMPS, renderField, type Ramp } from "@/lib/field";
import type { Filters, Layers } from "@/lib/layers";
import { WindField, WindParticles } from "@/lib/wind";

interface Props {
  mode: "mini" | "full";
  nepalGrid?: FC<GridProps>;
  globalGrid?: FC<GridProps>;
  satelliteGrid?: FC<GridProps>;
  rivers?: FC<StationProps>;
  rain?: FC<StationProps>;
  layers: Layers;
  filters: Filters;
  focus?: { lng: number; lat: number } | null;
  onPick?: (lng: number, lat: number) => void;
}

const STYLE = "https://tiles.openfreemap.org/styles/positron";
const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const NEPAL_CENTER: [number, number] = [84.1, 28.3];
const NEPAL_BBOX: [number, number, number, number] = [80.0, 26.3, 88.3, 30.5];
const EMPTY = { type: "FeatureCollection", features: [] } as const;

// MapLibre parses this with `new URL()`, so it must be absolute (component is client-only).
if (typeof window !== "undefined") maplibregl.setWorkerUrl(`${window.location.origin}/maplibre-gl-worker.mjs`);

type FieldKind = "temperature" | "heat" | "humidity" | "rainForecast" | "cloud";
const FIELDS: Record<FieldKind, { prop: keyof GridProps; ramp: Ramp }> = {
  temperature: { prop: "temperature_c", ramp: RAMPS.temperature },
  heat: { prop: "tmax_3d_c", ramp: RAMPS.heat },
  humidity: { prop: "humidity_pct", ramp: RAMPS.humidity },
  rainForecast: { prop: "rain_24h_forecast_mm", ramp: RAMPS.rain },
  cloud: { prop: "cloud_cover_pct", ramp: RAMPS.cloud },
};
const FIELD_PARTS = [
  { id: "w", bbox: [-180, -60, 0, 75] as [number, number, number, number], grid: "global", w: 256, h: 256 },
  { id: "e", bbox: [0, -60, 180, 75] as [number, number, number, number], grid: "global", w: 256, h: 256 },
  { id: "np", bbox: NEPAL_BBOX, grid: "nepal", w: 384, h: 200 },
] as const;

/** Square polygons around points so values can be extruded as 3D columns. */
function columns(fc: FC<StationProps> | undefined, halfKm: number, height: (p: StationProps) => number) {
  if (!fc) return EMPTY;
  return {
    type: "FeatureCollection",
    features: fc.features.map((f) => {
      const [lon, lat] = f.geometry.coordinates;
      const dLat = halfKm / 111, dLon = halfKm / (111 * Math.cos((lat * Math.PI) / 180));
      return {
        type: "Feature",
        properties: { ...f.properties, height: height(f.properties), reasons: (f.properties.reasons ?? []).join(" · ") },
        geometry: { type: "Polygon", coordinates: [[[lon - dLon, lat - dLat], [lon + dLon, lat - dLat], [lon + dLon, lat + dLat], [lon - dLon, lat + dLat], [lon - dLon, lat - dLat]]] },
      };
    }),
  };
}

function arrowImage(): ImageData {
  const size = 48, c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#000";
  ctx.beginPath();
  ctx.moveTo(size / 2, 2); ctx.lineTo(size * 0.82, size * 0.45); ctx.lineTo(size * 0.58, size * 0.45);
  ctx.lineTo(size * 0.58, size - 2); ctx.lineTo(size * 0.42, size - 2); ctx.lineTo(size * 0.42, size * 0.45);
  ctx.lineTo(size * 0.18, size * 0.45); ctx.closePath(); ctx.fill();
  return ctx.getImageData(0, 0, size, size);
}

/** Station data comes from external feeds: escape before putting it in popup HTML (SEC-09). */
function esc(v: unknown): string {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

function setVisible(map: MLMap, ids: string[], on: boolean) {
  for (const id of ids) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
}

function corners([w, s, e, n]: [number, number, number, number]): [[number, number], [number, number], [number, number], [number, number]] {
  return [[w, n], [e, n], [e, s], [w, s]];
}

let blank = "";
function transparentPng() {
  if (!blank) { const c = document.createElement("canvas"); c.width = c.height = 1; blank = c.toDataURL("image/png"); }
  return blank;
}

export default function WeatherGlobe(props: Props) {
  const { mode } = props;
  const el = useRef<HTMLDivElement>(null);
  const latest = useRef<Props>(props);
  const applyRef = useRef<{ data: () => void; layers: () => void; focus: () => void } | null>(null);

  useEffect(() => {
    if (!el.current) return;
    const full = mode === "full";
    const map = new maplibregl.Map({
      container: el.current, style: STYLE,
      center: full ? NEPAL_CENTER : [84.1, 22], zoom: full ? 5.4 : 1.15, pitch: full ? 45 : 0, bearing: 0,
      interactive: full, attributionControl: full ? { compact: true } : false, maxPitch: 80,
    });
    if (process.env.NODE_ENV === "development") (window as unknown as Record<string, unknown>)[`__amhews_${mode}`] = map;
    if (full) {
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      map.addControl(new maplibregl.GlobeControl(), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    }
    let ready = false;
    let particles: WindParticles | null = null;
    let marker: maplibregl.Marker | null = null;
    const fieldCache = new Map<string, unknown>();

    map.on("style.load", () => {
      map.setProjection({ type: "globe" });
      map.setSky({
        "sky-color": "#d6e8f5", "horizon-color": "#ffffff", "fog-color": "#ffffff",
        "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.9, 5, 0.6, 8, 0],
      } as maplibregl.SkySpecification);
      map.addImage("wind-arrow", arrowImage(), { sdf: true });
      const labelsBefore = map.getStyle().layers.find((l) => l.type === "symbol")?.id;

      // Weather fields (images), below basemap labels
      for (const kind of Object.keys(FIELDS) as FieldKind[]) {
        for (const part of FIELD_PARTS) {
          const id = `field-${kind}-${part.id}`;
          map.addSource(id, { type: "image", url: transparentPng(), coordinates: corners(part.bbox) });
          map.addLayer({ id, type: "raster", source: id, layout: { visibility: "none" },
                         paint: { "raster-opacity": kind === "temperature" ? 0.75 : 0.8, "raster-fade-duration": 0, "raster-resampling": "linear" } }, labelsBefore);
        }
      }

      // Terrain + hillshade (separate sources, as MapLibre recommends)
      map.addSource("dem", { type: "raster-dem", tiles: [DEM_TILES], encoding: "terrarium", tileSize: 256, maxzoom: 14 });
      map.addSource("dem-hs", { type: "raster-dem", tiles: [DEM_TILES], encoding: "terrarium", tileSize: 256, maxzoom: 14 });
      map.addLayer({ id: "hillshade", type: "hillshade", source: "dem-hs", minzoom: 4.5,
                     paint: { "hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#5b6b7a" } }, labelsBefore);

      // Rivers and border
      map.addSource("rivers-world", { type: "geojson", data: "/geo/rivers_world.geojson" });
      map.addSource("rivers-nepal", { type: "geojson", data: "/geo/rivers_nepal.geojson" });
      map.addSource("nepal", { type: "geojson", data: "/geo/nepal.geojson" });
      map.addLayer({ id: "rivers-world", type: "line", source: "rivers-world",
        paint: { "line-color": "#4f8fc6", "line-opacity": 0.75,
                 "line-width": ["interpolate", ["linear"], ["zoom"], 0, ["match", ["get", "scalerank"], [0, 1, 2], 0.8, 0.35], 6, 1.6] } }, labelsBefore);
      map.addLayer({ id: "rivers-nepal-casing", type: "line", source: "rivers-nepal",
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1.5, 7, 5], "line-opacity": 0.85 } }, labelsBefore);
      map.addLayer({ id: "rivers-nepal", type: "line", source: "rivers-nepal",
        paint: { "line-color": ["case", ["get", "transboundary"], "#7b2cbf", "#0a6cff"],
                 "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.8, 7, 2.8, 11, 4] } }, labelsBefore);
      map.addLayer({ id: "rivers-nepal-label", type: "symbol", source: "rivers-nepal", minzoom: 6.5,
        layout: { "symbol-placement": "line", "text-field": ["get", "name"], "text-size": 12, "text-font": ["Noto Sans Regular"] },
        paint: { "text-color": "#0b3c8c", "text-halo-color": "#ffffff", "text-halo-width": 1.5 } });
      map.addLayer({ id: "nepal-border-casing", type: "line", source: "nepal", paint: { "line-color": "#ffffff", "line-width": 5 } });
      map.addLayer({ id: "nepal-border", type: "line", source: "nepal", paint: { "line-color": "#c0262d", "line-width": 2.2 } });

      // Wind arrows, satellite rain, gauges
      for (const src of ["global-grid", "nepal-grid", "sat-grid", "river-cols", "rain-cols", "river-pts", "rain-pts"]) map.addSource(src, { type: "geojson", data: EMPTY as never });
      for (const [src, minz, maxz] of [["global-grid", 0, 4], ["nepal-grid", 4, 24]] as const) {
        map.addLayer({ id: `${src}-wind`, type: "symbol", source: src, minzoom: minz, maxzoom: maxz,
          layout: { "icon-image": "wind-arrow", "icon-rotate": ["+", ["coalesce", ["get", "wind_dir_deg"], 0], 180], "icon-rotation-alignment": "map",
                    "icon-size": ["interpolate", ["linear"], ["coalesce", ["get", "wind_speed_kmh"], 0], 0, 0.22, 30, 0.45, 80, 0.75], "icon-allow-overlap": true },
          paint: { "icon-color": "#24305e", "icon-opacity": 0.8 } });
      }
      map.addLayer({ id: "sat-grid-rain", type: "circle", source: "sat-grid",
        paint: { "circle-color": ["interpolate", ["linear"], ["coalesce", ["get", "precipitation_mm"], 0], 0, "#c6dbef", 2, "#3fa7d6", 10, "#7b2cbf", 30, "#ff006e"],
                 "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 6, 7, 26], "circle-opacity": 0.55 } });
      // Zoomed out, gauges are dots; from zoom 7 they become 3D columns
      map.addLayer({ id: "rain-dots", type: "circle", source: "rain-pts", maxzoom: 7,
        paint: { "circle-color": ["interpolate", ["linear"], ["coalesce", ["get", "rain_24h_mm"], 0], 0, "#9ecae1", 20, "#2171b5", 60, "#6a51a3"],
                 "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.5, 7, 4], "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.6 } });
      map.addLayer({ id: "river-dots", type: "circle", source: "river-pts", maxzoom: 7,
        paint: { "circle-color": ["match", ["get", "risk_level"], "CRITICAL", LEVEL_COLOR.CRITICAL, "WARNING", LEVEL_COLOR.WARNING,
                                  "WATCH", LEVEL_COLOR.WATCH, "NORMAL", LEVEL_COLOR.NORMAL, LEVEL_COLOR.UNKNOWN],
                 "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 2, 7, 6], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1 } });
      map.addLayer({ id: "rain-cols", type: "fill-extrusion", source: "rain-cols", minzoom: 6.5,
        paint: { "fill-extrusion-color": ["interpolate", ["linear"], ["get", "height"], 0, "#6baed6", 20000, "#2171b5", 60000, "#6a51a3"],
                 "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 5, ["get", "height"], 9, ["/", ["get", "height"], 6], 13, ["/", ["get", "height"], 40]], "fill-extrusion-opacity": 0.85 } });
      map.addLayer({ id: "river-cols", type: "fill-extrusion", source: "river-cols", minzoom: 6.5,
        paint: { "fill-extrusion-color": ["match", ["get", "risk_level"], "CRITICAL", LEVEL_COLOR.CRITICAL, "WARNING", LEVEL_COLOR.WARNING,
                                          "WATCH", LEVEL_COLOR.WATCH, "NORMAL", LEVEL_COLOR.NORMAL, LEVEL_COLOR.UNKNOWN],
                 "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 5, ["get", "height"], 9, ["/", ["get", "height"], 6], 13, ["/", ["get", "height"], 40]], "fill-extrusion-opacity": 0.92 } });

      particles = new WindParticles(map, full ? 3200 : 1400);

      if (full) {
        const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "320px" });
        const clickable = ["river-cols", "rain-cols", "river-dots", "rain-dots", "rivers-nepal"];
        map.on("click", (e) => {
          const hits = map.queryRenderedFeatures(e.point, { layers: clickable.filter((l) => map.getLayoutProperty(l, "visibility") !== "none") });
          const f = hits[0];
          if (!f) { latest.current.onPick?.(e.lngLat.lng, e.lngLat.lat); return; }
          const p = f.properties as Record<string, unknown>;
          const row = ([k, v]: [string, string]) => `<div><span class="muted">${esc(k)}:</span> ${esc(v)}</div>`;
          if (f.layer.id === "rivers-nepal") {
            popup.setLngLat(e.lngLat).setHTML(`<div class="popup"><b>${esc(p.name)}</b>${row(["Flows through", String(p.countries)])}${row(["Length (mapped)", `${p.length_km} km`])}<div class="muted">© OpenStreetMap contributors</div></div>`).addTo(map);
            return;
          }
          const rows: [string, string][] = f.layer.id.startsWith("river-")
            ? [["Water level", `${Number(p.value ?? NaN).toFixed(2)} m`], ["Warning / danger", `${p.warning_level ?? "—"} / ${p.danger_level ?? "—"} m`],
               ["Risk", `${p.risk_level} (${p.confidence ?? "—"})`], ["Trend", `${p.trend ?? "—"}`], ["Why", `${p.reasons || "—"}`]]
            : [["Rain 1 h", `${p.value ?? "—"} mm`], ["Rain 24 h", `${p.rain_24h_mm ?? "—"} mm`]];
          popup.setLngLat(e.lngLat).setHTML(
            `<div class="popup"><b>${esc(p.name)}</b><div class="muted">${esc(p.basin)} · ${esc(p.district)} · ${esc(p.source)}</div>` +
            rows.map(row).join("") + `<div class="muted">Observed ${esc(p.observed_at ?? "—")}</div></div>`).addTo(map);
        });
        for (const id of clickable) {
          map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
          map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
        }
        map.on("zoomend", applyTerrain);
      }
      ready = true;
      applyData();
      applyLayers();
      applyFocus();
    });

    // Slow spin in the mini view so the globe reads as live
    let raf = 0;
    if (!full) {
      const spin = () => {
        if (!map.isMoving()) map.setCenter([map.getCenter().lng + 0.04, map.getCenter().lat]);
        raf = requestAnimationFrame(spin);
      };
      map.once("idle", () => (raf = requestAnimationFrame(spin)));
    }

    function renderFields() {
      const p = latest.current;
      for (const kind of Object.keys(FIELDS) as FieldKind[]) {
        if (!p.layers[kind]) continue;   // render lazily: only fields that are switched on
        for (const part of FIELD_PARTS) {
          const fc = part.grid === "global" ? p.globalGrid : p.nepalGrid;
          const key = `${kind}-${part.id}`;
          if (!fc || fieldCache.get(key) === fc) continue;
          fieldCache.set(key, fc);
          const g = buildGrid(fc, FIELDS[kind].prop);
          const src = map.getSource(`field-${kind}-${part.id}`) as ImageSource | undefined;
          if (!g || !src) continue;
          const img = renderField(g, FIELDS[kind].ramp, part.bbox,
            { width: part.w, height: part.h, wrapLon: part.grid === "global", fadeEdgeDeg: part.grid === "nepal" ? 1.4 : undefined });
          src.updateImage({ url: img.url, coordinates: img.coordinates });
        }
      }
    }

    function applyData() {
      const p = latest.current;
      if (!ready) return;
      (map.getSource("global-grid") as GeoJSONSource).setData((p.globalGrid ?? EMPTY) as never);
      (map.getSource("nepal-grid") as GeoJSONSource).setData((p.nepalGrid ?? EMPTY) as never);
      (map.getSource("sat-grid") as GeoJSONSource).setData((p.satelliteGrid ?? EMPTY) as never);
      (map.getSource("river-cols") as GeoJSONSource).setData(columns(p.rivers, 1.4, (s) => 3000 + Math.max(0, Math.min(s.ratio_to_warning ?? 0, 1.6)) * 30000) as never);
      (map.getSource("river-pts") as GeoJSONSource).setData((p.rivers ?? EMPTY) as never);
      (map.getSource("rain-pts") as GeoJSONSource).setData((p.rain ?? EMPTY) as never);
      (map.getSource("rain-cols") as GeoJSONSource).setData(columns(p.rain, 1.0, (s) => Math.min(s.rain_24h_mm ?? 0, 200) * 600) as never);
      particles?.setField(new WindField(p.globalGrid, p.nepalGrid));
      renderFields();
    }

    function applyLayers() {
      const { layers: l, filters: f } = latest.current;
      if (!ready) return;
      for (const kind of Object.keys(FIELDS) as FieldKind[]) setVisible(map, FIELD_PARTS.map((part) => `field-${kind}-${part.id}`), l[kind]);
      renderFields();
      setVisible(map, ["global-grid-wind", "nepal-grid-wind"], l.windArrows);
      setVisible(map, ["rivers-world"], l.riversWorld);
      setVisible(map, ["rivers-nepal", "rivers-nepal-casing", "rivers-nepal-label"], l.riversNepal);
      setVisible(map, ["river-cols", "river-dots"], l.riverGauges);
      setVisible(map, ["rain-cols", "rain-dots"], l.rainGauges);
      setVisible(map, ["sat-grid-rain"], l.satellite);
      setVisible(map, ["hillshade"], l.terrain);
      setVisible(map, ["nepal-border", "nepal-border-casing"], l.border);
      if (particles) { particles.visible = l.windFlow; particles.minSpeed = f.minWindKmh; }
      const windFilter = [">=", ["coalesce", ["get", "wind_speed_kmh"], 0], f.minWindKmh] as maplibregl.FilterSpecification;
      map.setFilter("global-grid-wind", windFilter);
      map.setFilter("nepal-grid-wind", windFilter);
      for (const id of ["river-cols", "river-dots"]) map.setFilter(id, ["in", ["get", "risk_level"], ["literal", f.riskLevels]] as maplibregl.FilterSpecification);
      for (const id of ["rain-cols", "rain-dots"]) map.setFilter(id, [">=", ["coalesce", ["get", "rain_24h_mm"], 0], f.minRain24h] as maplibregl.FilterSpecification);
      const tb = f.transboundaryOnly ? (["==", ["get", "transboundary"], true] as maplibregl.FilterSpecification) : null;
      for (const id of ["rivers-nepal", "rivers-nepal-casing", "rivers-nepal-label"]) map.setFilter(id, tb);
      applyTerrain();
    }

    function applyTerrain() {
      if (!ready || !full) return;
      const want = latest.current.layers.terrain && map.getZoom() >= 6;
      const has = !!map.getTerrain();
      if (want && !has) map.setTerrain({ source: "dem", exaggeration: 1.4 });
      if (!want && has) map.setTerrain(null);
    }

    function applyFocus() {
      const f = latest.current.focus;
      if (!ready || !full) return;
      marker?.remove(); marker = null;
      if (!f) return;
      marker = new maplibregl.Marker({ color: "#c0262d" }).setLngLat([f.lng, f.lat]).addTo(map);
      map.flyTo({ center: [f.lng, f.lat], zoom: 11.5, pitch: 68, bearing: map.getBearing() + 25, duration: 3500, essential: true });
    }

    applyRef.current = { data: applyData, layers: applyLayers, focus: applyFocus };
    return () => {
      cancelAnimationFrame(raf);
      particles?.destroy();
      applyRef.current = null;
      map.remove();
    };
  }, [mode]);

  const { nepalGrid, globalGrid, satelliteGrid, rivers, rain, layers, filters, focus } = props;
  useEffect(() => {
    latest.current = props;
    applyRef.current?.data();
  }, [nepalGrid, globalGrid, satelliteGrid, rivers, rain]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    latest.current = props;
    applyRef.current?.layers();
  }, [layers, filters]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    latest.current = props;
    applyRef.current?.focus();
  }, [focus]); // eslint-disable-line react-hooks/exhaustive-deps

  // MapLibre sets `position: relative` on its container, so size it inside an absolutely positioned wrapper.
  return (
    <div className="absolute inset-0 bg-[#e9f1f7]">
      <div ref={el} className="h-full w-full" />
    </div>
  );
}

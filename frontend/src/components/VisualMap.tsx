"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

import { circle, MAP_STYLE, NEPAL_CENTER } from "@/lib/visual";

export interface MapPoint {
  id: string;
  lon: number;
  lat: number;
  color: string;
  label: string;
  /** marker shape: circle = photo observation, diamond = incident */
  kind?: "observation" | "incident" | "pick" | "home";
  ring?: boolean;
}
export interface MapCircle { id: string; lon: number; lat: number; km: number; color: string; dashed?: boolean }

interface Props {
  points?: MapPoint[];
  circles?: MapCircle[];
  onPick?: (lat: number, lon: number) => void;
  onSelect?: (id: string) => void;
  focus?: { lat: number; lon: number; zoom?: number } | null;
  className?: string;
}

const EMPTY = { type: "FeatureCollection" as const, features: [] };
// The bundler cannot serve MapLibre's worker; it is copied to public/ on install (same as WeatherGlobe).
if (typeof window !== "undefined") maplibregl.setWorkerUrl(`${window.location.origin}/maplibre-gl-worker.mjs`);

export default function VisualMap({ points = [], circles = [], onPick, onSelect, focus, className = "h-72" }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const cb = useRef({ onPick, onSelect });
  const data = useRef({ points, circles });
  useEffect(() => {                                   // keep the latest props for the map's event handlers
    cb.current = { onPick, onSelect };
    data.current = { points, circles };
  });

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({ container: el.current, style: MAP_STYLE, center: NEPAL_CENTER, zoom: 5.6, attributionControl: { compact: true } });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addSource("circles", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "circle-fill", type: "fill", source: "circles", paint: { "fill-color": ["get", "color"], "fill-opacity": 0.13 } });
      m.addLayer({ id: "circle-line", type: "line", source: "circles", filter: ["!", ["get", "dashed"]], paint: { "line-color": ["get", "color"], "line-width": 2 } });
      m.addLayer({ id: "circle-dash", type: "line", source: "circles", filter: ["get", "dashed"], paint: { "line-color": ["get", "color"], "line-width": 2, "line-dasharray": [2, 2] } });
      m.addSource("points", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "pt-obs", type: "circle", source: "points", filter: ["==", ["get", "kind"], "observation"],
        paint: { "circle-radius": 6, "circle-color": ["get", "color"], "circle-stroke-color": "#0b1d24", "circle-stroke-width": 1.5 } });
      m.addLayer({ id: "pt-inc", type: "symbol", source: "points", filter: ["==", ["get", "kind"], "incident"],
        layout: { "text-field": "◆", "text-size": 26, "text-allow-overlap": true, "text-anchor": "center" },
        paint: { "text-color": ["get", "color"], "text-halo-color": ["case", ["get", "ring"], "#ffffff", "#0b1d24"], "text-halo-width": 2 } });
      m.addLayer({ id: "pt-pick", type: "symbol", source: "points", filter: ["in", ["get", "kind"], ["literal", ["pick", "home"]]],
        layout: { "text-field": ["case", ["==", ["get", "kind"], "home"], "⌂", "●"], "text-size": 24, "text-allow-overlap": true },
        paint: { "text-color": ["get", "color"], "text-halo-color": "#ffffff", "text-halo-width": 2 } });
      ready.current = true;
      render();
      for (const id of ["pt-obs", "pt-inc"]) {
        m.on("click", id, (e) => {
          const f = e.features?.[0];
          if (f && cb.current.onSelect) cb.current.onSelect(String(f.properties?.id));
        });
        m.on("mouseenter", id, () => { m.getCanvas().style.cursor = "pointer"; });
        m.on("mouseleave", id, () => { m.getCanvas().style.cursor = ""; });
      }
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
      for (const id of ["pt-obs", "pt-inc"]) {
        m.on("mousemove", id, (e) => { const f = e.features?.[0]; if (f) popup.setLngLat(e.lngLat).setText(String(f.properties?.label)).addTo(m); });
        m.on("mouseleave", id, () => popup.remove());
      }
    });
    m.on("click", (e) => {
      const hit = ready.current && m.queryRenderedFeatures(e.point, { layers: ["pt-obs", "pt-inc"] }).length > 0;
      if (!hit && cb.current.onPick) cb.current.onPick(+e.lngLat.lat.toFixed(6), +e.lngLat.lng.toFixed(6));
    });
    function render() {
      if (!ready.current) return;
      const { points: ps, circles: cs } = data.current;
      (m.getSource("points") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: ps.map((p) => ({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
          properties: { id: p.id, color: p.color, label: p.label, kind: p.kind ?? "observation", ring: !!p.ring } })),
      });
      (m.getSource("circles") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: cs.map((c) => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [circle(c.lon, c.lat, c.km)] },
          properties: { id: c.id, color: c.color, dashed: !!c.dashed } })),
      });
    }
    (m as unknown as { __render: () => void }).__render = render;
    return () => { ready.current = false; m.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const m = map.current as unknown as { __render?: () => void } | null;
    m?.__render?.();
  }, [points, circles]);

  useEffect(() => {
    if (focus && map.current) map.current.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 12, duration: 800 });
  }, [focus]);

  return <div ref={el} className={`w-full overflow-hidden rounded-lg border border-white/10 ${className}`} role="application" aria-label="Map" />;
}

import type { Map as MLMap } from "maplibre-gl";

import type { FC, GridProps } from "./api";
import { buildGrid, sampleGrid, type Grid } from "./field";

/** u/v wind field (km/h) from the coarse global grid, refined by the denser regional grid inside its bbox. */
export class WindField {
  private gu: Grid | null; private gv: Grid | null;
  private ru: Grid | null; private rv: Grid | null;
  private rbox: [number, number, number, number] | null;

  constructor(global?: FC<GridProps>, regional?: FC<GridProps>) {
    [this.gu, this.gv] = WindField.uv(global);
    [this.ru, this.rv] = WindField.uv(regional);
    this.rbox = this.ru ? [this.ru.lons[0], this.ru.lats[0], this.ru.lons.at(-1)!, this.ru.lats.at(-1)!] : null;
  }

  private static uv(fc?: FC<GridProps>): [Grid | null, Grid | null] {
    if (!fc?.features.length) return [null, null];
    const withUV = {
      ...fc,
      features: fc.features.map((f) => {
        const s = f.properties.wind_speed_kmh ?? 0, d = ((f.properties.wind_dir_deg ?? 0) * Math.PI) / 180;
        // meteorological direction = where the wind comes FROM
        return { ...f, properties: { ...f.properties, u: -s * Math.sin(d), v: -s * Math.cos(d) } as unknown as GridProps };
      }),
    };
    return [buildGrid(withUV, "u" as keyof GridProps), buildGrid(withUV, "v" as keyof GridProps)];
  }

  get ready() { return !!(this.gu || this.ru); }

  sample(lon: number, lat: number): [number, number] | null {
    const b = this.rbox;
    if (this.ru && this.rv && b && lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3]) {
      const u = sampleGrid(this.ru, lon, lat, false), v = sampleGrid(this.rv, lon, lat, false);
      if (u !== null && v !== null) return [u, v];
    }
    if (this.gu && this.gv) {
      const u = sampleGrid(this.gu, lon, lat, true), v = sampleGrid(this.gv, lon, lat, true);
      if (u !== null && v !== null) return [u, v];
    }
    return null;
  }
}

const SPEED_COLORS: [number, string][] = [[0, "#3b6e99"], [12, "#2a5db0"], [25, "#5b3fa6"], [40, "#a2307f"], [60, "#d1263f"]];
function colorFor(speed: number) {
  let c = SPEED_COLORS[0][1];
  for (const [s, col] of SPEED_COLORS) if (speed >= s) c = col;
  return c;
}

interface Particle { lon: number; lat: number; age: number; life: number }

/** Animated wind-flow streaks drawn on a 2D canvas that follows the map (works on the globe). */
export class WindParticles {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private particles: Particle[] = [];
  private raf = 0;
  private field: WindField | null = null;
  minSpeed = 0;
  visible = true;

  constructor(private map: MLMap, private count: number) {
    this.canvas = document.createElement("canvas");
    Object.assign(this.canvas.style, { position: "absolute", inset: "0", pointerEvents: "none" });
    map.getCanvasContainer().appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d")!;
    this.resize();
    map.on("resize", this.resize);
    map.on("move", this.clear);
    this.loop();
  }

  setField(f: WindField) { this.field = f; this.particles = []; }

  private resize = () => {
    const c = this.map.getCanvas(), dpr = window.devicePixelRatio || 1;
    this.canvas.width = c.clientWidth * dpr; this.canvas.height = c.clientHeight * dpr;
    this.canvas.style.width = `${c.clientWidth}px`; this.canvas.style.height = `${c.clientHeight}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  private clear = () => this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

  private spawn(): Particle {
    const z = this.map.getZoom();
    let lon: number, lat: number;
    if (z < 3.5) {
      const c = this.map.getCenter();
      lon = c.lng + (Math.random() - 0.5) * 180;
      lat = Math.max(-60, Math.min(72, c.lat + (Math.random() - 0.5) * 160));
    } else {
      const b = this.map.getBounds();
      lon = b.getWest() + Math.random() * (b.getEast() - b.getWest());
      lat = b.getSouth() + Math.random() * (b.getNorth() - b.getSouth());
    }
    return { lon: ((lon + 540) % 360) - 180, lat, age: 0, life: 60 + Math.random() * 90 };
  }

  private visibleOnGlobe(lon: number, lat: number) {
    if (this.map.getZoom() > 5) return true;
    const c = this.map.getCenter(), r = Math.PI / 180;
    const cos = Math.sin(lat * r) * Math.sin(c.lat * r) + Math.cos(lat * r) * Math.cos(c.lat * r) * Math.cos((lon - c.lng) * r);
    return cos > 0.12;   // front hemisphere only
  }

  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    const ctx = this.ctx, w = this.canvas.clientWidth || this.canvas.width, h = this.canvas.clientHeight || this.canvas.height;
    // fade previous trails
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = "rgba(0,0,0,0.94)";
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = "source-over";
    if (!this.visible || !this.field?.ready) return;
    while (this.particles.length < this.count) this.particles.push(this.spawn());
    // constant on-screen speed: ~0.09 px per frame per km/h, whatever the zoom
    const pxPerDeg = (512 * Math.pow(2, this.map.getZoom())) / 360;
    const scale = 0.09 / pxPerDeg;
    ctx.lineWidth = 1.6;
    ctx.lineCap = "round";
    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      const uv = this.field.sample(p.lon, p.lat);
      if (!uv || p.age++ > p.life) { this.particles[i] = this.spawn(); continue; }
      const [u, v] = uv, speed = Math.hypot(u, v);
      const nlon = p.lon + (u * scale) / Math.max(Math.cos((p.lat * Math.PI) / 180), 0.2);
      const nlat = Math.max(-85, Math.min(85, p.lat + v * scale));
      if (speed >= this.minSpeed && this.visibleOnGlobe(p.lon, p.lat)) {
        const a = this.map.project([p.lon, p.lat]), b = this.map.project([nlon, nlat]);
        if (Math.abs(a.x - b.x) < 40 && Math.abs(a.y - b.y) < 40) {
          ctx.strokeStyle = colorFor(speed);
          ctx.globalAlpha = Math.min(1, Math.sin((p.age / p.life) * Math.PI) * 1.2);
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      p.lon = ((nlon + 540) % 360) - 180; p.lat = nlat;
    }
    ctx.globalAlpha = 1;
  };

  destroy() {
    cancelAnimationFrame(this.raf);
    this.map.off("resize", this.resize);
    this.map.off("move", this.clear);
    this.canvas.remove();
  }
}

export const WIND_LEGEND = SPEED_COLORS;

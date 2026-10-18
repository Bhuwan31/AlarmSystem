import type { FC, GridProps } from "./api";

/** Colour ramp: [value, [r, g, b, a]] stops, ascending. */
export type Ramp = [number, [number, number, number, number]][];

export const RAMPS: Record<string, Ramp> = {
  temperature: [
    [-40, [94, 33, 143, 210]], [-25, [49, 54, 149, 210]], [-10, [69, 117, 180, 205]], [0, [116, 173, 209, 200]],
    [8, [102, 189, 99, 200]], [16, [217, 239, 139, 200]], [22, [254, 224, 139, 205]], [28, [253, 174, 97, 210]],
    [34, [244, 109, 67, 215]], [40, [215, 48, 39, 220]], [48, [128, 0, 38, 225]],
  ],
  humidity: [[0, [191, 129, 45, 170]], [30, [223, 194, 125, 150]], [60, [128, 205, 193, 160]], [85, [53, 151, 143, 180]], [100, [1, 102, 94, 200]]],
  rain: [[0, [0, 0, 0, 0]], [0.5, [158, 202, 225, 120]], [5, [66, 146, 198, 180]], [20, [33, 113, 181, 210]], [50, [106, 81, 163, 225]], [100, [199, 21, 133, 235]]],
  cloud: [[0, [0, 0, 0, 0]], [20, [120, 130, 140, 40]], [60, [110, 120, 130, 110]], [100, [90, 100, 110, 170]]],
  heat: [[31.9, [0, 0, 0, 0]], [32, [254, 217, 118, 150]], [35, [253, 141, 60, 190]], [38, [227, 26, 28, 215]], [42, [128, 0, 38, 235]]],
};

export function rampColor(ramp: Ramp, v: number): [number, number, number, number] {
  if (v <= ramp[0][0]) return ramp[0][1];
  for (let i = 1; i < ramp.length; i++) {
    const [v1, c1] = ramp[i];
    if (v <= v1) {
      const [v0, c0] = ramp[i - 1];
      const t = (v - v0) / (v1 - v0);
      return [0, 1, 2, 3].map((k) => c0[k] + (c1[k] - c0[k]) * t) as [number, number, number, number];
    }
  }
  return ramp[ramp.length - 1][1];
}

export function rampCss(ramp: Ramp): string {
  const lo = ramp[0][0], hi = ramp[ramp.length - 1][0];
  return `linear-gradient(to right, ${ramp.map(([v, c]) => `rgba(${c[0]},${c[1]},${c[2]},${Math.max(c[3], 120) / 255}) ${((v - lo) / (hi - lo)) * 100}%`).join(", ")})`;
}

/** Regular lat/lon grid of one property, built from grid points. */
export interface Grid {
  lats: number[];   // ascending
  lons: number[];   // ascending
  values: (number | null)[][];   // [latIdx][lonIdx]
}

export function buildGrid(fc: FC<GridProps> | undefined, key: keyof GridProps): Grid | null {
  if (!fc?.features.length) return null;
  const lats = [...new Set(fc.features.map((f) => f.geometry.coordinates[1]))].sort((a, b) => a - b);
  const lons = [...new Set(fc.features.map((f) => f.geometry.coordinates[0]))].sort((a, b) => a - b);
  const li = new Map(lats.map((v, i) => [v, i])), lo = new Map(lons.map((v, i) => [v, i]));
  const values = lats.map(() => lons.map(() => null as number | null));
  for (const f of fc.features) {
    const v = f.properties[key];
    values[li.get(f.geometry.coordinates[1])!][lo.get(f.geometry.coordinates[0])!] = typeof v === "number" ? v : null;
  }
  return { lats, lons, values };
}

function bracket(arr: number[], x: number, wrap: number | null): [number, number, number] {
  const n = arr.length;
  if (wrap !== null) {
    // periodic longitude axis
    let i = arr.findIndex((v) => v > x) - 1;
    if (i < 0) i = x < arr[0] ? n - 1 : n - 1;
    const j = (i + 1) % n;
    let span = arr[j] - arr[i];
    if (span <= 0) span += wrap;
    let d = x - arr[i];
    if (d < 0) d += wrap;
    return [i, j, Math.min(Math.max(d / span, 0), 1)];
  }
  if (x <= arr[0]) return [0, 0, 0];
  if (x >= arr[n - 1]) return [n - 1, n - 1, 0];
  const i = arr.findIndex((v) => v > x) - 1;
  return [i, i + 1, (x - arr[i]) / (arr[i + 1] - arr[i])];
}

export function sampleGrid(g: Grid, lon: number, lat: number, wrapLon: boolean): number | null {
  const [i0, i1, ty] = bracket(g.lats, lat, null);
  const [j0, j1, tx] = bracket(g.lons, lon, wrapLon ? 360 : null);
  const q = [g.values[i0][j0], g.values[i0][j1], g.values[i1][j0], g.values[i1][j1]];
  const w = [(1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty];
  let sum = 0, wsum = 0;
  q.forEach((v, k) => { if (v !== null) { sum += v * w[k]; wsum += w[k]; } });
  return wsum > 0 ? sum / wsum : null;
}

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const invMercY = (y: number) => (360 / Math.PI) * Math.atan(Math.exp(y)) - 90;

export interface FieldImage {
  url: string;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
}

/** Rasterise a grid into a PNG whose rows are spaced in Web Mercator, so MapLibre places it correctly. */
export function renderField(
  g: Grid, ramp: Ramp, bbox: [number, number, number, number],
  opts: { width: number; height: number; wrapLon: boolean; fadeEdgeDeg?: number },
): FieldImage {
  const [w, s, e, n] = bbox;
  const c = document.createElement("canvas");
  c.width = opts.width; c.height = opts.height;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(opts.width, opts.height);
  const y0 = mercY(n), y1 = mercY(s);
  for (let py = 0; py < opts.height; py++) {
    const lat = invMercY(y0 + ((py + 0.5) / opts.height) * (y1 - y0));
    for (let px = 0; px < opts.width; px++) {
      const lon = w + ((px + 0.5) / opts.width) * (e - w);
      const v = sampleGrid(g, lon, lat, opts.wrapLon);
      if (v === null) continue;
      const [r, gg, b, a] = rampColor(ramp, v);
      let alpha = a;
      if (opts.fadeEdgeDeg) {
        const edge = Math.min(lon - w, e - lon, lat - s, n - lat);
        alpha *= Math.max(0, Math.min(1, edge / opts.fadeEdgeDeg));
      }
      const k = (py * opts.width + px) * 4;
      img.data[k] = r; img.data[k + 1] = gg; img.data[k + 2] = b; img.data[k + 3] = alpha;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { url: c.toDataURL("image/png"), coordinates: [[w, n], [e, n], [e, s], [w, s]] };
}

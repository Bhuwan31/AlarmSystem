"use client";

import { useMemo, useState } from "react";

export interface Point { t: string; v: number | null }
interface Threshold { value: number; label: string; color: string }

/** Minimal responsive SVG time-series chart with threshold lines and hover read-out. */
export default function LineChart({ points, unit, thresholds = [], height = 220, color = "#38bdf8" }:
  { points: Point[]; unit: string; thresholds?: Threshold[]; height?: number; color?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const valid = useMemo(() => points.filter((p) => p.v !== null) as { t: string; v: number }[], [points]);
  if (valid.length < 2) return <p className="py-8 text-center text-sm text-slate-400">Not enough readings yet to draw a chart.</p>;

  const W = 800, H = height, padL = 52, padR = 12, padT = 12, padB = 26;
  const ts = valid.map((p) => new Date(p.t).getTime());
  const t0 = ts[0], t1 = ts[ts.length - 1];
  const vals = [...valid.map((p) => p.v), ...thresholds.map((t) => t.value)];
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo || 1) * 0.1; lo -= pad; hi += pad;
  const x = (t: number) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const path = valid.map((p, i) => `${i ? "L" : "M"}${x(ts[i]).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const fmtT = (t: number) => new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const h = hover !== null ? valid[hover] : null;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Chart of ${valid.length} readings in ${unit}`}
           onMouseLeave={() => setHover(null)}
           onMouseMove={(e) => {
             const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
             const tx = t0 + (((e.clientX - r.left) / r.width) * W - padL) / (W - padL - padR) * (t1 - t0);
             let best = 0;
             ts.forEach((t, i) => { if (Math.abs(t - tx) < Math.abs(ts[best] - tx)) best = i; });
             setHover(best);
           }}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="#ffffff14" />
            <text x={padL - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#94a3b8">{v.toFixed(Math.abs(hi - lo) < 5 ? 2 : 0)}</text>
          </g>
        ))}
        {thresholds.map((th) => (
          <g key={th.label}>
            <line x1={padL} x2={W - padR} y1={y(th.value)} y2={y(th.value)} stroke={th.color} strokeDasharray="6 4" strokeWidth="1.5" />
            <text x={W - padR - 4} y={y(th.value) - 4} textAnchor="end" fontSize="11" fill={th.color}>{th.label} {th.value}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke={color} strokeWidth="2" />
        <text x={padL} y={H - 6} fontSize="11" fill="#94a3b8">{fmtT(t0)}</text>
        <text x={W - padR} y={H - 6} fontSize="11" fill="#94a3b8" textAnchor="end">{fmtT(t1)}</text>
        {h && hover !== null && (
          <g>
            <line x1={x(ts[hover])} x2={x(ts[hover])} y1={padT} y2={H - padB} stroke="#ffffff40" />
            <circle cx={x(ts[hover])} cy={y(h.v)} r="4" fill={color} />
          </g>
        )}
      </svg>
      {h && hover !== null && (
        <div className="pointer-events-none absolute right-2 top-2 rounded bg-black/70 px-2 py-1 text-xs">
          {fmtT(ts[hover])}: <b>{h.v.toFixed(2)} {unit}</b>
        </div>
      )}
    </div>
  );
}

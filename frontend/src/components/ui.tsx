"use client";

import Link from "next/link";

import type { RiskLevel, SourceStatus } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/colors";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, note, children, className = "" }: { title?: string; note?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-white/10 bg-white/[0.03] p-4 ${className}`}>
      {(title || note) && (
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          {title && <h2 className="font-semibold">{title}</h2>}
          {note && <span className="text-xs text-slate-400">{note}</span>}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

export function LevelBadge({ level }: { level: RiskLevel | string }) {
  const l = (level in LEVEL_COLOR ? level : "UNKNOWN") as RiskLevel;
  const dark = l === "WATCH" || l === "WARNING";
  return (
    <span className="inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: LEVEL_COLOR[l], color: dark ? "#1a1a1a" : "#fff" }}>
      {level}
    </span>
  );
}

export function StatusDot({ state }: { state: SourceStatus["state"] | "ok" | "degraded" | "offline" | "unknown" }) {
  const c = state === "ok" ? "#4f9d69" : state === "stale" || state === "offline" ? "#d1495b" : state === "degraded" ? "#e8a33d" : "#6c7a89";
  return <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ background: c }} aria-label={state} />;
}

type Variant = "primary" | "secondary" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-sky-600 text-white hover:bg-sky-500",
  secondary: "bg-white/10 text-slate-100 hover:bg-white/20",
  danger: "bg-red-600 text-white hover:bg-red-500",
  ghost: "text-slate-300 hover:bg-white/10",
};

export function Button({ variant = "secondary", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button {...p} className={`rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`} />;
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-md border border-white/15 bg-black/30 px-2.5 py-1.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none";

export function Notice({ kind = "info", children }: { kind?: "info" | "error" | "ok" | "warn"; children: React.ReactNode }) {
  const cls = { info: "border-sky-500/40 bg-sky-500/10 text-sky-100", error: "border-red-500/40 bg-red-500/10 text-red-100",
                ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100", warn: "border-amber-500/40 bg-amber-500/10 text-amber-100" }[kind];
  return <div className={`rounded-lg border p-3 text-sm ${cls}`}>{children}</div>;
}

export function SignInPrompt({ role, action }: { role: string; action: string }) {
  return (
    <Notice kind="info">
      <Link href="/login" className="font-semibold underline">Sign in</Link> as {role} or higher to {action}.
    </Notice>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-4 text-sm text-slate-400">{children}</p>;
}

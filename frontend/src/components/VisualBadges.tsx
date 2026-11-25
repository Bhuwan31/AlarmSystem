import { ALERT_COLOR, RISK_COLOR, type Risk } from "@/lib/visual";

export function RiskBadge({ risk }: { risk: Risk }) {
  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-bold" style={{ background: RISK_COLOR[risk], color: risk === "MODERATE" ? "#111" : "#fff" }}>
      {risk} RISK
    </span>
  );
}

export function AlertBadge({ level }: { level: string }) {
  const dark = level === "WATCH" || level === "WARNING";
  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-bold" style={{ background: ALERT_COLOR[level] ?? "#6c7a89", color: dark ? "#111" : "#fff" }}>
      {level}
    </span>
  );
}

export function StatusPill({ status }: { status: string }) {
  const c = { PROPOSED: "bg-amber-400/20 text-amber-200", ACTIVE: "bg-red-500/20 text-red-200", CLOSED: "bg-white/10 text-slate-300",
              REJECTED: "bg-white/5 text-slate-500", SCHEDULED: "bg-sky-500/20 text-sky-200", SENT: "bg-emerald-500/20 text-emerald-200",
              CANCELLED: "bg-white/5 text-slate-500", FAILED: "bg-red-500/20 text-red-200", SENDING: "bg-sky-500/20 text-sky-200" }[status]
    ?? "bg-white/10 text-slate-300";
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${c}`}>{status}</span>;
}

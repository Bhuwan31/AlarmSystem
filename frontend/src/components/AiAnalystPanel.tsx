"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago } from "@/lib/colors";
import { Button, LevelBadge, Notice } from "./ui";

export interface AiFinding {
  area: string; lat: number; lon: number; severity: string; confidence: string; hazard: string;
  summary: string; evidence: string[]; recommended_action: string; station_ids: number[];
}
interface Analysis {
  id: string; trigger: string; model: string; started_at: string; finished_at: string; overall_level: string;
  headline: string; summary: string; findings: AiFinding[]; data_gaps: string[]; tool_calls: number;
}
interface AiStatus { configured: boolean; enabled: boolean; model: string; interval_minutes: number; last_run_at: string | null; last_status: string | null }

const HAZARD: Record<string, string> = { flood: "🌊 flood", heavy_rain: "🌧 heavy rain", heat: "🔥 heat", wind: "💨 wind", cold: "❄ cold", data_gap: "⚠ data gap", other: "• other" };

/** Latest advisory findings from the AI analyst, shown above the warnings list. */
export default function AiAnalystPanel({ onProposed }: { onProposed?: () => void }) {
  const { can, api } = useAuth();
  const { data: status } = useSWR<AiStatus>("/api/v1/ai/status", fetcher, { refreshInterval: 60_000 });
  const { data, mutate } = useSWR<{ analysis: Analysis | null; running: boolean }>("/api/v1/ai/analyses/latest", fetcher,
    { refreshInterval: (d) => (d?.running ? 5_000 : 60_000) });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const a = data?.analysis;

  async function runNow() {
    setMsg(null);
    try { await api("/api/v1/ai/analyses/run", { method: "POST" }); setMsg({ kind: "ok", text: "Analysis started — results appear here in a minute or two." }); mutate(); }
    catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  async function propose(f: AiFinding) {
    const level = f.severity === "NORMAL" ? "WATCH" : f.severity;
    try {
      await api("/api/v1/warnings", { method: "POST", body: { station_id: f.station_ids[0], level, valid_hours: 6,
        note: `AI analyst (${f.confidence} confidence): ${f.summary}`.slice(0, 500) } });
      setMsg({ kind: "ok", text: `Proposal created for ${f.area}. It still needs human approval below.` }); onProposed?.();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  return (
    <section className="rounded-xl border border-violet-400/30 bg-violet-500/[0.06] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">✦ AI analyst <span className="rounded bg-violet-400/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-violet-200">advisory</span></h2>
          <p className="text-xs text-slate-400">
            Reviews every gauge, device, satellite and weather input{status?.configured ? ` every ${status.interval_minutes} min with ${status.model}` : ""}.
            It cannot issue or approve warnings.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data?.running && <span className="animate-pulse text-xs text-violet-200">Analysing…</span>}
          {can("operator") && status?.configured && <Button onClick={runNow} disabled={data?.running}>Run now</Button>}
          <Link href="/assistant" className="rounded-md px-3 py-1.5 text-sm text-violet-200 hover:bg-white/10">Ask the assistant →</Link>
        </div>
      </div>

      {status && !status.configured && (
        <div className="mt-3"><Notice kind="info">AI is switched off. Add <code>GEMINI_API_KEY</code> (free, from aistudio.google.com) or <code>ANTHROPIC_API_KEY</code> to <code>.env</code> and restart the backend (<code>docker compose up -d backend</code>) to enable the analyst and the assistant.</Notice></div>
      )}
      {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}

      {a ? (
        <div className="mt-3 space-y-3">
          <div className="rounded-lg bg-black/20 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <LevelBadge level={a.overall_level} />
              <span className="font-medium">{a.headline}</span>
              <span className="text-xs text-slate-400">· {ago(a.finished_at)} · {a.tool_calls} data checks · {a.trigger}</span>
            </div>
            <p className="mt-2 whitespace-pre-line text-sm text-slate-300">{a.summary}</p>
            {a.data_gaps.length > 0 && <p className="mt-2 text-xs text-amber-200">Data gaps: {a.data_gaps.join(" · ")}</p>}
          </div>
          {a.findings.length > 0 && (
            <div className="grid gap-2 lg:grid-cols-2">
              {a.findings.map((f, i) => (
                <article key={i} className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-semibold">{f.area}</div>
                    <div className="flex items-center gap-1 text-[10px]"><span className="text-slate-400">{HAZARD[f.hazard] ?? f.hazard}</span><LevelBadge level={f.severity} /><span className="rounded bg-white/10 px-1">{f.confidence}</span></div>
                  </div>
                  <p className="mt-1 text-slate-300">{f.summary}</p>
                  {f.evidence.length > 0 && <ul className="mt-1 list-inside list-disc text-xs text-slate-400">{f.evidence.map((e, j) => <li key={j}>{e}</li>)}</ul>}
                  <p className="mt-1 text-xs"><span className="text-slate-400">Suggested action:</span> {f.recommended_action}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    {f.station_ids.slice(0, 3).map((id) => <Link key={id} href={`/stations/${id}`} className="text-sky-300 hover:underline">station {id} →</Link>)}
                    {can("operator") && f.station_ids.length > 0 && f.severity !== "NORMAL" && (
                      <button onClick={() => propose(f)} className="text-violet-200 hover:underline">Create proposal for approval</button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      ) : status?.configured && <p className="mt-3 text-sm text-slate-400">{data?.running ? "First analysis is running…" : "No analysis yet. The first one runs about two minutes after the backend starts."}</p>}
    </section>
  );
}

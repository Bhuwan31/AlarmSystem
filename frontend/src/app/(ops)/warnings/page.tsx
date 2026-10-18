"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Button, Empty, Field, inputCls, LevelBadge, Notice, PageHeader, Panel, SignInPrompt } from "@/components/ui";
import type { Warning } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago } from "@/lib/colors";
import { useRivers, useWarnings } from "@/lib/hooks";

type W = Warning & { proposed_by: string; rejection_reason: string | null; cancel_reason: string | null; valid_from: string | null };

export default function WarningsPage() {
  const [tab, setTab] = useState<"current" | "history">("current");
  const { data: current, mutate: m1 } = useWarnings();
  const { data: history, mutate: m2 } = useWarnings("all");
  const list = (tab === "current" ? current : history) as W[] | undefined;
  const refresh = () => { m1(); m2(); };

  return (
    <div className="space-y-4">
      <PageHeader title="Warnings" subtitle="Proposals come from the risk engine or operators. WARNING needs 1 approver; CRITICAL needs 2 different approvers signed in with two-factor." />
      <div className="flex gap-2" role="tablist">
        {(["current", "history"] as const).map((t) => (
          <Button key={t} role="tab" aria-selected={tab === t} variant={tab === t ? "primary" : "secondary"} onClick={() => setTab(t)}>
            {t === "current" ? `Active & proposed (${current?.length ?? 0})` : "History (30 days)"}
          </Button>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-3">
          {!list?.length && <Empty>No warnings in this view.</Empty>}
          {list?.map((w) => <WarningCard key={w.id} w={w} onChange={refresh} />)}
        </div>
        <ManualWarning onCreated={refresh} />
      </div>
    </div>
  );
}

function WarningCard({ w, onChange }: { w: W; onChange: () => void }) {
  const { user, can, mfa, api } = useAuth();
  const [lang, setLang] = useState<"en" | "ne">("en");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<"reject" | "cancel" | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const needed = w.level === "CRITICAL" ? 2 : 1;
  const alreadyApproved = !!user && w.approvers.includes(user.id);

  async function act(path: string, body?: unknown) {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ status: string }>(`/api/v1/warnings/${w.id}/${path}`, { method: "POST", body });
      setMsg({ kind: "ok", text: `Done — status is now ${r.status}.` });
      setMode(null); setReason(""); onChange();
    } catch (e) {
      setMsg({ kind: "error", text: (e as Error).message });
    } finally { setBusy(false); }
  }

  return (
    <article className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link href={`/stations/${w.station_id}`} className="font-semibold hover:underline">{w.station_name}</Link>
          <div className="text-xs text-slate-400">{w.district ?? ""} · {w.source} · created {ago(w.created_at)}{w.valid_until ? ` · valid until ${new Date(w.valid_until).toLocaleString()}` : ""}</div>
        </div>
        <div className="flex items-center gap-1">
          <LevelBadge level={w.level} />
          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px]">{w.status}</span>
          {w.exercise && <span className="rounded bg-amber-400/20 px-1.5 py-0.5 text-[10px] text-amber-300">EXERCISE</span>}
        </div>
      </div>
      <div className="mt-3 rounded-lg bg-black/20 p-3 text-sm">
        <div className="mb-1 flex gap-2 text-[11px]">
          {(["en", "ne"] as const).map((l) => (
            <button key={l} onClick={() => setLang(l)} className={`rounded px-1.5 ${lang === l ? "bg-white/15" : "text-slate-400"}`}>{l === "en" ? "English" : "नेपाली"}</button>
          ))}
        </div>
        <p lang={lang}>{w.message[lang]}</p>
      </div>
      <p className="mt-2 text-xs text-slate-400">Why: {w.reasons.join(" · ") || "—"}</p>
      {w.status === "PROPOSED" && <p className="mt-1 text-xs text-slate-400">Approvals: {w.approvers.length} of {needed}</p>}
      {w.rejection_reason && <p className="mt-1 text-xs text-red-300">Rejected: {w.rejection_reason}</p>}
      {w.cancel_reason && <p className="mt-1 text-xs text-slate-300">Cancelled: {w.cancel_reason} (all-clear sent)</p>}

      {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}

      {(w.status === "PROPOSED" || w.status === "ACTIVE") && (
        <div className="mt-3 space-y-2">
          {!can("approver") ? <SignInPrompt role="approver" action="act on warnings" /> : (
            <>
              <div className="flex flex-wrap gap-2">
                {w.status === "PROPOSED" && (
                  <>
                    <Button variant="primary" disabled={busy || alreadyApproved || (w.level === "CRITICAL" && !mfa)} onClick={() => act("approve")}>
                      {alreadyApproved ? "You approved" : "Approve"}
                    </Button>
                    <Button variant="secondary" disabled={busy} onClick={() => setMode(mode === "reject" ? null : "reject")}>Reject…</Button>
                  </>
                )}
                {w.status === "ACTIVE" && <Button variant="danger" disabled={busy} onClick={() => setMode(mode === "cancel" ? null : "cancel")}>Cancel warning…</Button>}
              </div>
              {w.level === "CRITICAL" && !mfa && w.status === "PROPOSED" && (
                <p className="text-xs text-amber-300">CRITICAL approvals need a two-factor session. Set up two-factor on the Admin page, then sign in again.</p>
              )}
              {mode && (
                <div className="flex flex-wrap items-end gap-2">
                  <Field label={mode === "reject" ? "Reason for rejecting" : "Reason for cancelling (an all-clear goes to everyone who got the warning)"}>
                    <input className={`${inputCls} min-w-64`} value={reason} onChange={(e) => setReason(e.target.value)} />
                  </Field>
                  <Button variant={mode === "cancel" ? "danger" : "primary"} disabled={busy || reason.trim().length < 3} onClick={() => act(mode, { reason })}>
                    Confirm {mode}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </article>
  );
}

function ManualWarning({ onCreated }: { onCreated: () => void }) {
  const { can, api } = useAuth();
  const { data: rivers } = useRivers();
  const [q, setQ] = useState("");
  const [station, setStation] = useState<{ id: number; name: string } | null>(null);
  const [level, setLevel] = useState("WARNING");
  const [hours, setHours] = useState(6);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const matches = useMemo(() => (q.length < 2 ? [] : (rivers?.features ?? [])
    .filter((f) => f.properties.name.toLowerCase().includes(q.toLowerCase())).slice(0, 8)), [q, rivers]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!station) return;
    try {
      await api("/api/v1/warnings", { method: "POST", body: { station_id: station.id, level, valid_hours: hours, note } });
      setMsg({ kind: "ok", text: "Proposal created. It now needs approval." });
      setStation(null); setQ(""); setNote(""); onCreated();
    } catch (err) { setMsg({ kind: "error", text: (err as Error).message }); }
  }

  return (
    <Panel title="Issue a manual warning" note="e.g. an embankment breach reported by phone" className="h-fit">
      {!can("operator") ? <SignInPrompt role="operator" action="propose warnings" /> : (
        <form onSubmit={submit} className="space-y-3">
          <Field label="River reach (station)">
            {station ? (
              <div className="flex items-center justify-between rounded-md bg-white/5 px-2.5 py-1.5 text-sm">
                {station.name}<button type="button" className="text-xs text-sky-300" onClick={() => setStation(null)}>change</button>
              </div>
            ) : (
              <>
                <input className={inputCls} placeholder="Type a station name…" value={q} onChange={(e) => setQ(e.target.value)} />
                {matches.length > 0 && (
                  <ul className="mt-1 max-h-48 overflow-y-auto rounded-md border border-white/10 bg-[#0b1f26] text-sm">
                    {matches.map((f) => (
                      <li key={f.properties.id}>
                        <button type="button" className="w-full px-2.5 py-1.5 text-left hover:bg-white/10" onClick={() => setStation({ id: f.properties.id, name: f.properties.name })}>
                          {f.properties.name} <span className="text-xs text-slate-400">{f.properties.basin}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Level">
              <select className={inputCls} value={level} onChange={(e) => setLevel(e.target.value)}>
                <option>WATCH</option><option>WARNING</option><option>CRITICAL</option>
              </select>
            </Field>
            <Field label="Valid for (hours)">
              <input className={inputCls} type="number" min={1} max={72} value={hours} onChange={(e) => setHours(+e.target.value)} />
            </Field>
          </div>
          <Field label="Note (why)"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} required minLength={3} /></Field>
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          <Button type="submit" variant="primary" disabled={!station || note.trim().length < 3}>Create proposal</Button>
        </form>
      )}
    </Panel>
  );
}

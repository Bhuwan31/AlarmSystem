"use client";

import { useState } from "react";
import useSWR from "swr";

import { Button, Empty, Field, inputCls, Notice, PageHeader, Panel, SignInPrompt } from "@/components/ui";
import { fetcher, type Shelter } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago } from "@/lib/colors";

const STATUS_CLS: Record<Shelter["status"], string> = { open: "bg-emerald-500/20 text-emerald-300", full: "bg-amber-500/20 text-amber-300",
  closed: "bg-slate-500/20 text-slate-300", unsafe: "bg-red-500/20 text-red-300" };

export default function SheltersPage() {
  const { data, mutate } = useSWR<Shelter[]>("/api/v1/shelters", fetcher, { refreshInterval: 60_000 });
  const total = data?.reduce((a, s) => a + (s.status === "open" ? s.free_places : 0), 0) ?? 0;
  return (
    <div className="space-y-4">
      <PageHeader title="Evacuation shelters" subtitle={`${data?.length ?? 0} shelters · ${total} free places in open shelters. Full, closed or unsafe shelters are never recommended to the public.`} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-2">
          {data && !data.length && <Empty>No shelters registered yet. Add the first one with the form.</Empty>}
          {data?.map((s) => <ShelterRow key={s.id} s={s} onChange={() => mutate()} />)}
        </div>
        <AddShelter onAdded={() => mutate()} />
      </div>
    </div>
  );
}

function ShelterRow({ s, onChange }: { s: Shelter; onChange: () => void }) {
  const { can, api } = useAuth();
  const [occ, setOcc] = useState(s.occupancy);
  const [err, setErr] = useState<string | null>(null);
  const pct = s.capacity ? Math.min(100, (s.occupancy / s.capacity) * 100) : 0;
  async function save(body: Record<string, unknown>) {
    setErr(null);
    try { await api(`/api/v1/shelters/${s.id}`, { method: "PATCH", body }); onChange(); } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-semibold">{s.name} {s.name_local && <span className="font-normal text-slate-400">· {s.name_local}</span>}</div>
          <div className="text-xs text-slate-400">{s.district ?? "—"} · {s.lat.toFixed(4)}, {s.lon.toFixed(4)} · {s.contact ?? "no contact"} · updated {ago(s.updated_at)}</div>
          <div className="mt-1 flex gap-1 text-[10px]">
            {s.accessible && <span className="rounded bg-white/10 px-1.5">♿ step-free</span>}
            {s.accepts_livestock && <span className="rounded bg-white/10 px-1.5">livestock</span>}
            {s.has_medical && <span className="rounded bg-white/10 px-1.5">medical</span>}
          </div>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${STATUS_CLS[s.status]}`}>{s.status}</span>
      </div>
      <div className="mt-2">
        <div className="h-2 overflow-hidden rounded bg-white/10"><div className="h-full bg-sky-500" style={{ width: `${pct}%` }} /></div>
        <div className="mt-1 text-xs text-slate-400">{s.occupancy} / {s.capacity} people · {s.free_places} free</div>
      </div>
      {can("operator") && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button className="!px-2" onClick={() => setOcc(Math.max(0, occ - 10))} aria-label="10 fewer">−10</Button>
          <input type="number" min={0} className={`${inputCls} w-24`} value={occ} onChange={(e) => setOcc(+e.target.value)} aria-label="Occupancy" />
          <Button className="!px-2" onClick={() => setOcc(occ + 10)} aria-label="10 more">+10</Button>
          <Button variant="primary" disabled={occ === s.occupancy} onClick={() => save({ occupancy: occ })}>Save occupancy</Button>
          <select className={`${inputCls} w-36`} value={s.status} onChange={(e) => save({ status: e.target.value })} aria-label="Status">
            <option value="open">Open</option><option value="full">Full</option><option value="closed">Closed</option><option value="unsafe">Unsafe</option>
          </select>
        </div>
      )}
      {err && <div className="mt-2"><Notice kind="error">{err}</Notice></div>}
    </div>
  );
}

function AddShelter({ onAdded }: { onAdded: () => void }) {
  const { can, api } = useAuth();
  const [f, setF] = useState({ name: "", name_local: "", district: "", lat: "", lon: "", capacity: "100", contact: "", accessible: false, accepts_livestock: false, has_medical: false });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const set = (k: string, v: unknown) => setF({ ...f, [k]: v });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/api/v1/shelters", { method: "POST", body: { ...f, lat: +f.lat, lon: +f.lon, capacity: +f.capacity,
        name_local: f.name_local || null, district: f.district || null, contact: f.contact || null } });
      setMsg({ kind: "ok", text: "Shelter added." }); setF({ ...f, name: "", name_local: "", lat: "", lon: "" }); onAdded();
    } catch (err) { setMsg({ kind: "error", text: (err as Error).message }); }
  }
  return (
    <Panel title="Add a shelter" className="h-fit">
      {!can("operator") ? <SignInPrompt role="operator" action="manage shelters" /> : (
        <form onSubmit={submit} className="space-y-2">
          <Field label="Name"><input className={inputCls} required minLength={3} value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Local-language name (optional)"><input className={inputCls} value={f.name_local} onChange={(e) => set("name_local", e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Latitude"><input className={inputCls} required type="number" step="any" value={f.lat} onChange={(e) => set("lat", e.target.value)} /></Field>
            <Field label="Longitude"><input className={inputCls} required type="number" step="any" value={f.lon} onChange={(e) => set("lon", e.target.value)} /></Field>
            <Field label="District"><input className={inputCls} value={f.district} onChange={(e) => set("district", e.target.value)} /></Field>
            <Field label="Capacity (people)"><input className={inputCls} required type="number" min={0} value={f.capacity} onChange={(e) => set("capacity", e.target.value)} /></Field>
          </div>
          <Field label="Contact"><input className={inputCls} value={f.contact} onChange={(e) => set("contact", e.target.value)} /></Field>
          <div className="flex flex-wrap gap-3 text-sm">
            {([["accessible", "Step-free access"], ["accepts_livestock", "Takes livestock"], ["has_medical", "Medical support"]] as const).map(([k, l]) => (
              <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={f[k]} onChange={(e) => set(k, e.target.checked)} />{l}</label>
            ))}
          </div>
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
          <Button type="submit" variant="primary">Add shelter</Button>
        </form>
      )}
    </Panel>
  );
}

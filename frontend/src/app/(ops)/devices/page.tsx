"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { Button, Empty, Field, inputCls, Notice, PageHeader, Panel, SignInPrompt, StatusDot } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, fmt } from "@/lib/colors";

interface Device {
  id: string; kind: "gauge" | "siren"; name: string; lat: number; lon: number; station_id: number | null; firmware: string | null;
  battery_v: number | null; rssi_dbm: number | null; last_seen_at: string | null; status: "ok" | "degraded" | "offline" | "unknown"; test_mode: boolean;
}

export default function DevicesPage() {
  const { data, mutate } = useSWR<Device[]>("/api/v1/devices", fetcher, { refreshInterval: 30_000 });
  return (
    <div className="space-y-4">
      <PageHeader title="Field devices" subtitle="Own river gauges and sirens connected over MQTT. A device that misses its heartbeat for 5 minutes is marked offline and raises a data-quality event." />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-white/[0.03] text-left text-xs text-slate-400">
              <tr><th className="py-2 pl-3">Device</th><th>Type</th><th>Status</th><th>Battery</th><th>Signal</th><th>Firmware</th><th>Last seen</th><th className="pr-3" /></tr>
            </thead>
            <tbody>
              {data?.map((d) => <DeviceRow key={d.id} d={d} onChange={() => mutate()} />)}
              {data && !data.length && <tr><td colSpan={8} className="p-4"><Empty>No devices registered yet.</Empty></td></tr>}
            </tbody>
          </table>
        </div>
        <Register onDone={() => mutate()} />
      </div>
    </div>
  );
}

function DeviceRow({ d, onChange }: { d: Device; onChange: () => void }) {
  const { can, api } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  async function selfTest() {
    try { await api(`/api/v1/devices/${d.id}/self-test`, { method: "POST" }); setMsg("Self-test sent (silent chirp)."); onChange(); }
    catch (e) { setMsg((e as Error).message); }
  }
  return (
    <tr className="border-t border-white/5 align-top">
      <td className="py-2 pl-3"><div className="font-medium">{d.name}</div><div className="text-xs text-slate-400">{d.id} · {d.lat.toFixed(4)}, {d.lon.toFixed(4)}</div>
        {d.station_id && <Link href={`/stations/${d.station_id}`} className="text-xs text-sky-300 hover:underline">{d.kind === "gauge" ? "readings" : "covered reach"} →</Link>}</td>
      <td>{d.kind}{d.test_mode && <span className="ml-1 rounded bg-amber-400/20 px-1 text-[10px] text-amber-300">test mode</span>}</td>
      <td><span className="flex items-center gap-1.5"><StatusDot state={d.status} />{d.status}</span></td>
      <td className="tabular-nums">{fmt(d.battery_v, 2, " V")}</td>
      <td className="tabular-nums">{fmt(d.rssi_dbm, 0, " dBm")}</td>
      <td className="text-xs">{d.firmware ?? "—"}</td>
      <td className="text-xs text-slate-400">{ago(d.last_seen_at)}</td>
      <td className="pr-3">
        {d.kind === "siren" && can("operator") && <Button className="!px-2 !py-1 text-xs" onClick={selfTest}>Self-test</Button>}
        {msg && <div className="mt-1 text-[11px] text-slate-300">{msg}</div>}
      </td>
    </tr>
  );
}

function Register({ onDone }: { onDone: () => void }) {
  const { can, api } = useAuth();
  const [f, setF] = useState({ id: "", kind: "gauge", name: "", lat: "", lon: "", station_id: "", warning_level: "", danger_level: "" });
  const [secrets, setSecrets] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string, v: string) => setF({ ...f, [k]: v });
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setSecrets(null);
    const num = (v: string) => (v === "" ? null : +v);
    try {
      const r = await api<Record<string, unknown>>("/api/v1/devices", { method: "POST", body: {
        id: f.id, kind: f.kind, name: f.name, lat: +f.lat, lon: +f.lon, station_id: num(f.station_id),
        warning_level: num(f.warning_level), danger_level: num(f.danger_level) } });
      setSecrets(r); onDone();
    } catch (e2) { setErr((e2 as Error).message); }
  }
  return (
    <Panel title="Register a device" className="h-fit">
      {!can("admin") ? <SignInPrompt role="admin" action="register devices" /> : (
        <form onSubmit={submit} className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <Field label="Device id" hint="lowercase, e.g. gauge-002"><input className={inputCls} required pattern="[a-z0-9-]{3,40}" value={f.id} onChange={(e) => set("id", e.target.value)} /></Field>
            <Field label="Type"><select className={inputCls} value={f.kind} onChange={(e) => set("kind", e.target.value)}><option value="gauge">River gauge</option><option value="siren">Siren</option></select></Field>
          </div>
          <Field label="Name"><input className={inputCls} required minLength={3} value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Latitude"><input className={inputCls} required type="number" step="any" value={f.lat} onChange={(e) => set("lat", e.target.value)} /></Field>
            <Field label="Longitude"><input className={inputCls} required type="number" step="any" value={f.lon} onChange={(e) => set("lon", e.target.value)} /></Field>
          </div>
          {f.kind === "gauge" ? (
            <div className="grid grid-cols-2 gap-2">
              <Field label="Warning level (m)"><input className={inputCls} type="number" step="any" value={f.warning_level} onChange={(e) => set("warning_level", e.target.value)} /></Field>
              <Field label="Danger level (m)"><input className={inputCls} type="number" step="any" value={f.danger_level} onChange={(e) => set("danger_level", e.target.value)} /></Field>
            </div>
          ) : (
            <Field label="Station id of the river reach it covers" hint="Find the id in the address of a station page (/stations/…)">
              <input className={inputCls} required type="number" value={f.station_id} onChange={(e) => set("station_id", e.target.value)} />
            </Field>
          )}
          {err && <Notice kind="error">{err}</Notice>}
          {secrets && (
            <Notice kind="warn">
              <b>Copy these now — they are shown only once.</b>
              <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[11px]">{JSON.stringify(secrets, null, 2)}</pre>
            </Notice>
          )}
          <Button type="submit" variant="primary">Register</Button>
        </form>
      )}
    </Panel>
  );
}

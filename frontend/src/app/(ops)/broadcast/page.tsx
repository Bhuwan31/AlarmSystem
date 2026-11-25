"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { AlertBadge, StatusPill } from "@/components/VisualBadges";
import { Button, Empty, Field, inputCls, Notice, PageHeader, Panel, SignInPrompt } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ALERT_COLOR, type Areas, fmtTime, isoLocal } from "@/lib/visual";

const VisualMap = dynamic(() => import("@/components/VisualMap"), { ssr: false });

type Target = "country" | "province" | "district" | "city" | "point";
type Level = "INFO" | "WATCH" | "WARNING" | "CRITICAL";
type Status = "PROPOSED" | "SCHEDULED" | "SENDING" | "SENT" | "CANCELLED" | "FAILED" | "REJECTED";
interface Broadcast {
  id: string; target_type: Target; target_value: string | null; radius_km: number | null; level: Level; title: string; message: string;
  status: Status; exercise: boolean; recipients: number | null; send_at: string; valid_until: string | null; sent_at: string | null;
  created_at: string; updated_at: string | null; error: string | null; created_by: string; lat: number | null; lon: number | null;
  source: "operator" | "ai_analyst"; area_label: string | null; hazard: string | null; edited: boolean;
  ai_reason: { summary?: string; evidence?: string[]; confidence?: string; recommended_action?: string } | null;
  original_level: Level | null; original_title: string | null; original_message: string | null; original_radius_km: number | null;
  reviewed_by: string | null; reviewed_at: string | null; review_note: string | null; cancelled_by: string | null;
}
interface Delivery { status: string; delivery: Record<string, number> | null; send_at: string }

const LEVELS: Level[] = ["INFO", "WATCH", "WARNING", "CRITICAL"];
const TEMPLATES: Record<Level, { title: string; message: string }> = {
  INFO: { title: "Information", message: "Please stay informed about weather conditions in your area and follow guidance from local authorities." },
  WATCH: { title: "FLOOD WATCH", message: "Heavy rain is possible. Flooding may develop in low-lying areas and near rivers. Prepare an emergency bag and stay informed." },
  WARNING: { title: "FLOOD WARNING", message: "Flooding is expected or occurring. Avoid rivers, streams and flooded roads. Move valuables and people to higher ground and be ready to evacuate." },
  CRITICAL: { title: "CRITICAL FLOOD ALERT", message: "Dangerous flooding. Move to higher ground or a safe shelter NOW. Do not walk or drive through flood water. Follow instructions from police and local officials." },
};
const HISTORY_FILTERS: { key: string; label: string; match: (s: Status) => boolean }[] = [
  { key: "all", label: "All", match: (s) => s !== "PROPOSED" },
  { key: "sent", label: "Sent", match: (s) => s === "SENT" },
  { key: "rejected", label: "Rejected", match: (s) => s === "REJECTED" },
  { key: "scheduled", label: "Scheduled", match: (s) => s === "SCHEDULED" || s === "SENDING" },
  { key: "other", label: "Cancelled / failed", match: (s) => s === "CANCELLED" || s === "FAILED" },
];

function deliveryText(r: Delivery): string {
  return r.status === "SENT" ? `Sent — ${Object.entries(r.delivery ?? {}).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join(", ") || "no subscribers in the area"}`
    : `Scheduled for ${fmtTime(r.send_at)}`;
}

function targetText(b: Broadcast): string {
  if (b.target_type === "country") return "whole country";
  if (b.target_type === "point") return `${b.radius_km ?? "?"} km around ${b.area_label ?? "map point"}`;
  return `${b.target_value}${b.radius_km ? ` (${b.radius_km} km)` : ""}`;
}

export default function BroadcastPage() {
  const { can, ready } = useAuth();
  if (!ready) return null;
  if (!can("approver")) return (<><PageHeader title="Area messages" /><SignInPrompt role="approver" action="send messages to an area" /></>);
  return <AreaMessages />;
}

function AreaMessages() {
  const { api } = useAuth();
  const { data: list, mutate } = useSWR<Broadcast[]>("broadcasts", () => api<Broadcast[]>("/api/v1/visual-disaster/broadcasts?limit=300"), { refreshInterval: 15_000 });
  const { mutate: mutateKey } = useSWRConfig();
  const [show, setShow] = useState<Broadcast | null>(null);
  const drafts = (list ?? []).filter((b) => b.status === "PROPOSED")
    .sort((a, b) => LEVELS.indexOf(b.level) - LEVELS.indexOf(a.level) || b.created_at.localeCompare(a.created_at));
  const refresh = () => { mutate(); mutateKey("pending-messages"); };      // also clears the banner / menu badge

  return (
    <div className="space-y-5">
      <PageHeader title="Area messages" subtitle="Messages the AI drafted for risk areas wait here for your decision: edit them, send now, schedule or reject. You can also write your own message for a district, city, province, the whole country or a point on the map." />
      <section id="drafts" className="scroll-mt-20">
        <Panel title={`Waiting for your decision${drafts.length ? ` (${drafts.length})` : ""}`}
               note="Drafted by the AI analyst from live data. Nothing is sent until you press Send.">
          {!list ? <Empty>Loading…</Empty> : drafts.length === 0 ? <Empty>No AI-drafted messages waiting.</Empty> : (
            <div className="space-y-4">{drafts.map((b) => <DraftCard key={b.id} b={b} onDone={refresh} onShow={() => setShow(b)} />)}</div>
          )}
        </Panel>
      </section>
      <Composer onSent={refresh} show={show} />
      <History list={list} onChange={refresh} onShow={setShow} />
    </div>
  );
}

/** An AI draft (waiting or previously rejected): every field editable, then send now / schedule / save / reject. */
function DraftCard({ b, onDone, onShow }: { b: Broadcast; onDone: () => void; onShow: () => void }) {
  const { api, mfa } = useAuth();
  const [level, setLevel] = useState<Level>(b.level);
  const [title, setTitle] = useState(b.title);
  const [message, setMessage] = useState(b.message);
  const [radius, setRadius] = useState<number>(b.radius_km ?? 10);
  const [validHours, setValidHours] = useState(12);
  const [when, setWhen] = useState<"now" | "later">("now");
  const [sendAt, setSendAt] = useState("");
  const [count, setCount] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const point = b.target_type === "point";
  const dirty = level !== b.level || title !== b.title || message !== b.message || (point && radius !== b.radius_km);
  const edits = { level, title, message, ...(point ? { radius_km: radius } : {}) };

  async function act(fn: () => Promise<string>) {
    setBusy(true); setMsg(null);
    try { setMsg({ kind: "ok", text: await fn() }); onDone(); } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } finally { setBusy(false); }
  }
  async function countRecipients() {
    try {
      const body = point ? { target_type: "point", latitude: b.lat, longitude: b.lon, radius_km: radius, level, title, message }
        : { target_type: b.target_type, target_value: b.target_value, radius_km: b.radius_km, level, title, message };
      setCount((await api<{ recipients: number }>("/api/v1/visual-disaster/broadcasts/preview", { method: "POST", body })).recipients);
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }
  const send = () => {
    if (!confirm(`${when === "now" ? "Send now" : "Schedule"} this ${level} message to subscribers in ${point ? `${radius} km around ${b.area_label ?? "the area"}` : targetText(b)}?`)) return;
    const start = when === "later" && sendAt ? new Date(sendAt) : new Date();
    act(async () => deliveryText(await api<Delivery>(`/api/v1/visual-disaster/broadcasts/${b.id}/approve`, { method: "POST", body: {
      ...edits, send_at: when === "later" && sendAt ? isoLocal(start) : null,
      valid_until: validHours ? isoLocal(new Date(start.getTime() + validHours * 3600_000)) : null } })));
  };
  const save = () => act(async () => { await api(`/api/v1/visual-disaster/broadcasts/${b.id}`, { method: "PATCH", body: edits }); return "Changes saved."; });
  const reject = () => {
    const note = prompt("Reason for rejecting (optional). The draft stays in the history and can still be sent later.");
    if (note === null) return;
    act(async () => { await api(`/api/v1/visual-disaster/broadcasts/${b.id}/reject`, { method: "POST", body: { note: note || null } }); return "Rejected — kept in the history."; });
  };

  return (
    <article className="rounded-lg border border-white/10 bg-black/20 p-3" style={{ borderLeft: `4px solid ${ALERT_COLOR[b.level] ?? "#888"}` }}>
      <header className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <StatusPill status={b.status} /><AlertBadge level={b.level} />
        <span className="font-medium">{b.area_label ?? targetText(b)}</span>
        <span className="text-xs text-slate-400">
          {b.source === "ai_analyst" ? "AI draft" : "Operator"} · {fmtTime(b.created_at)}{b.updated_at && b.updated_at !== b.created_at ? ` · updated ${fmtTime(b.updated_at)}` : ""}
          {b.ai_reason?.confidence ? ` · confidence ${b.ai_reason.confidence.toLowerCase()}` : ""}{b.exercise ? " · exercise" : ""}
        </span>
        {point && <Button variant="ghost" className="ml-auto" onClick={onShow}>Show on map</Button>}
      </header>
      {b.status === "REJECTED" && <p className="mb-2 text-xs text-slate-400">Rejected by {b.reviewed_by} at {fmtTime(b.reviewed_at)}{b.review_note ? ` — “${b.review_note}”` : ""}. You can still edit and send it.</p>}
      {b.ai_reason?.summary && (
        <details className="mb-3 rounded-md bg-white/5 p-2 text-xs text-slate-300" open>
          <summary className="cursor-pointer font-medium text-slate-200">What the AI saw</summary>
          <p className="mt-1">{b.ai_reason.summary}</p>
          {!!b.ai_reason.evidence?.length && <ul className="mt-1 list-disc pl-4">{b.ai_reason.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>}
          {b.ai_reason.recommended_action && <p className="mt-1"><b>Suggested action for officials:</b> {b.ai_reason.recommended_action}</p>}
        </details>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Level"><select className={inputCls} value={level} onChange={(e) => setLevel(e.target.value as Level)}>{LEVELS.map((l) => <option key={l}>{l}</option>)}</select></Field>
        {point && <Field label="Radius (km)"><input type="number" min={1} max={200} className={inputCls} value={radius} onChange={(e) => { setRadius(+e.target.value); setCount(null); }} /></Field>}
        <Field label="Valid for (hours)"><input type="number" min={1} max={168} className={inputCls} value={validHours} onChange={(e) => setValidHours(+e.target.value)} /></Field>
      </div>
      <div className="mt-3 space-y-3">
        <Field label="Title"><input className={inputCls} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Message to residents" hint="The system adds the validity time and a source line.">
          <textarea className={`${inputCls} h-28`} value={message} maxLength={2000} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        {b.edited && b.original_message && (
          <details className="text-xs text-slate-400"><summary className="cursor-pointer">Edited — show the AI&apos;s original draft</summary>
            <p className="mt-1 whitespace-pre-wrap">{b.original_level} · {b.original_title}{b.original_radius_km ? ` · ${b.original_radius_km} km` : ""}{"\n"}{b.original_message}</p>
          </details>
        )}
        <fieldset className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-1.5"><input type="radio" checked={when === "now"} onChange={() => setWhen("now")} />Send now</label>
          <label className="flex items-center gap-1.5"><input type="radio" checked={when === "later"} onChange={() => setWhen("later")} />Schedule</label>
          {when === "later" && <input type="datetime-local" className={`${inputCls} w-auto`} value={sendAt} onChange={(e) => setSendAt(e.target.value)} />}
        </fieldset>
        {level === "CRITICAL" && !mfa && <Notice kind="warn">CRITICAL messages need a two-factor session.</Notice>}
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={countRecipients}>Count recipients</Button>
          {count != null && <span className="text-sm text-slate-300">{count} subscriber{count === 1 ? "" : "s"}</span>}
          <span className="ml-auto flex flex-wrap gap-2">
            {dirty && <Button disabled={busy} onClick={save}>Save edits</Button>}
            {b.status === "PROPOSED" && <Button variant="ghost" disabled={busy} onClick={reject}>Reject</Button>}
            <Button variant="danger" disabled={busy || (when === "later" && !sendAt) || (level === "CRITICAL" && !mfa) || message.trim().length < 10}
                    onClick={send}>{when === "now" ? "Send now" : "Schedule"}</Button>
          </span>
        </div>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </div>
    </article>
  );
}

/** Operator-written message to a country / province / district / city / map point. */
function Composer({ onSent, show }: { onSent: () => void; show: Broadcast | null }) {
  const { api, mfa } = useAuth();
  const { data: areas } = useSWR<Areas>("/api/v1/visual-disaster/geo/areas", (p: string) => api<Areas>(p));
  const [target, setTarget] = useState<Target>("district");
  const [value, setValue] = useState("Kathmandu");
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [radius, setRadius] = useState<number>(5);
  const [level, setLevel] = useState<Level>("WARNING");
  const [title, setTitle] = useState(TEMPLATES.WARNING.title);
  const [message, setMessage] = useState(TEMPLATES.WARNING.message);
  const [when, setWhen] = useState<"now" | "later">("now");
  const [sendAt, setSendAt] = useState("");
  const [validHours, setValidHours] = useState(12);
  const [preview, setPreview] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const city = areas?.cities.find((c) => c.name === value);
  const district = areas?.districts.find((d) => d.name === value);
  const center = target === "point" ? point : target === "city" && city ? { lat: city.lat, lon: city.lon } : target === "district" && district ? { lat: district.lat, lon: district.lon } : null;
  const shown = show && show.lat != null && show.lon != null ? show : null;
  const focus = shown ? { lat: shown.lat!, lon: shown.lon!, zoom: 9 } : center ? { lat: center.lat, lon: center.lon, zoom: target === "district" ? 9 : 10 } : null;

  function payload() {
    const start = when === "later" && sendAt ? new Date(sendAt) : new Date();
    return {
      target_type: target, target_value: ["province", "district", "city"].includes(target) ? value : null,
      latitude: target === "point" ? point?.lat : null, longitude: target === "point" ? point?.lon : null,
      radius_km: target === "point" || target === "city" ? radius : null, level, title, message,
      send_at: when === "later" && sendAt ? isoLocal(start) : null,
      valid_until: validHours ? isoLocal(new Date(start.getTime() + validHours * 3600_000)) : null,
    };
  }

  function changeTarget(t: Target) {
    setTarget(t); setPreview(null);
    if (t === "province") setValue(areas?.provinces[2] ?? "Bagmati");
    if (t === "district") setValue("Kathmandu");
    if (t === "city") { setValue("Kathmandu"); setRadius(8); }
  }

  async function doPreview() {
    setMsg(null);
    try { setPreview((await api<{ recipients: number }>("/api/v1/visual-disaster/broadcasts/preview", { method: "POST", body: payload() })).recipients); }
    catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  async function send() {
    const label = target === "country" ? "the whole country" : target === "point" ? `${radius} km around the map point` : `${value}${target === "city" ? ` (${radius} km)` : ` ${target}`}`;
    if (!confirm(`${when === "now" ? "Send now" : "Schedule"} a ${level} message to subscribers in ${label}?`)) return;
    setBusy(true); setMsg(null);
    try {
      setMsg({ kind: "ok", text: deliveryText(await api<Delivery>("/api/v1/visual-disaster/broadcasts", { method: "POST", body: payload() })) });
      onSent();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-5 [&>*]:min-w-0 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel title="Write your own message">
        <div className="space-y-3">
          <fieldset>
            <legend className="mb-1 text-xs text-slate-400">Send to</legend>
            <div className="flex flex-wrap gap-1.5">
              {(["country", "province", "district", "city", "point"] as const).map((t) => (
                <Button key={t} variant={target === t ? "primary" : "secondary"} onClick={() => changeTarget(t)}>
                  {{ country: "Whole country", province: "Province", district: "District", city: "City", point: "Map point" }[t]}
                </Button>
              ))}
            </div>
          </fieldset>
          {target === "province" && (
            <Field label="Province"><select className={inputCls} value={value} onChange={(e) => { setValue(e.target.value); setPreview(null); }}>
              {areas?.provinces.map((p) => <option key={p}>{p}</option>)}</select></Field>
          )}
          {target === "district" && (
            <Field label="District" hint="Reaches subscribers who chose this district.">
              <select className={inputCls} value={value} onChange={(e) => { setValue(e.target.value); setPreview(null); }}>
                {areas?.provinces.map((p) => (
                  <optgroup key={p} label={p}>{areas.districts.filter((d) => d.province === p).map((d) => <option key={d.name}>{d.name}</option>)}</optgroup>
                ))}
              </select>
            </Field>
          )}
          {target === "city" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="City"><select className={inputCls} value={value} onChange={(e) => { setValue(e.target.value); setRadius(areas?.cities.find((c) => c.name === e.target.value)?.radius_km ?? 5); setPreview(null); }}>
                {areas?.cities.map((c) => <option key={c.name}>{c.name}</option>)}</select></Field>
              <Field label="Radius (km)"><input type="number" min={1} max={50} className={inputCls} value={radius} onChange={(e) => { setRadius(+e.target.value); setPreview(null); }} /></Field>
            </div>
          )}
          {target === "point" && (
            <Field label="Radius (km)" hint="Click the map to place the centre.">
              <input type="number" min={1} max={200} className={inputCls} value={radius} onChange={(e) => { setRadius(+e.target.value); setPreview(null); }} />
            </Field>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Level">
              <select className={inputCls} value={level} onChange={(e) => { const l = e.target.value as Level; setLevel(l); setTitle(TEMPLATES[l].title); setMessage(TEMPLATES[l].message); }}>
                {LEVELS.map((l) => <option key={l}>{l}</option>)}
              </select>
            </Field>
            <Field label="Valid for (hours)"><input type="number" min={0} max={168} className={inputCls} value={validHours} onChange={(e) => setValidHours(+e.target.value)} /></Field>
          </div>
          <Field label="Title"><input className={inputCls} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Message" hint="The system adds the validity time and a source line.">
            <textarea className={`${inputCls} h-32`} value={message} maxLength={2000} onChange={(e) => setMessage(e.target.value)} />
          </Field>
          <fieldset className="flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" checked={when === "now"} onChange={() => setWhen("now")} />Send now</label>
            <label className="flex items-center gap-1.5"><input type="radio" checked={when === "later"} onChange={() => setWhen("later")} />Schedule</label>
            {when === "later" && <input type="datetime-local" className={`${inputCls} w-auto`} value={sendAt} onChange={(e) => setSendAt(e.target.value)} />}
          </fieldset>
          {level === "CRITICAL" && !mfa && <Notice kind="warn">CRITICAL messages need a two-factor session.</Notice>}
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={doPreview} disabled={target === "point" && !point}>Count recipients</Button>
            {preview != null && <span className="text-sm text-slate-300">{preview} subscriber{preview === 1 ? "" : "s"} will receive it</span>}
            <Button variant="danger" className="ml-auto" disabled={busy || (target === "point" && !point) || (when === "later" && !sendAt) || (level === "CRITICAL" && !mfa)} onClick={send}>
              {when === "now" ? "Send now" : "Schedule"}
            </Button>
          </div>
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        </div>
      </Panel>
      <div className="space-y-2">
        <VisualMap className="h-96" onPick={(lat, lon) => { if (target === "point") { setPoint({ lat, lon }); setPreview(null); } }}
          points={[
            ...(center ? [{ id: "c", lon: center.lon, lat: center.lat, color: ALERT_COLOR[level], kind: "pick" as const, label: "Target" }] : []),
            ...(shown ? [{ id: shown.id, lon: shown.lon!, lat: shown.lat!, color: ALERT_COLOR[shown.level], kind: "incident" as const, label: shown.title }] : []),
          ]}
          circles={[
            ...(center && (target === "point" || target === "city") ? [{ id: "r", lon: center.lon, lat: center.lat, km: radius, color: ALERT_COLOR[level] }] : []),
            ...(shown && shown.radius_km ? [{ id: "s", lon: shown.lon!, lat: shown.lat!, km: shown.radius_km, color: ALERT_COLOR[shown.level], dashed: true }] : []),
          ]}
          focus={focus} />
        <p className="text-xs text-slate-400">{shown ? `Dashed circle: ${shown.title}.` : "Pick “Map point” and click the map to target an exact place."}</p>
      </div>
    </div>
  );
}

/** Everything decided so far: sent, rejected, scheduled, cancelled — with times, who decided, and the message text. */
function History({ list, onChange, onShow }: { list: Broadcast[] | undefined; onChange: () => void; onShow: (b: Broadcast) => void }) {
  const { api } = useAuth();
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const f = HISTORY_FILTERS.find((x) => x.key === filter)!;
  const rows = (list ?? []).filter((b) => f.match(b.status));
  const n = (key: string) => (list ?? []).filter((b) => HISTORY_FILTERS.find((x) => x.key === key)!.match(b.status)).length;
  return (
    <Panel title="History">
      <div className="mb-3 flex flex-wrap gap-1.5">
        {HISTORY_FILTERS.map((x) => (
          <Button key={x.key} variant={filter === x.key ? "primary" : "secondary"} onClick={() => setFilter(x.key)}>{x.label} ({n(x.key)})</Button>
        ))}
      </div>
      {rows.length === 0 ? <Empty>Nothing here yet.</Empty> : (
        <ul className="divide-y divide-white/5 text-sm">
          {rows.map((b) => (
            <li key={b.id} className="py-2">
              <button className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen(open === b.id ? null : b.id)} aria-expanded={open === b.id}>
                <StatusPill status={b.status} /><AlertBadge level={b.level} />
                <span className="font-medium">{b.title}</span>
                <span className="text-xs text-slate-400">
                  → {targetText(b)} · {b.source === "ai_analyst" ? `AI draft${b.edited ? ", edited" : ""}` : "operator"}
                  {" · "}{b.status === "SENT" ? `sent ${fmtTime(b.sent_at)} to ${b.recipients ?? 0}`
                    : b.status === "REJECTED" ? `rejected ${fmtTime(b.reviewed_at)}`
                    : b.status === "SCHEDULED" ? `for ${fmtTime(b.send_at)}` : fmtTime(b.updated_at ?? b.created_at)}
                  {b.exercise ? " · exercise" : ""}
                </span>
                <span className="ml-auto text-xs text-slate-500">{open === b.id ? "▲" : "▼"}</span>
              </button>
              {open === b.id && (
                b.status === "REJECTED" ? <div className="mt-2"><DraftCard b={b} onDone={onChange} onShow={() => onShow(b)} /></div> : (
                  <div className="mt-2 space-y-1 rounded-md bg-white/5 p-3 text-xs text-slate-300">
                    <p className="whitespace-pre-wrap text-sm text-slate-100">{b.message}</p>
                    <p>Created {fmtTime(b.created_at)} by {b.created_by}{b.reviewed_by ? ` · approved by ${b.reviewed_by} at ${fmtTime(b.reviewed_at)}` : ""}
                      {b.valid_until ? ` · valid until ${fmtTime(b.valid_until)}` : ""}{b.cancelled_by ? ` · cancelled by ${b.cancelled_by}` : ""}</p>
                    {b.edited && b.original_message && <p>AI&apos;s original: <i>{b.original_title} — {b.original_message}</i></p>}
                    {b.error && <p className="text-red-300">{b.error}</p>}
                    {b.status === "SCHEDULED" && (
                      <Button variant="ghost" onClick={async () => { await api(`/api/v1/visual-disaster/broadcasts/${b.id}/cancel`, { method: "POST" }); onChange(); }}>Cancel</Button>
                    )}
                  </div>
                )
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

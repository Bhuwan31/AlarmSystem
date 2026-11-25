"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { AlertBadge, RiskBadge, StatusPill } from "@/components/VisualBadges";
import { Button, Empty, Field, inputCls, Notice, PageHeader, Panel, SignInPrompt, Stat } from "@/components/ui";
import { useAuth, SEND_ROLE } from "@/lib/auth";
import { confirmTwice } from "@/lib/confirm";
import {
  ACTION_TEXT, ALERT_COLOR, CORRELATION_TEXT, fmtTime, LOCATION_SOURCE_TEXT, RADII, TIME_SOURCE_TEXT, type AlertLevel, type Incident,
  type Observation,
} from "@/lib/visual";

const VisualMap = dynamic(() => import("@/components/VisualMap"), { ssr: false });
const FILTERS = ["ALL", "PROPOSED", "ACTIVE", "CLOSED", "REJECTED"] as const;

interface Delivery { id: string; name: string; notification_channel: string; notification_status: string; level: string; distance_km: number | null;
  error: string | null; created_at: string; sent_at: string | null; acknowledged_at: string | null }
interface ModelStatus { available: boolean; model_version: string; dqn?: { mode: string; validated_for_alerts: boolean }; cnn?: { validated_for_alerts: boolean };
  dataset?: { version: string; synthetic_only: boolean } }

export default function IncidentsPage() {
  const { can, ready } = useAuth();
  if (!ready) return null;
  if (!can("operator")) return (<><PageHeader title="Visual incidents" /><SignInPrompt role="operator" action="review AI photo detections" /></>);
  return <Dashboard />;
}

function Dashboard() {
  const { api, can } = useAuth();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [selected, setSelected] = useState<string | null>(null);
  const { data: incidents, mutate } = useSWR<Incident[]>("incidents", () => api<Incident[]>("/api/v1/visual-disaster/incidents?limit=300"), { refreshInterval: 10_000 });
  const { data: obs } = useSWR<Observation[]>("all-obs", () => api<Observation[]>("/api/v1/visual-disaster/observations?limit=300"), { refreshInterval: 15_000 });
  const { data: model } = useSWR<ModelStatus>("model-status", () => api<ModelStatus>("/api/v1/visual-disaster/model/status"));

  const shown = useMemo(() => (incidents ?? []).filter((i) => filter === "ALL" || i.incident_status === filter), [incidents, filter]);
  const proposed = incidents?.filter((i) => i.incident_status === "PROPOSED") ?? [];
  const active = incidents?.filter((i) => i.incident_status === "ACTIVE") ?? [];
  const [now] = useState(() => Date.now());
  const day = now - 86400_000;
  const photos24 = obs?.filter((o) => new Date(o.upload_timestamp).getTime() > day).length ?? 0;
  const sel = incidents?.find((i) => i.id === selected) ?? null;

  const points = [
    ...(obs ?? []).filter((o) => o.latitude != null && o.longitude != null && new Date(o.upload_timestamp).getTime() > now - 7 * 86400_000).map((o) => {
      const a = o.analysis;
      const color = !a ? "#6c7a89" : a.alert_level !== "NONE" ? ALERT_COLOR[a.alert_level] : a.recommended_action === "MONITOR" ? ALERT_COLOR.MONITOR : "#4f9d69";
      return { id: o.incident_id ?? `obs:${o.image_id}`, lon: o.longitude!, lat: o.latitude!, color, kind: "observation" as const,
               label: `${a?.classification_label ?? o.processing_status} · ${fmtTime(o.capture_timestamp ?? o.upload_timestamp)}` };
    }),
    ...shown.map((i) => ({ id: i.id, lon: i.longitude, lat: i.latitude, color: ALERT_COLOR[i.alert_level], kind: "incident" as const, ring: i.id === selected,
                           label: `${i.incident_status} ${i.alert_level} — ${i.location_label}` })),
  ];
  const circles = shown.filter((i) => i.incident_status === "PROPOSED" || i.incident_status === "ACTIVE")
    .map((i) => ({ id: i.id, lon: i.longitude, lat: i.latitude, km: i.affected_radius, color: ALERT_COLOR[i.alert_level], dashed: i.incident_status === "PROPOSED" }));

  return (
    <div className="space-y-5">
      <PageHeader title="Visual incidents" subtitle="AI photo detections grouped into incidents. Nothing is sent until an approver reviews the suggested message and presses Send." />
      {proposed.length > 0 && can(SEND_ROLE) && (
        <Notice kind="warn">
          <b>{proposed.length} new detection{proposed.length > 1 ? "s" : ""} waiting for review.</b>{" "}
          {proposed.slice(0, 3).map((i) => (
            <button key={i.id} className="ml-2 underline" onClick={() => setSelected(i.id)}>{i.alert_level} {i.disaster_type.replace("_", " ").toLowerCase()} — {i.location_label}</button>
          ))}
        </Notice>
      )}
      {model && (!model.available || !model.cnn?.validated_for_alerts) && (
        <Notice kind="info">
          {model.available ? <>Image model <b>{model.model_version}</b> is trained on {model.dataset?.synthetic_only ? "synthetic images only" : `dataset ${model.dataset?.version}`} and is
            <b> not validated</b> on real photos; the decision agent runs in <b>{model.dqn?.mode}</b> mode. Treat every detection as a lead to check.</>
            : <>No trained image model is installed; photos are stored for manual review only.</>}
        </Notice>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Awaiting review" value={proposed.length} />
        <Stat label="Active alerts" value={active.length} sub={`${active.reduce((s, i) => s + (i.notified ?? 0), 0)} people notified`} />
        <Stat label="Photos (24 h)" value={photos24} />
        <Stat label="Model" value={model?.available ? "ready" : "—"} sub={model?.dqn?.mode} />
      </div>
      <div className="grid gap-5 [&>*]:min-w-0 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <VisualMap className="h-[420px]" points={points} circles={circles}
            onSelect={(id) => { if (!id.startsWith("obs:")) setSelected(id); }}
            focus={sel ? { lat: sel.latitude, lon: sel.longitude, zoom: 11 } : null} />
          <Legend />
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => <Button key={f} variant={filter === f ? "primary" : "ghost"} onClick={() => setFilter(f)}>{f}</Button>)}
          </div>
          <Panel>
            {!shown.length ? <Empty>No incidents.</Empty> : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-slate-400"><tr><th className="py-1">Status</th><th>Level</th><th>Type</th><th>Place</th><th>Reports</th><th>Radius</th><th>Users</th><th>Detected</th></tr></thead>
                  <tbody className="divide-y divide-white/5">
                    {shown.map((i) => (
                      <tr key={i.id} className={`cursor-pointer hover:bg-white/5 ${i.id === selected ? "bg-sky-500/10" : ""}`} onClick={() => setSelected(i.id)}>
                        <td className="py-1.5"><StatusPill status={i.incident_status} />{i.escalation_suggested && <span className="ml-1 text-[10px] text-red-300">↑ escalate?</span>}</td>
                        <td><AlertBadge level={i.alert_level} /></td>
                        <td className="whitespace-nowrap">{i.disaster_type.replace("_", " ").toLowerCase()}</td>
                        <td className="max-w-[16rem] truncate">{i.location_label}</td>
                        <td className="tabular-nums">{i.report_count}</td>
                        <td className="tabular-nums">{i.affected_radius} km</td>
                        <td className="tabular-nums">{i.incident_status === "ACTIVE" ? `${i.notified} sent` : i.users_in_radius}</td>
                        <td className="whitespace-nowrap text-xs text-slate-400">{fmtTime(i.first_detected_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
        <div>{selected ? <Detail id={selected} onChanged={() => mutate()} /> : <Panel><Empty>Select an incident on the map or in the list.</Empty></Panel>}</div>
      </div>
    </div>
  );
}

function Legend() {
  const items: [string, string][] = [["#4f9d69", "Normal photo"], [ALERT_COLOR.MONITOR, "Monitoring"], [ALERT_COLOR.WATCH, "Watch"],
    [ALERT_COLOR.WARNING, "Flood warning"], [ALERT_COLOR.CRITICAL, "Critical"]];
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-400">
      {items.map(([c, l]) => <span key={l} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: c }} />{l}</span>)}
      <span>● photo · ◆ incident · dashed circle = proposed area · solid = alerted area</span>
    </div>
  );
}

function Detail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { api, can } = useAuth();
  const { data: inc, mutate } = useSWR<Incident>(["incident", id], () => api<Incident>(`/api/v1/visual-disaster/incidents/${id}`), { refreshInterval: 10_000 });
  const { data: deliveries, mutate: mutateDeliveries } = useSWR<Delivery[]>(can(SEND_ROLE) ? ["deliveries", id] : null,
    () => api<Delivery[]>(`/api/v1/visual-disaster/incidents/${id}/notifications`));
  const [level, setLevel] = useState<AlertLevel>("WARNING");
  const [radius, setRadius] = useState<number>(3);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [channels, setChannels] = useState<Record<string, boolean>>({ in_app: true, push: true, sms: true, email: true });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  useEffect(() => {
    // Fill the editable message once per incident (and when the suggestion changes before approval).
    if (!inc) return;
    const key = `${inc.id}:${inc.incident_status}:${inc.suggested_level}:${inc.last_updated_at}`;
    if (loadedFor?.split(":")[0] === inc.id && inc.incident_status === "ACTIVE") return;
    if (loadedFor === key) return;
    const m = inc.sent_message ?? inc.proposed_message;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLevel(inc.incident_status === "ACTIVE" && inc.escalation_suggested ? inc.suggested_level : inc.alert_level);
    setRadius(RADII.includes(inc.affected_radius as 1) ? inc.affected_radius : 3);
    setTitle(m.title); setBody(m.body); setLoadedFor(key); setMsg(null);
  }, [inc, loadedFor]);

  if (!inc) return <Panel>Loading…</Panel>;
  const open = inc.incident_status === "PROPOSED" || inc.incident_status === "ACTIVE";

  async function act(path: string, payload: unknown, ok: string) {
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ delivery?: Record<string, number>; all_clear?: Record<string, number> | null }>(`/api/v1/visual-disaster/incidents/${id}/${path}`, { method: "POST", body: payload });
      const d = r?.delivery ?? r?.all_clear;
      setMsg({ kind: "ok", text: d ? `${ok} — ${Object.entries(d).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join(", ")}` : ok });
      mutate(); mutateDeliveries(); onChanged();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <Panel title={`${inc.disaster_type.replace("_", " ")} — ${inc.location_label}`} note={<StatusPill status={inc.incident_status} />}>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <AlertBadge level={inc.alert_level} /><RiskBadge risk={inc.risk_level} />
          <span className="text-slate-400">{inc.report_count} report{inc.report_count > 1 ? "s" : ""} · confidence up to {Math.round(inc.max_confidence * 100)}% · {inc.district}, {inc.province}</span>
          {inc.exercise && <span className="rounded bg-amber-400/15 px-1.5 text-[10px] font-semibold text-amber-300">EXERCISE</span>}
        </div>
        <p className="mt-2 text-sm text-slate-300">{CORRELATION_TEXT[inc.weather_correlation] ?? inc.weather_correlation}</p>
        {inc.escalation_suggested && <Notice kind="warn">New reports suggest {inc.suggested_level}. Review and send an update if justified.</Notice>}
        <p className="mt-1 text-xs text-slate-500">First detected {fmtTime(inc.first_detected_at)} · updated {fmtTime(inc.last_updated_at)}{inc.approved_at ? ` · approved ${fmtTime(inc.approved_at)}` : ""}</p>
      </Panel>

      <Panel title="Photos and AI analysis">
        <div className="space-y-4">{inc.observations?.map((o) => <ObservationCard key={o.image_id} o={o} />)}</div>
      </Panel>

      {open && can(SEND_ROLE) && (
        <Panel title={inc.incident_status === "PROPOSED" ? "Suggested message — review and send" : "Send an update"}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Alert level">
              <select className={inputCls} value={level} onChange={(e) => setLevel(e.target.value as AlertLevel)}>
                {(["WATCH", "WARNING", "CRITICAL"] as const).map((l) => <option key={l} value={l}>{l}{l === inc.suggested_level ? " (suggested)" : ""}</option>)}
              </select>
            </Field>
            <Field label="Affected radius" hint={`AI suggestion: ${inc.suggested_radius} km. Choose from type, severity, terrain and official guidance.`}>
              <select className={inputCls} value={radius} onChange={(e) => setRadius(+e.target.value)}>
                {RADII.map((r) => <option key={r} value={r}>{r} km — {inc.users_by_radius?.[String(r)] ?? "?"} subscribed users{r === inc.suggested_radius ? " (suggested)" : ""}</option>)}
              </select>
            </Field>
          </div>
          <div className="mt-3 h-56"><VisualMap className="h-56" points={[{ id: inc.id, lon: inc.longitude, lat: inc.latitude, color: ALERT_COLOR[level], kind: "incident", label: inc.location_label }]}
            circles={[{ id: "r", lon: inc.longitude, lat: inc.latitude, km: radius, color: ALERT_COLOR[level] }]} focus={{ lat: inc.latitude, lon: inc.longitude, zoom: radius >= 5 ? 10 : 11.5 }} /></div>
          <Field label="Title"><input className={`${inputCls} mt-3`} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /></Field>
          <Field label="Message" hint="{distance} is replaced with each person's distance from the incident.">
            <textarea className={`${inputCls} h-56 font-mono text-xs`} value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} />
          </Field>
          <fieldset className="mt-2 flex flex-wrap gap-4 text-sm">
            <legend className="mb-1 text-xs text-slate-400">Channels {inc.external_sending_enabled ? "" : "(external channels are SIMULATED on this server)"}</legend>
            {(["in_app", "push", "sms", "email"] as const).map((c) => (
              <label key={c} className="flex items-center gap-1.5">
                <input type="checkbox" checked={c === "in_app" || channels[c]} disabled={c === "in_app"} onChange={(e) => setChannels({ ...channels, [c]: e.target.checked })} />
                {c.replace("_", "-")}{inc.channels_configured && !inc.channels_configured[c] && <span className="text-[10px] text-slate-500">(not configured)</span>}
              </label>
            ))}
          </fieldset>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="danger" disabled={busy} onClick={() => {
              if (!confirmTwice(`Send ${level} to ${inc.users_by_radius?.[String(radius)] ?? "?"} subscribers within ${radius} km?`, level)) return;
              act("approve-send", { level, radius_km: radius, title, body, channels: Object.entries(channels).filter(([, v]) => v).map(([k]) => k) }, "Approved and sent");
            }}>{inc.incident_status === "PROPOSED" ? "Approve & send" : "Send update"}</Button>
            {inc.incident_status === "PROPOSED" && inc.verification_status !== "confirmed" &&
              <Button disabled={busy} onClick={() => act("verify", { decision: "confirm", note }, "Confirmed (not sent)")}>Confirm only</Button>}
            {inc.incident_status === "PROPOSED" &&
              <Button disabled={busy} onClick={() => act("verify", { decision: "reject", note: note || "rejected after review" }, "Rejected")}>Reject</Button>}
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto_auto]">
            <input className={inputCls} placeholder="Note (required for level change / close)" value={note} onChange={(e) => setNote(e.target.value)} />
            <Button disabled={busy || note.length < 3 || level === inc.alert_level} onClick={() => act("level", { level, note }, `Level set to ${level}`)}>
              {["WATCH", "WARNING", "CRITICAL"].indexOf(level) > ["WATCH", "WARNING", "CRITICAL"].indexOf(inc.alert_level) ? "Escalate" : "Downgrade"} level only
            </Button>
            <Button disabled={busy || note.length < 3} onClick={() => act("close", { note, send_all_clear: inc.incident_status === "ACTIVE" }, "Closed")}>
              Close{inc.incident_status === "ACTIVE" ? " + all clear" : ""}
            </Button>
          </div>
          {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
        </Panel>
      )}
      {open && !can(SEND_ROLE) && <Notice kind="info">An operator must review and send this incident&apos;s message.</Notice>}
      {!open && inc.close_note && <Panel title="Closed"><p className="text-sm">{inc.close_note}</p></Panel>}

      {can(SEND_ROLE) && (
        <Panel title="Notification delivery" note={deliveries ? `${deliveries.length} records` : undefined}>
          {!deliveries?.length ? <Empty>Nothing sent for this incident.</Empty> : (
            <div className="max-h-72 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-slate-400"><tr><th>Recipient</th><th>Channel</th><th>Status</th><th>Level</th><th>Distance</th><th>Sent</th><th>Ack</th></tr></thead>
                <tbody className="divide-y divide-white/5">
                  {deliveries.map((d) => (
                    <tr key={d.id} title={d.error ?? ""}>
                      <td className="py-1">{d.name}</td><td>{d.notification_channel}</td>
                      <td className={d.notification_status === "failed" ? "text-red-300" : d.notification_status === "suppressed" ? "text-slate-500" : ""}>{d.notification_status.replaceAll("_", " ")}</td>
                      <td>{d.level}</td><td className="tabular-nums">{d.distance_km != null ? `${d.distance_km.toFixed(1)} km` : "—"}</td>
                      <td>{d.sent_at ? new Date(d.sent_at).toLocaleTimeString() : "—"}</td><td>{d.acknowledged_at ? "✓" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}

      <Panel title="History">
        <ol className="space-y-1 text-xs">
          {inc.history?.map((h, i) => (
            <li key={i} className="flex gap-2"><span className="whitespace-nowrap text-slate-500">{fmtTime(h.at)}</span>
              <span className="text-slate-300">{h.action}</span><span className="truncate text-slate-500">{h.actor.startsWith("system") ? "AI" : "officer"} {summary(h.payload)}</span></li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}

function summary(p: Record<string, unknown>): string {
  const keys = ["level", "to", "radius_km", "note", "result"];
  return keys.filter((k) => p[k] != null).map((k) => `${k}=${typeof p[k] === "object" ? JSON.stringify(p[k]) : p[k]}`).join(" ");
}

function ObservationCard({ o }: { o: Observation }) {
  const { apiBlobUrl } = useAuth();
  const [img, setImg] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    apiBlobUrl(o.image_url).then((u) => { url = u; setImg(u); }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [o.image_url, apiBlobUrl]);
  const a = o.analysis;
  return (
    <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {img ? <a href={img} target="_blank" rel="noreferrer"><img src={img} alt="Reported photo" className="h-32 w-40 rounded object-cover" /></a>
        : <div className="h-32 w-40 rounded bg-white/5" />}
      <div className="text-xs">
        {a ? (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <b>{a.classification_label}</b><span className="text-slate-400">{Math.round(a.visual_confidence * 100)}%</span>
              {a.alert_level !== "NONE" && <AlertBadge level={a.alert_level} />}
            </div>
            <div className="mt-1 text-slate-400">Policy: {ACTION_TEXT[a.recommended_action] ?? a.recommended_action} · Agent: {a.agent_action ? ACTION_TEXT[a.agent_action] : "—"} ({a.evidence.agent_mode})</div>
            <div className="text-slate-400">Taken {fmtTime(o.capture_timestamp)} ({TIME_SOURCE_TEXT[o.capture_time_source]}) · location {o.location_source ? LOCATION_SOURCE_TEXT[o.location_source] : "—"}{o.gps_accuracy_meters ? ` ±${Math.round(o.gps_accuracy_meters)} m` : ""}</div>
            <details className="mt-1"><summary className="cursor-pointer text-slate-300">Reasons</summary>
              <ul className="mt-1 list-disc pl-4 text-slate-400">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></details>
          </>
        ) : <span className="text-slate-400">{o.processing_status}{o.error ? `: ${o.error}` : ""}</span>}
      </div>
    </div>
  );
}

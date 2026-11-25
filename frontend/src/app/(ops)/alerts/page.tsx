"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { AlertBadge } from "@/components/VisualBadges";
import { Button, Empty, Field, inputCls, Notice, PageHeader, Panel } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ALERT_COLOR, type Areas, fmtTime, getPosition } from "@/lib/visual";

const VisualMap = dynamic(() => import("@/components/VisualMap"), { ssr: false });

interface Alert { id: string; kind: "incident" | "broadcast"; level: string; title: string; body: string; distance_km: number | null; created_at: string;
  read_at: string | null; acknowledged_at: string | null; latitude: number | null; longitude: number | null; radius_km: number | null }
interface Sub { subscribed: boolean; consent: boolean; latitude?: number | null; longitude?: number | null; home_label?: string | null; district?: string | null;
  province?: string | null; channels?: Record<string, boolean>; phone?: string | null; email?: string | null; consent_at?: string | null; ntfy_topic?: string | null }

export default function AlertsPage() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  return (
    <div className="space-y-5">
      <PageHeader title="My alerts" subtitle="Location-based flood and landslide alerts for the place you choose. You decide what you receive and can opt out at any time." />
      {user ? <Inbox /> : (
        <Notice kind="info"><Link href="/login?mode=register" className="font-semibold underline">Create a free account</Link> or{" "}
          <Link href="/login" className="font-semibold underline">sign in</Link> to receive alerts for your area.</Notice>
      )}
    </div>
  );
}

function Inbox() {
  const { api } = useAuth();
  const { data: alerts, mutate } = useSWR<Alert[]>("my-alerts", () => api<Alert[]>("/api/v1/visual-disaster/alerts"), { refreshInterval: 20_000 });
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => { if (alerts?.some((a) => !a.read_at)) api("/api/v1/visual-disaster/alerts/read-all", { method: "POST" }).catch(() => {}); }, [alerts, api]);
  const sel = alerts?.find((a) => a.id === open);
  return (
    <div className="grid gap-5 [&>*]:min-w-0 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Inbox" note={<BrowserNotifications />}>
          {!alerts?.length ? <Empty>No alerts. When an approved alert covers your saved location it appears here.</Empty> : (
            <ul className="space-y-2">
              {alerts.map((a) => (
                <li key={a.id} className={`rounded-lg border p-3 ${a.acknowledged_at ? "border-white/10" : "border-amber-400/40 bg-amber-400/5"}`}>
                  <button className="flex w-full flex-wrap items-center gap-2 text-left" onClick={() => setOpen(open === a.id ? null : a.id)}>
                    <AlertBadge level={a.level} /><span className="font-semibold">{a.title}</span>
                    <span className="ml-auto text-xs text-slate-400">{fmtTime(a.created_at)}{a.distance_km != null ? ` · ${a.distance_km.toFixed(1)} km away` : ""}</span>
                  </button>
                  {open === a.id && <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-slate-200">{a.body}</pre>}
                  <div className="mt-2 flex gap-2">
                    {!a.acknowledged_at ? (
                      <Button variant="primary" onClick={async () => { await api(`/api/v1/visual-disaster/alerts/${a.id}/ack`, { method: "POST" }); mutate(); }}>I have seen this</Button>
                    ) : <span className="text-xs text-emerald-300">Acknowledged {fmtTime(a.acknowledged_at)}</span>}
                    {open !== a.id && <Button variant="ghost" onClick={() => setOpen(a.id)}>Read</Button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {sel?.latitude != null && sel.longitude != null && (
          <VisualMap className="h-64" points={[{ id: sel.id, lon: sel.longitude, lat: sel.latitude, color: ALERT_COLOR[sel.level] ?? "#888", kind: "incident", label: sel.title }]}
            circles={sel.radius_km ? [{ id: "r", lon: sel.longitude, lat: sel.latitude, km: sel.radius_km, color: ALERT_COLOR[sel.level] ?? "#888" }] : []}
            focus={{ lat: sel.latitude, lon: sel.longitude, zoom: 11 }} />
        )}
      </div>
      <Subscription />
    </div>
  );
}

function BrowserNotifications() {
  const [perm, setPerm] = useState<string>("default");
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (typeof Notification !== "undefined") setPerm(Notification.permission); }, []);
  if (typeof Notification === "undefined") return null;
  if (perm === "granted") return <span className="text-xs text-emerald-300">Browser notifications on</span>;
  if (perm === "denied") return <span className="text-xs text-slate-500">Browser notifications blocked</span>;
  return <Button variant="ghost" onClick={async () => setPerm(await Notification.requestPermission())}>Turn on browser notifications</Button>;
}

function Subscription() {
  const { api } = useAuth();
  const { data: sub, mutate } = useSWR<Sub>("my-sub", () => api<Sub>("/api/v1/visual-disaster/subscription"));
  const { data: areas } = useSWR<Areas>("/api/v1/visual-disaster/geo/areas", (p: string) => api<Areas>(p));
  const { data: ch } = useSWR("/api/v1/visual-disaster/channels", (p: string) => api<{ configured: Record<string, boolean>; external_sending_enabled: boolean }>(p));
  const [home, setHome] = useState<{ lat: number; lon: number } | null>(null);
  const [district, setDistrict] = useState("");
  const [channels, setChannels] = useState<Record<string, boolean>>({ in_app: true, ntfy: false, push: false, sms: false, email: false });
  const [topic, setTopic] = useState("");
  const [testing, setTesting] = useState(false);
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error" | "info"; text: string } | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!sub || loaded) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoaded(true);
    if (sub.latitude != null && sub.longitude != null) setHome({ lat: sub.latitude, lon: sub.longitude });
    setDistrict(sub.district ?? ""); setChannels({ in_app: true, ...(sub.channels ?? {}) });
    setPhone(sub.phone ?? ""); setEmail(sub.email ?? ""); setConsent(sub.subscribed); setTopic(sub.ntfy_topic ?? "");
  }, [sub, loaded]);

  async function pickHome(lat: number, lon: number) {
    setHome({ lat, lon });
    try { const r = await api<{ district: string }>(`/api/v1/visual-disaster/geo/locate?lat=${lat}&lon=${lon}`); setDistrict(r.district); } catch { /* keep */ }
  }

  const missing = [
    !home && "choose your location on the map (or press “Use my current location”)",
    channels.ntfy && topic.length < 12 && "press “New random” to get a topic name for the ntfy app",
    !consent && "tick the “I agree” box",
  ].filter(Boolean) as string[];

  async function save() {
    setMsg(null);
    if (missing.length) { setMsg({ kind: "error", text: `Almost there — please ${missing.join(", then ")}.` }); return; }
    try {
      await api("/api/v1/visual-disaster/subscription", { method: "PUT", body: { consent, latitude: home?.lat, longitude: home?.lon, district: district || null,
        channels, phone: phone || null, email: email || null, ntfy_topic: channels.ntfy && topic ? topic.trim() : null } });
      setMsg({ kind: "ok", text: "Saved. You will receive approved alerts that cover your location or district." });
      mutate();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  function newTopic() {
    const a = new Uint8Array(9);
    crypto.getRandomValues(a);
    setTopic("amhews-" + Array.from(a, (b) => b.toString(36).padStart(2, "0")).join("").slice(0, 14));
  }

  async function testPhone() {
    setMsg(null); setTesting(true);
    try {
      const r = await api<{ results: Record<string, { status: string; error: string | null }>; external_sending_enabled: boolean }>(
        "/api/v1/visual-disaster/subscription/test", { method: "POST" });
      const parts = Object.entries(r.results).map(([c, v]) => `${c === "ntfy" ? "phone (ntfy)" : c}: ${v.status.replaceAll("_", " ")}${v.error ? ` — ${v.error}` : ""}`);
      const sent = Object.values(r.results).some((v) => v.status === "sent");
      setMsg({ kind: sent ? "ok" : "error", text: sent ? `Test sent — check your phone. (${parts.join("; ")})`
        : `Not sent: ${parts.join("; ")}.${!r.external_sending_enabled ? " Phone sending is switched off on this server (NOTIFY_EXTERNAL_ENABLED)." : ""}` });
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } finally { setTesting(false); }
  }

  async function optOut() {
    if (!confirm("Stop all location-based alerts and delete your saved location and phone number?")) return;
    await api("/api/v1/visual-disaster/subscription", { method: "DELETE" });
    setConsent(false); setHome(null); setPhone(""); setLoaded(false); mutate();
    setTopic("");
    setMsg({ kind: "info", text: "You have opted out. Your location, phone number and topic name were deleted. To subscribe again: choose your location, tick the phone option (a new topic name is made), tick “I agree”, press Subscribe — and subscribe to the new topic name in the ntfy app." });
  }

  return (
    <Panel title="Alert settings" note={sub?.subscribed ? <span className="text-emerald-300">subscribed</span> : "not subscribed"}>
      <div className="space-y-3 text-sm">
        <Field label="Home or work location" hint="Click the map or use your current position. Only used to decide whether an alert covers you.">
          <div className="space-y-2">
            <VisualMap className="h-56" onPick={pickHome}
              points={home ? [{ id: "home", lon: home.lon, lat: home.lat, color: "#0ea5e9", kind: "home", label: "Your location" }] : []}
              focus={home ? { lat: home.lat, lon: home.lon, zoom: 12 } : null} />
            <Button onClick={async () => { try { const p = await getPosition(); pickHome(+p.coords.latitude.toFixed(5), +p.coords.longitude.toFixed(5)); } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } }}>
              Use my current location
            </Button>
          </div>
        </Field>
        <Field label="District" hint="Area messages sent to a district reach everyone who chose it.">
          <select className={inputCls} value={district} onChange={(e) => setDistrict(e.target.value)}>
            <option value="">(nearest to my location)</option>
            {areas?.provinces.map((p) => <optgroup key={p} label={p}>{areas.districts.filter((d) => d.province === p).map((d) => <option key={d.name}>{d.name}</option>)}</optgroup>)}
          </select>
        </Field>
        <fieldset className="space-y-1.5">
          <legend className="mb-1 text-xs text-slate-400">How to reach me</legend>
          {(["in_app", "ntfy", "push", "sms", "email"] as const).map((c) => (
            <label key={c} className="flex items-center gap-2">
              <input type="checkbox" checked={c === "in_app" || (!!channels[c] && !!ch?.configured[c])} disabled={c === "in_app" || (!!ch && !ch.configured[c])} onChange={(e) => { setChannels({ ...channels, [c]: e.target.checked }); if (c === "ntfy" && e.target.checked && !topic) newTopic(); }} />
              {{ in_app: "In this app (always on)", ntfy: "Phone notification (free ntfy app)", push: "Push notification", sms: "SMS", email: "Email" }[c]}
              {ch && !ch.configured[c] && <span className="text-xs text-slate-500">— not available on this server yet</span>}
            </label>
          ))}
        </fieldset>
        {channels.ntfy && (
          <div className="space-y-2 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
            <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-300">
              <li>Install <b>ntfy</b> on your phone (free, from Google Play or the App Store).</li>
              <li>In ntfy tap <b>+</b> (Subscribe to topic) and type exactly the topic name below.</li>
              <li>Save here, then press <b>Send a test to my phone</b>.</li>
            </ol>
            <Field label="Your private topic name" hint="Anyone who knows this name can read your alerts, so keep the random one. Letters, numbers, - and _ (12–64 characters).">
              <div className="flex gap-2">
                <input className={`${inputCls} font-mono`} value={topic} maxLength={64} placeholder="amhews-…" onChange={(e) => setTopic(e.target.value.replace(/[^A-Za-z0-9_-]/g, ""))} />
                <Button onClick={newTopic}>New random</Button>
              </div>
            </Field>
          </div>
        )}
        {channels.sms && ch?.configured.sms && <Field label="Mobile number"><input className={inputCls} value={phone} placeholder="+977 98…" onChange={(e) => setPhone(e.target.value)} /></Field>}
        {channels.email && ch?.configured.email && <Field label="Email (blank = account email)"><input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>}
        <label className="flex items-start gap-2 rounded-lg border border-white/10 p-3">
          <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>I agree that this system stores my chosen location{channels.sms && ch?.configured.sms ? " and phone number" : ""} to send me disaster alerts for that area. Alerts may come from
            AI-assisted photo reports reviewed by an operator; they are not official government announcements. I can opt out at any time, which deletes my location.</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={save}>{sub?.subscribed ? "Save changes" : "Subscribe to alerts"}</Button>
          {sub?.subscribed && <Button disabled={testing} onClick={testPhone}>{testing ? "Sending…" : "Send a test to my phone"}</Button>}
          {sub?.subscribed && <Button variant="ghost" onClick={optOut}>Opt out</Button>}
        </div>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </div>
    </Panel>
  );
}

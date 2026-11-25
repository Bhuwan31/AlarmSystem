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
  province?: string | null; channels?: Record<string, boolean>; phone?: string | null; email?: string | null; consent_at?: string | null }

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
  const { data: ch } = useSWR("/api/v1/visual-disaster/channels", (p: string) => api<{ configured: Record<string, boolean> }>(p));
  const [home, setHome] = useState<{ lat: number; lon: number } | null>(null);
  const [district, setDistrict] = useState("");
  const [channels, setChannels] = useState<Record<string, boolean>>({ in_app: true, push: false, sms: false, email: false });
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
    setPhone(sub.phone ?? ""); setEmail(sub.email ?? ""); setConsent(sub.subscribed);
  }, [sub, loaded]);

  async function pickHome(lat: number, lon: number) {
    setHome({ lat, lon });
    try { const r = await api<{ district: string }>(`/api/v1/visual-disaster/geo/locate?lat=${lat}&lon=${lon}`); setDistrict(r.district); } catch { /* keep */ }
  }

  async function save() {
    setMsg(null);
    try {
      await api("/api/v1/visual-disaster/subscription", { method: "PUT", body: { consent, latitude: home?.lat, longitude: home?.lon, district: district || null,
        channels, phone: phone || null, email: email || null } });
      setMsg({ kind: "ok", text: "Saved. You will receive approved alerts that cover your location or district." });
      mutate();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  async function optOut() {
    if (!confirm("Stop all location-based alerts and delete your saved location and phone number?")) return;
    await api("/api/v1/visual-disaster/subscription", { method: "DELETE" });
    setConsent(false); setHome(null); setPhone(""); setLoaded(false); mutate();
    setMsg({ kind: "info", text: "You have opted out. Your location and phone number were deleted." });
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
          {(["in_app", "push", "sms", "email"] as const).map((c) => (
            <label key={c} className="flex items-center gap-2">
              <input type="checkbox" checked={c === "in_app" || !!channels[c]} disabled={c === "in_app"} onChange={(e) => setChannels({ ...channels, [c]: e.target.checked })} />
              {{ in_app: "In this app (always on)", push: "Push notification", sms: "SMS", email: "Email" }[c]}
              {ch && !ch.configured[c] && <span className="text-xs text-slate-500">— not available on this server yet</span>}
            </label>
          ))}
        </fieldset>
        {channels.sms && <Field label="Mobile number"><input className={inputCls} value={phone} placeholder="+977 98…" onChange={(e) => setPhone(e.target.value)} /></Field>}
        {channels.email && <Field label="Email (blank = account email)"><input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>}
        <label className="flex items-start gap-2 rounded-lg border border-white/10 p-3">
          <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>I agree that this system stores my chosen location{channels.sms ? " and phone number" : ""} to send me disaster alerts for that area. Alerts may come from
            AI-assisted photo reports reviewed by an operator; they are not official government announcements. I can opt out at any time, which deletes my location.</span>
        </label>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={!consent || !home} onClick={save}>{sub?.subscribed ? "Save changes" : "Subscribe to alerts"}</Button>
          {sub?.subscribed && <Button variant="ghost" onClick={optOut}>Opt out</Button>}
        </div>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </div>
    </Panel>
  );
}

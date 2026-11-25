"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { Button, Empty, Notice, PageHeader, Panel } from "@/components/ui";
import { RiskBadge } from "@/components/VisualBadges";
import { useAuth } from "@/lib/auth";
import {
  ACTION_TEXT, ALERT_COLOR, checkFile, CORRELATION_TEXT, fmtTime, getPosition, isoLocal, LOCATION_SOURCE_TEXT, TIME_SOURCE_TEXT, type Observation,
} from "@/lib/visual";

const VisualMap = dynamic(() => import("@/components/VisualMap"), { ssr: false });

type Loc = { lat: number; lon: number; accuracy: number | null; source: "device_gps" | "exif" | "manual" };
type Draft = { blob: Blob; url: string; source: "camera" | "upload"; captureIso: string | null; fileName?: string };

export default function VisualDetectionPage() {
  const { user, ready } = useAuth();
  if (!ready) return null;
  return (
    <div className="space-y-5">
      <PageHeader title="AI Visual Disaster Detection"
        subtitle="Photograph or upload what you see. The AI checks the photo for heavy rain, flooding, rising water, waterlogging or landslides, compares it with rain and river data, and suggests whether a warning is justified. A trained officer reviews every suggestion before anyone is alerted." />
      {user ? <Workflow /> : (
        <Notice kind="info">
          <Link href="/login?mode=register" className="font-semibold underline">Create a free account</Link> or{" "}
          <Link href="/login" className="font-semibold underline">sign in</Link> to report a photo. Reports are linked to your account so
          officers can follow up and to prevent misuse.
        </Notice>
      )}
    </div>
  );
}

function Workflow() {
  const { api, apiForm } = useAuth();
  const [tab, setTab] = useState<"camera" | "upload">("camera");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [obs, setObs] = useState<Observation | null>(null);
  const [loc, setLoc] = useState<Loc | null>(null);
  const [gpsMsg, setGpsMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resultId, setResultId] = useState<string | null>(null);
  const { data: mine, mutate: refreshMine } = useSWR<Observation[]>("mine", () => api<Observation[]>("/api/v1/visual-disaster/observations?mine=true&limit=20"),
    { refreshInterval: 15_000 });

  const reset = useCallback(() => {
    if (draft) URL.revokeObjectURL(draft.url);
    setDraft(null); setObs(null); setLoc(null); setGpsMsg(null); setError(null); setResultId(null);
  }, [draft]);

  async function onCameraPhoto(blob: Blob, captureIso: string) {
    reset();
    setDraft({ blob, url: URL.createObjectURL(blob), source: "camera", captureIso });
    setGpsMsg("Getting your location…");
    try {
      const p = await getPosition();
      setLoc({ lat: +p.coords.latitude.toFixed(6), lon: +p.coords.longitude.toFixed(6), accuracy: Math.round(p.coords.accuracy), source: "device_gps" });
      setGpsMsg(null);
    } catch (e) {
      setGpsMsg(`${(e as Error).message} Tap the map to mark where the photo was taken.`);
    }
  }

  async function onUploadFile(f: File) {
    reset();
    const bad = checkFile(f);
    if (bad) { setError(bad); return; }
    setDraft({ blob: f, url: URL.createObjectURL(f), source: "upload", captureIso: null, fileName: f.name });
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("image_source", "upload");
      fd.append("client_tz_offset_min", String(-new Date().getTimezoneOffset()));
      const o = await apiForm<Observation>("/api/v1/visual-disaster/observations", fd);
      setObs(o);
      if (o.latitude != null && o.longitude != null) setLoc({ lat: o.latitude, lon: o.longitude, accuracy: o.gps_accuracy_meters, source: "exif" });
      else setGpsMsg("This photo has no GPS location. Tap the map to mark where it was taken.");
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  async function submit() {
    if (!draft || !loc) return;
    setBusy(true); setError(null);
    try {
      let o = obs;
      if (!o) {                                           // camera: upload now with device time and GPS
        const fd = new FormData();
        fd.append("file", draft.blob, "camera.jpg");
        fd.append("image_source", "camera");
        if (draft.captureIso) fd.append("capture_timestamp", draft.captureIso);
        fd.append("client_tz_offset_min", String(-new Date().getTimezoneOffset()));
        fd.append("latitude", String(loc.lat));
        fd.append("longitude", String(loc.lon));
        fd.append("location_source", loc.source === "manual" ? "manual" : "device_gps");
        if (loc.accuracy != null && loc.source !== "manual") fd.append("gps_accuracy_m", String(loc.accuracy));
        o = await apiForm<Observation>("/api/v1/visual-disaster/observations", fd);
      }
      await api("/api/v1/visual-disaster/analyze", { method: "POST", body: {
        observation_id: o.image_id, latitude: loc.lat, longitude: loc.lon, location_source: loc.source,
        gps_accuracy_m: loc.source === "manual" ? null : loc.accuracy } });
      setResultId(o.image_id);
      refreshMine();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  if (resultId) return <Result id={resultId} onNew={reset} />;

  return (
    <div className="grid gap-5 [&>*]:min-w-0 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <div className="flex gap-2" role="tablist">
          <Button variant={tab === "camera" ? "primary" : "secondary"} role="tab" aria-selected={tab === "camera"} onClick={() => { reset(); setTab("camera"); }}>📷 Take photograph</Button>
          <Button variant={tab === "upload" ? "primary" : "secondary"} role="tab" aria-selected={tab === "upload"} onClick={() => { reset(); setTab("upload"); }}>⬆ Upload photograph</Button>
        </div>
        {error && <Notice kind="error">{error}</Notice>}
        {!draft && (tab === "camera" ? <Camera onPhoto={onCameraPhoto} onError={setError} /> : <Upload onFile={onUploadFile} />)}
        {draft && (
          <Panel title="Check the photo" note={draft.source === "camera" ? "from camera" : draft.fileName}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={draft.url} alt="Photo to analyse" className="max-h-80 w-full rounded-lg object-contain bg-black/40" />
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-400">Taken</dt>
              <dd>{draft.source === "camera" ? `${fmtTime(draft.captureIso)} (device clock)`
                : obs ? (obs.capture_timestamp ? `${fmtTime(obs.capture_timestamp)} — ${TIME_SOURCE_TEXT[obs.capture_time_source]}`
                  : "unknown (no time in the photo); only the upload time is recorded") : "reading photo…"}</dd>
              {obs && <><dt className="text-slate-400">Uploaded</dt><dd>{fmtTime(obs.upload_timestamp)}</dd></>}
              <dt className="text-slate-400">Location</dt>
              <dd>{loc ? `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)} — ${LOCATION_SOURCE_TEXT[loc.source]}${loc.accuracy ? ` (±${Math.round(loc.accuracy)} m)` : ""}`
                : (gpsMsg ?? "not set")}</dd>
              {obs?.suggested_location && <><dt className="text-slate-400">Place</dt><dd>{obs.suggested_location.label}</dd></>}
              {obs?.duplicate_of && <><dt className="text-slate-400">Note</dt><dd className="text-amber-300">This photo was already submitted; it will not be counted twice.</dd></>}
            </dl>
            {gpsMsg && loc === null && <p className="mt-2 text-xs text-amber-300">{gpsMsg}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="primary" disabled={!loc || busy} onClick={submit}>{busy ? "Sending…" : "Confirm and analyse"}</Button>
              <Button onClick={reset} disabled={busy}>Discard</Button>
            </div>
          </Panel>
        )}
      </div>
      <div className="space-y-4">
        <Panel title="Where was the photo taken?" note="tap the map to set or correct">
          <VisualMap className="h-80"
            points={loc ? [{ id: "pick", lon: loc.lon, lat: loc.lat, color: "#0ea5e9", label: "Photo location", kind: "pick" }] : []}
            circles={loc?.accuracy && loc.source !== "manual" ? [{ id: "acc", lon: loc.lon, lat: loc.lat, km: loc.accuracy / 1000, color: "#0ea5e9", dashed: true }] : []}
            focus={loc ? { lat: loc.lat, lon: loc.lon, zoom: 14 } : null}
            onPick={(lat, lon) => draft && setLoc({ lat, lon, accuracy: null, source: "manual" })} />
          <p className="mt-2 text-xs text-slate-400">Your exact location is only used to assess this report and to alert people nearby. It is shown to duty officers, never to the public.</p>
        </Panel>
        <MySubmissions items={mine} onOpen={setResultId} />
      </div>
    </div>
  );
}

function Camera({ onPhoto, onError }: { onPhoto: (b: Blob, iso: string) => void; onError: (m: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [live, setLive] = useState(false);
  const [unsupported, setUnsupported] = useState(false);

  const stop = useCallback(() => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; setLive(false); }, []);
  useEffect(() => stop, [stop]);

  async function start() {
    if (!navigator.mediaDevices?.getUserMedia) { setUnsupported(true); return; }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false });
      stream.current = s;
      if (video.current) { video.current.srcObject = s; await video.current.play(); }
      setLive(true);
    } catch (e) {
      setUnsupported(true);
      onError(`Camera unavailable: ${(e as Error).message}. You can use your phone's camera app below instead.`);
    }
  }

  function capture() {
    const v = video.current;
    if (!v) return;
    const iso = isoLocal(new Date());
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")?.drawImage(v, 0, 0);
    c.toBlob((b) => { if (b) { stop(); onPhoto(b, iso); } }, "image/jpeg", 0.92);
  }

  return (
    <Panel title="Take a photograph">
      <video ref={video} playsInline muted className={`w-full rounded-lg bg-black ${live ? "" : "hidden"}`} aria-label="Camera preview" />
      {!live && (
        <div className="space-y-3 text-sm text-slate-300">
          <p>Point the camera at the water, road or slope. Include something for scale (a car, wall, bridge or trees) if it is safe. Do not put yourself at risk to take a photo.</p>
          {!unsupported && <Button variant="primary" onClick={start}>Open camera</Button>}
          <label className="block text-xs text-slate-400">
            {unsupported ? "Use your device camera:" : "Or use your phone's camera app:"}
            <input type="file" accept="image/*" capture="environment" className="mt-1 block text-sm"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onPhoto(f, isoLocal(new Date())); }} />
          </label>
          <p className="text-xs text-slate-500">The time is taken from your device clock and your location from its GPS (you will be asked for permission).</p>
        </div>
      )}
      {live && (
        <div className="mt-3 flex gap-2">
          <Button variant="primary" onClick={capture}>Capture</Button>
          <Button onClick={stop}>Close camera</Button>
        </div>
      )}
    </Panel>
  );
}

function Upload({ onFile }: { onFile: (f: File) => void }) {
  const [over, setOver] = useState(false);
  return (
    <Panel title="Upload a photograph">
      <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f); }}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-8 text-center text-sm ${over ? "border-sky-400 bg-sky-500/10" : "border-white/15"}`}>
        <span className="text-3xl" aria-hidden>🖼</span>
        <span>Drop a photo here or <span className="text-sky-300 underline">choose a file</span></span>
        <span className="text-xs text-slate-400">JPEG, PNG or WebP, up to 10 MB. The time and GPS position stored in the photo are read if present.</span>
        <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
      </label>
    </Panel>
  );
}

function MySubmissions({ items, onOpen }: { items?: Observation[]; onOpen: (id: string) => void }) {
  return (
    <Panel title="My reports">
      {!items?.length ? <Empty>No reports yet.</Empty> : (
        <ul className="divide-y divide-white/5 text-sm">
          {items.map((o) => (
            <li key={o.image_id}>
              <button className="flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-white/5" onClick={() => onOpen(o.image_id)}>
                <span>
                  <span className="block">{o.analysis?.classification_label ?? statusText(o.processing_status)}</span>
                  <span className="text-xs text-slate-400">{fmtTime(o.capture_timestamp ?? o.upload_timestamp)} · {o.image_source}</span>
                </span>
                {o.analysis && <RiskBadge risk={o.analysis.risk_level} />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function statusText(s: Observation["processing_status"]) {
  return { awaiting_location: "Waiting for location", received: "Not analysed yet", queued: "Queued", processing: "Analysing…",
           done: "Done", failed: "Analysis failed", rejected: "Duplicate photo" }[s];
}


function Result({ id, onNew }: { id: string; onNew: () => void }) {
  const { api, apiBlobUrl } = useAuth();
  const { data: o } = useSWR<Observation>(["obs", id], () => api<Observation>(`/api/v1/visual-disaster/observations/${id}`),
    { refreshInterval: (d) => (d && ["done", "failed", "rejected"].includes(d.processing_status) ? 0 : 1500) });
  const [img, setImg] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    apiBlobUrl(`/api/v1/visual-disaster/observations/${id}/image`).then((u) => { url = u; setImg(u); }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id, apiBlobUrl]);

  if (!o) return <Panel>Loading…</Panel>;
  const a = o.analysis;
  const working = !["done", "failed", "rejected"].includes(o.processing_status);
  const top = a ? Object.entries(a.class_probabilities).sort((x, y) => y[1] - x[1]).slice(0, 4) : [];
  return (
    <div className="grid gap-5 [&>*]:min-w-0 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Analysis result" note={a ? `model ${a.model_version}` : undefined}>
          {working && <Notice kind="info">Analysing the photo and checking rain, river and warning data nearby…</Notice>}
          {o.processing_status === "failed" && <Notice kind="error">Analysis failed: {o.error}. A duty officer can still review the photo.</Notice>}
          {a && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-lg font-semibold">{a.classification_label}</span>
                <RiskBadge risk={a.risk_level} />
                {a.alert_level !== "NONE" && <span className="rounded px-1.5 py-0.5 text-[10px] font-bold text-black" style={{ background: ALERT_COLOR[a.alert_level] }}>{a.alert_level}</span>}
              </div>
              <div>
                <div className="mb-1 text-xs text-slate-400">Visual confidence {Math.round(a.visual_confidence * 100)}%</div>
                <div className="h-2 rounded bg-white/10"><div className="h-2 rounded bg-sky-500" style={{ width: `${a.visual_confidence * 100}%` }} /></div>
                <ul className="mt-2 grid grid-cols-2 gap-x-4 text-xs text-slate-400">
                  {top.map(([k, v]) => <li key={k} className="flex justify-between"><span>{k.replaceAll("_", " ")}</span><span className="tabular-nums">{Math.round(v * 100)}%</span></li>)}
                </ul>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-slate-400">Recommended</dt><dd>{ACTION_TEXT[a.recommended_action] ?? a.recommended_action}</dd>
                <dt className="text-slate-400">Decision agent</dt><dd>{a.agent_action ? `${ACTION_TEXT[a.agent_action] ?? a.agent_action} — ${a.evidence.agent_mode}` : "unavailable"}</dd>
                <dt className="text-slate-400">Weather</dt><dd>{CORRELATION_TEXT[a.weather_correlation]}</dd>
                {a.evidence.gauges && <><dt className="text-slate-400">Rain gauges</dt><dd>{a.evidence.gauges.rain_24h_mm ?? "—"} mm / 24 h, {a.evidence.gauges.rain_1h_mm ?? "—"} mm / 1 h ({a.evidence.gauges.stations} within 15 km)</dd></>}
                {a.evidence.river && <><dt className="text-slate-400">River gauge</dt><dd>{a.evidence.river.station} ({a.evidence.river.km} km): {a.evidence.river.level}</dd></>}
                {a.evidence.official && <><dt className="text-slate-400">Official warning</dt><dd>{a.evidence.official.level} at {a.evidence.official.station}</dd></>}
                <dt className="text-slate-400">Alert</dt>
                <dd>{a.alert_eligible ? <span className="text-amber-300">Sent to duty officers for review. No public message has been sent yet.</span> : "No alert proposed."}</dd>
              </dl>
              <details className="text-sm"><summary className="cursor-pointer text-slate-300">Why?</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-400">{a.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </details>
            </div>
          )}
          <div className="mt-4 flex gap-2"><Button variant="primary" onClick={onNew}>Report another photo</Button></div>
        </Panel>
        <p className="text-xs text-slate-500">AI results can be wrong. If you are in danger, move to safety and call local emergency services (Police 100, Nepal Army 1150) — do not wait for an alert.</p>
      </div>
      <div className="space-y-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {img && <img src={img} alt="Submitted photo" className="max-h-72 w-full rounded-lg bg-black/40 object-contain" />}
        {o.latitude != null && o.longitude != null && (
          <VisualMap className="h-72"
            points={[{ id: o.image_id, lon: o.longitude, lat: o.latitude, color: a ? ALERT_COLOR[a.alert_level] : "#888", label: "Your photo" }]}
            circles={a?.alert_eligible ? [{ id: "r", lon: o.longitude, lat: o.latitude, km: a.evidence.suggested_radius_km, color: ALERT_COLOR[a.alert_level], dashed: true }] : []}
            focus={{ lat: o.latitude, lon: o.longitude, zoom: a?.alert_eligible ? 11.5 : 13 }} />
        )}
        {a?.alert_eligible && <p className="text-xs text-slate-400">Dashed circle: suggested alert area ({a.evidence.suggested_radius_km} km). The officer decides the final area.</p>}
      </div>
    </div>
  );
}

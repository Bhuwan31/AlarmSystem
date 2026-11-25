"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { isMuted, playAlarm, setMuted, unlockAudioOnFirstGesture } from "@/lib/alarm";
import { fetcher, type Profile, type Warning } from "@/lib/api";
import { useAuth, type Role, SEND_ROLE } from "@/lib/auth";

const NAV: { href: string; label: string; icon: string; role?: Role }[] = [
  { href: "/", label: "Dashboard", icon: "◧" },
  { href: "/map", label: "3D map", icon: "◍" },
  { href: "/warnings", label: "Warnings", icon: "⚠" },
  { href: "/visual", label: "Report a photo", icon: "📷" },
  { href: "/alerts", label: "My alerts", icon: "🔔" },
  { href: "/incidents", label: "Visual incidents", icon: "◆", role: "operator" },
  { href: "/broadcast", label: "Area messages", icon: "📢", role: SEND_ROLE },
  { href: "/assistant", label: "AI assistant", icon: "✦" },
  { href: "/rivers", label: "Rivers", icon: "≈" },
  { href: "/rain", label: "Rainfall", icon: "☂" },
  { href: "/weather", label: "Weather & heat", icon: "☀" },
  { href: "/climate", label: "30-day weather", icon: "◷" },
  { href: "/ml", label: "ML models", icon: "⌬" },
  { href: "/shelters", label: "Shelters", icon: "⌂" },
  { href: "/devices", label: "Field devices", icon: "⚙" },
  { href: "/sources", label: "Data sources", icon: "⇅" },
  { href: "/audit", label: "Audit log", icon: "☰", role: "admin" },
  { href: "/admin", label: "Admin", icon: "✦", role: "admin" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout, mfa } = useAuth();
  const [open, setOpen] = useState(false);
  const { data: profile } = useSWR<Profile>("/api/v1/profile", fetcher);

  return (
    <div className="min-h-screen bg-[#07141a] text-slate-100 lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className={`${open ? "block" : "hidden"} border-b border-white/10 bg-[#061015] lg:sticky lg:top-0 lg:block lg:h-screen lg:border-b-0 lg:border-r`}>
        <div className="hidden px-4 py-4 lg:block">
          <div className="text-xs font-semibold tracking-[0.2em] text-amber-400">AMHEWS</div>
          <div className="text-sm text-slate-400">{profile?.name ?? "Early warning"}</div>
        </div>
        {/* The current path is only known at request time, so the active highlight streams in (Next.js 16) */}
        <Suspense fallback={<Nav path={null} onNavigate={() => setOpen(false)} />}>
          <NavWithPath onNavigate={() => setOpen(false)} />
        </Suspense>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-white/10 bg-[#07141a]/95 px-4 py-2.5 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button className="rounded-md bg-white/10 px-2 py-1 text-sm lg:hidden" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Menu">☰</button>
            <span className="text-xs font-semibold tracking-[0.2em] text-amber-400 lg:hidden">AMHEWS</span>
            {profile?.policies?.exercise_mode !== false && (
              <span className="rounded-full bg-amber-400/15 px-3 py-1 text-xs font-semibold text-amber-300">EXERCISE MODE — no public alerts</span>
            )}
          </div>
          <div className="flex items-center gap-2 text-sm">
            {user ? (
              <>
                <AlertBell />
                <span className="hidden text-slate-300 sm:inline">{user.name}</span>
                <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-300">{user.role}{mfa ? " · 2FA" : ""}</span>
                <button onClick={logout} className="rounded-md px-2 py-1 text-slate-300 hover:bg-white/10">Sign out</button>
              </>
            ) : (
              <Link href="/login" className="rounded-md bg-sky-600 px-3 py-1 font-medium text-white hover:bg-sky-500">Sign in</Link>
            )}
          </div>
        </header>
        <ReviewBanner />
        <main className="p-4 sm:p-6">{children}</main>
        <footer className="px-4 pb-6 text-xs text-slate-500 sm:px-6">
          Decision support only. Public warnings and sirens are issued by authorized officials. Data: DHM Nepal, Open-Meteo (CC BY 4.0), NASA GPM IMERG, ISRO MOSDAC, © OpenStreetMap contributors, Natural Earth, OpenFreeMap, AWS Terrain Tiles.
        </footer>
      </div>
    </div>
  );
}

function NavWithPath({ onNavigate }: { onNavigate: () => void }) {
  return <Nav path={usePathname()} onNavigate={onNavigate} />;
}

function Nav({ path, onNavigate }: { path: string | null; onNavigate: () => void }) {
  const { can } = useAuth();
  const { data: warnings } = useSWR<Warning[]>("/api/v1/warnings", fetcher, { refreshInterval: 60_000 });
  const pending = warnings?.filter((w) => w.status === "PROPOSED").length ?? 0;
  const proposed = useProposedIncidents();
  const unread = useUnread();
  const drafts = usePendingMessages();
  const active = (href: string) => path !== null && (href === "/" ? path === "/" : path.startsWith(href));
  return (
    <nav className="grid gap-0.5 p-2" aria-label="Main">
      {NAV.filter((n) => !n.role || can(n.role)).map((n) => (
        <Link key={n.href} href={n.href} onClick={onNavigate}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${active(n.href) ? "bg-sky-500/15 text-sky-200" : "text-slate-300 hover:bg-white/5"}`}
              aria-current={active(n.href) ? "page" : undefined}>
          <span className="w-4 text-center text-slate-400" aria-hidden>{n.icon}</span>
          <span className="flex-1">{n.label}</span>
          {n.href === "/warnings" && pending > 0 && <span className="rounded-full bg-amber-400 px-1.5 text-[10px] font-bold text-black">{pending}</span>}
          {n.href === "/incidents" && proposed.length > 0 && <span className="rounded-full bg-amber-400 px-1.5 text-[10px] font-bold text-black">{proposed.length}</span>}
          {n.href === "/broadcast" && drafts.count > 0 && <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">{drafts.count}</span>}
          {n.href === "/alerts" && unread > 0 && <span className="rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white">{unread}</span>}
        </Link>
      ))}
      <Link href="/public" className="mt-3 flex items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-300 hover:bg-white/5">
        <span className="w-4 text-center text-slate-400" aria-hidden>↗</span>Public page
      </Link>
    </nav>
  );
}

interface ProposedIncident { id: string; incident_status: string; alert_level: string; disaster_type: string; location_label: string }

function useProposedIncidents(): ProposedIncident[] {
  const { api, can } = useAuth();
  const { data } = useSWR<ProposedIncident[]>(can("operator") ? "proposed-incidents" : null,
    () => api<ProposedIncident[]>("/api/v1/visual-disaster/incidents?status=PROPOSED&limit=50"), { refreshInterval: 20_000 });
  return data ?? [];
}

function useUnread(): number {
  const { api, user } = useAuth();
  const { data } = useSWR<{ unread: number }>(user ? "unread-alerts" : null, () => api<{ unread: number }>("/api/v1/visual-disaster/alerts/unread"),
    { refreshInterval: 30_000 });
  return data?.unread ?? 0;
}

/** Header bell: unread count; shows a browser notification when a new alert arrives (if the user allowed it). */
function AlertBell() {
  const { api } = useAuth();
  const unread = useUnread();
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (last.current !== null && unread > last.current && typeof Notification !== "undefined" && Notification.permission === "granted") {
      api<{ title: string; body: string }[]>("/api/v1/visual-disaster/alerts?limit=1").then((a) => {
        if (a[0]) new Notification(a[0].title, { body: a[0].body.split("\n").slice(0, 4).join("\n"), tag: "amhews-alert" });
      }).catch(() => {});
    }
    last.current = unread;
  }, [unread, api]);
  return (
    <Link href="/alerts" className="relative rounded-md px-2 py-1 hover:bg-white/10" aria-label={`${unread} unread alerts`}>
      <span aria-hidden>🔔</span>
      {unread > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">{unread}</span>}
    </Link>
  );
}

interface PendingMessages { count: number; items: { id: string; level: string; title: string; area_label: string | null; hazard: string | null; at: string }[] }

/** AI-drafted area messages waiting for an approver (polled every 20 s). */
function usePendingMessages(): PendingMessages {
  const { api, can } = useAuth();
  const { data } = useSWR<PendingMessages>(can(SEND_ROLE) ? "pending-messages" : null,
    () => api<PendingMessages>("/api/v1/visual-disaster/broadcasts/pending"), { refreshInterval: 20_000 });
  return data ?? { count: 0, items: [] };
}

const REMIND_MS = 5 * 60_000;
const SEEN_KEY = "amhews.drafts.seen";

/** Plays the alert tone when a new AI draft arrives, then a reminder every 5 minutes while drafts are waiting. */
function useDraftAlarm(p: PendingMessages) {
  const lastPlayed = useRef(0);
  useEffect(() => unlockAudioOnFirstGesture(), []);
  useEffect(() => {
    if (p.count === 0) return;
    let seen: string[] = [];
    try { seen = JSON.parse(sessionStorage.getItem(SEEN_KEY) ?? "[]"); } catch { /* ignore */ }
    const fresh = p.items.filter((i) => !seen.includes(i.id));
    const top = (fresh[0] ?? p.items[0]).level;
    const due = fresh.length > 0 || Date.now() - lastPlayed.current > REMIND_MS;
    if (due && playAlarm(top)) {
      lastPlayed.current = Date.now();
      try { sessionStorage.setItem(SEEN_KEY, JSON.stringify(p.items.map((i) => i.id))); } catch { /* ignore */ }
      if (fresh.length && typeof Notification !== "undefined" && Notification.permission === "granted") {
        new Notification(`AI suggests a ${fresh[0].level} message`, { body: fresh[0].title, tag: "amhews-draft" });
      }
    }
  }, [p]);
  useEffect(() => {                                       // reminder tick even when nothing new arrives
    if (p.count === 0) return;
    const t = setInterval(() => { if (Date.now() - lastPlayed.current > REMIND_MS && playAlarm(p.items[0]?.level)) lastPlayed.current = Date.now(); }, 30_000);
    return () => clearInterval(t);
  }, [p]);
}

/** For approvers: banners when the AI drafts an area message or proposes an incident from a photo. */
function ReviewBanner() {
  const { can } = useAuth();
  const proposed = useProposedIncidents();
  const drafts = usePendingMessages();
  // the banner only renders after the client has fetched drafts, so reading localStorage here cannot cause a hydration mismatch
  const [muted, setMutedState] = useState(() => typeof window !== "undefined" && isMuted());
  useDraftAlarm(drafts);
  if (!can(SEND_ROLE)) return null;
  const d = drafts.items[0];
  const first = proposed[0];
  const tone = d?.level === "CRITICAL" ? "border-red-500/40 bg-red-500/15 text-red-100" : "border-amber-400/30 bg-amber-400/10 text-amber-100";
  return (
    <>
      {d && (
        <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2 text-sm sm:px-6 ${tone}`} role="alert">
          <span aria-hidden>🔊</span>
          <span className="min-w-0 flex-1"><b>AI suggests a {d.level} message</b> for {d.area_label ?? "a risk area"}: {d.title}.{" "}
            <Link href="/broadcast#drafts" className="font-semibold underline">Review, edit and send{drafts.count > 1 ? ` (${drafts.count} waiting)` : ""}</Link>
          </span>
          <button className="rounded px-2 py-0.5 text-xs hover:bg-white/10" onClick={() => { setMuted(!muted); setMutedState(!muted); }}
                  aria-pressed={muted}>{muted ? "🔇 Sound off — turn on" : "🔔 Sound on — mute"}</button>
        </div>
      )}
      {first && (
        <div className="border-b border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-100 sm:px-6" role="status">
          <b>{first.alert_level} {first.disaster_type.replace("_", " ").toLowerCase()} detected</b> near {first.location_label} from a photo report. A
          suggested message is ready.{" "}
          <Link href="/incidents" className="font-semibold underline">Review and send{proposed.length > 1 ? ` (${proposed.length} waiting)` : ""}</Link>
        </div>
      )}
    </>
  );
}

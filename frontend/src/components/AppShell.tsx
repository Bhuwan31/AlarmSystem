"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState } from "react";
import useSWR from "swr";

import { fetcher, type Profile, type Warning } from "@/lib/api";
import { useAuth, type Role } from "@/lib/auth";

const NAV: { href: string; label: string; icon: string; role?: Role }[] = [
  { href: "/", label: "Dashboard", icon: "◧" },
  { href: "/map", label: "3D map", icon: "◍" },
  { href: "/warnings", label: "Warnings", icon: "⚠" },
  { href: "/rivers", label: "Rivers", icon: "≈" },
  { href: "/rain", label: "Rainfall", icon: "☂" },
  { href: "/weather", label: "Weather & heat", icon: "☀" },
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
                <span className="hidden text-slate-300 sm:inline">{user.name}</span>
                <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-300">{user.role}{mfa ? " · 2FA" : ""}</span>
                <button onClick={logout} className="rounded-md px-2 py-1 text-slate-300 hover:bg-white/10">Sign out</button>
              </>
            ) : (
              <Link href="/login" className="rounded-md bg-sky-600 px-3 py-1 font-medium text-white hover:bg-sky-500">Operator sign in</Link>
            )}
          </div>
        </header>
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
        </Link>
      ))}
      <Link href="/public" className="mt-3 flex items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-300 hover:bg-white/5">
        <span className="w-4 text-center text-slate-400" aria-hidden>↗</span>Public page
      </Link>
    </nav>
  );
}

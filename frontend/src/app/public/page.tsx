"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { fetcher, type Shelter } from "@/lib/api";
import { LEVEL_COLOR } from "@/lib/colors";

type Lang = "ne" | "en";
type Level = "NORMAL" | "WATCH" | "WARNING" | "CRITICAL" | "UNKNOWN";
interface Near {
  level: Level;
  rivers: { id: number; name: string; distance_km: number; level: Level | null }[];
  warnings: { id: string; level: Level; message: { en: string; ne: string }; exercise: boolean; station_name: string; distance_km: number }[];
  shelters: (Shelter & { distance_km: number })[];
  emergency_numbers: Record<string, string>;
}

// Nepali text needs native-speaker review before launch (TBD-03).
const T = {
  title: { en: "Flood alerts for your area", ne: "तपाईंको क्षेत्रको बाढी सूचना" },
  intro: { en: "Check the flood risk on rivers near you and find the nearest safe shelter.", ne: "नजिकका नदीको बाढी जोखिम हेर्नुहोस् र नजिकको सुरक्षित आश्रयस्थल पत्ता लगाउनुहोस्।" },
  useLocation: { en: "Use my location", ne: "मेरो स्थान प्रयोग गर्नुहोस्" },
  orPick: { en: "or choose a place", ne: "वा ठाउँ छान्नुहोस्" },
  locating: { en: "Finding your location…", ne: "तपाईंको स्थान खोज्दै…" },
  denied: { en: "Location not available. Choose a place from the list.", ne: "स्थान उपलब्ध छैन। सूचीबाट ठाउँ छान्नुहोस्।" },
  riskNow: { en: "Flood risk now", ne: "अहिलेको बाढी जोखिम" },
  rivers: { en: "Rivers near you", ne: "नजिकका नदीहरू" },
  shelters: { en: "Nearest open shelters", ne: "नजिकका खुला आश्रयस्थल" },
  noShelter: { en: "No open shelter registered nearby. Go to higher ground and follow local officials.", ne: "नजिकै खुला आश्रयस्थल दर्ता छैन। अग्लो स्थानमा जानुहोस् र स्थानीय अधिकारीको निर्देशन मान्नुहोस्।" },
  emergency: { en: "Emergency numbers", ne: "आपतकालीन नम्बर" },
  disclaimer: { en: "This service gives early-warning information only. Always follow instructions from police and local officials on site. No warning does not mean you are safe.",
                ne: "यो सेवाले पूर्वसूचना मात्र दिन्छ। घटनास्थलमा प्रहरी र स्थानीय अधिकारीको निर्देशन सधैं पालना गर्नुहोस्। सूचना नआउनुको अर्थ सुरक्षित हुनु होइन।" },
  free: { en: "free places", ne: "खाली ठाउँ" },
  km: { en: "km", ne: "कि.मि." },
};
const LEVEL_TEXT: Record<Level, { en: [string, string]; ne: [string, string] }> = {
  NORMAL: { en: ["Normal", "No flood risk detected on nearby rivers. Stay informed."], ne: ["सामान्य", "नजिकका नदीमा बाढी जोखिम देखिएको छैन। जानकारी लिइरहनुहोस्।"] },
  WATCH: { en: ["Watch — be prepared", "Rivers are rising. Charge your phone, pack essentials, know your nearest shelter."], ne: ["सतर्कता — तयार रहनुहोस्", "नदी बढ्दैछ। फोन चार्ज गर्नुहोस्, आवश्यक सामान तयार राख्नुहोस्, नजिकको आश्रयस्थल थाहा पाउनुहोस्।"] },
  WARNING: { en: ["Warning — flooding likely", "Move people with limited mobility, livestock and valuables to higher ground. Be ready to leave."], ne: ["चेतावनी — बाढीको सम्भावना", "अशक्त व्यक्ति, पशुधन र बहुमूल्य सामान अग्लो स्थानमा सार्नुहोस्। जान तयार रहनुहोस्।"] },
  CRITICAL: { en: ["Evacuate now", "Go to the nearest shelter or high ground now. Do not cross flowing water."], ne: ["तुरुन्त सुरक्षित स्थानमा जानुहोस्", "अहिले नै नजिकको आश्रयस्थल वा अग्लो स्थानमा जानुहोस्। बगिरहेको पानी पार नगर्नुहोस्।"] },
  UNKNOWN: { en: ["No river data here", "There is no monitored river near this place. Follow local officials and radio."], ne: ["यहाँ नदीको तथ्याङ्क छैन", "यस ठाउँ नजिक निगरानी गरिएको नदी छैन। स्थानीय अधिकारी र रेडियोको सूचना सुन्नुहोस्।"] },
};
const PLACES: [string, string, number, number][] = [
  ["Kathmandu", "काठमाडौं", 27.7172, 85.324], ["Pokhara", "पोखरा", 28.2096, 83.9856], ["Biratnagar", "विराटनगर", 26.4525, 87.2718],
  ["Birgunj", "वीरगञ्ज", 27.0104, 84.877], ["Janakpur", "जनकपुर", 26.7288, 85.9263], ["Bharatpur", "भरतपुर", 27.6833, 84.4333],
  ["Butwal", "बुटवल", 27.7006, 83.4483], ["Nepalgunj", "नेपालगन्ज", 28.05, 81.6167], ["Dhangadhi", "धनगढी", 28.6833, 80.6], ["Rajapur (Bardiya)", "राजापुर (बर्दिया)", 28.43, 81.12],
];
const NUM_LABEL: Record<string, { en: string; ne: string }> = { police: { en: "Police", ne: "प्रहरी" }, fire: { en: "Fire", ne: "दमकल" }, ambulance: { en: "Ambulance", ne: "एम्बुलेन्स" } };

export default function PublicPage() {
  const [lang, setLang] = useState<Lang>("ne");
  const [pos, setPos] = useState<{ lat: number; lon: number; label: string } | null>(null);
  const [locMsg, setLocMsg] = useState<string | null>(null);
  const { data, isLoading } = useSWR<Near>(pos ? `/api/v1/risk/near?lat=${pos.lat}&lon=${pos.lon}` : null, fetcher, { refreshInterval: 120_000 });
  const t = (k: keyof typeof T) => T[k][lang];

  function locate() {
    if (!navigator.geolocation) { setLocMsg(t("denied")); return; }
    setLocMsg(t("locating"));
    // Location is used only to look up nearby risk; it is not stored (PRV-02).
    navigator.geolocation.getCurrentPosition(
      (p) => { setPos({ lat: +p.coords.latitude.toFixed(3), lon: +p.coords.longitude.toFixed(3), label: "📍" }); setLocMsg(null); },
      () => setLocMsg(t("denied")), { timeout: 10_000 });
  }

  const lvl = data?.level ?? "UNKNOWN";
  const dark = lvl === "WATCH" || lvl === "WARNING";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900" lang={lang}>
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
          <div className="text-sm font-semibold tracking-[0.15em] text-amber-600">AMHEWS</div>
          <div className="flex rounded-md border border-slate-300 text-sm" role="group" aria-label="Language">
            {(["ne", "en"] as const).map((l) => (
              <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l} className={`px-3 py-1 ${lang === l ? "bg-slate-900 text-white" : ""}`}>{l === "ne" ? "नेपाली" : "English"}</button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <div>
          <h1 className="text-2xl font-bold">{t("title")}</h1>
          <p className="mt-1 text-slate-600">{t("intro")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={locate} className="rounded-lg bg-sky-700 px-4 py-2.5 font-semibold text-white hover:bg-sky-600">{t("useLocation")}</button>
          <span className="text-sm text-slate-500">{t("orPick")}</span>
          <select className="rounded-lg border border-slate-300 bg-white px-3 py-2.5" value={pos?.label ?? ""} aria-label={t("orPick")}
                  onChange={(e) => { const p = PLACES.find((x) => x[0] === e.target.value); if (p) setPos({ lat: p[2], lon: p[3], label: p[0] }); }}>
            <option value="" disabled>—</option>
            {PLACES.map(([en, ne]) => <option key={en} value={en}>{lang === "ne" ? ne : en}</option>)}
          </select>
        </div>
        {locMsg && <p className="text-sm text-slate-600">{locMsg}</p>}

        {pos && (isLoading || !data) && <p className="text-slate-500">…</p>}

        {data && (
          <>
            <section className="rounded-2xl p-5 shadow-sm" style={{ background: LEVEL_COLOR[lvl], color: dark ? "#1a1a1a" : "#fff" }} aria-live="polite">
              <div className="text-sm font-semibold uppercase tracking-wide opacity-80">{t("riskNow")}</div>
              <div className="mt-1 text-3xl font-bold">{LEVEL_TEXT[lvl][lang][0]}</div>
              <p className="mt-2 text-lg">{LEVEL_TEXT[lvl][lang][1]}</p>
            </section>

            {data.warnings.map((w) => (
              <section key={w.id} className="rounded-xl border-2 bg-white p-4" style={{ borderColor: LEVEL_COLOR[w.level] }}>
                <p className="text-base">{w.message[lang]}</p>
                <p className="mt-1 text-xs text-slate-500">{w.station_name} · {w.distance_km} {t("km")}</p>
              </section>
            ))}

            <section className="rounded-xl bg-white p-4 shadow-sm">
              <h2 className="font-semibold">{t("shelters")}</h2>
              {data.shelters.length ? (
                <ul className="mt-2 divide-y divide-slate-100">
                  {data.shelters.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                      <div>
                        <div className="font-medium">{lang === "ne" && s.name_local ? s.name_local : s.name}</div>
                        <div className="text-xs text-slate-500">{s.distance_km} {t("km")} · {s.capacity - s.occupancy} {t("free")}{s.accessible ? " · ♿" : ""}{s.contact ? ` · ☎ ${s.contact}` : ""}</div>
                      </div>
                      <a className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white" target="_blank" rel="noreferrer"
                         href={`https://www.openstreetmap.org/directions?route=${pos ? `${pos.lat},${pos.lon};${s.lat},${s.lon}` : ""}`} aria-label={lang === "ne" ? "बाटो हेर्नुहोस्" : "Directions"}>↗</a>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-2 text-sm text-slate-600">{t("noShelter")}</p>}
            </section>

            <section className="rounded-xl bg-white p-4 shadow-sm">
              <h2 className="font-semibold">{t("rivers")}</h2>
              <ul className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
                {data.rivers.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2">
                    <span>{r.name} <span className="text-xs text-slate-500">{r.distance_km} {t("km")}</span></span>
                    <span className="rounded px-1.5 text-[11px] font-semibold" style={{ background: LEVEL_COLOR[r.level ?? "UNKNOWN"], color: r.level === "WATCH" || r.level === "WARNING" ? "#1a1a1a" : "#fff" }}>
                      {LEVEL_TEXT[r.level ?? "UNKNOWN"][lang][0].split(" — ")[0]}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="rounded-xl bg-white p-4 shadow-sm">
              <h2 className="font-semibold">{t("emergency")}</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(data.emergency_numbers).map(([k, n]) => (
                  <a key={k} href={`tel:${n}`} className="rounded-lg bg-red-600 px-4 py-2 text-lg font-bold text-white">{NUM_LABEL[k]?.[lang] ?? k} {n}</a>
                ))}
              </div>
            </section>
          </>
        )}

        <p className="text-sm text-slate-600">{t("disclaimer")}</p>
        <p className="text-xs text-slate-400"><Link href="/" className="underline">Operations dashboard</Link> · Data: DHM Nepal, Open-Meteo</p>
      </main>
    </div>
  );
}

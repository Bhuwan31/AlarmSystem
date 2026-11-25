"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { Button, inputCls, Notice, PageHeader, SignInPrompt } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Msg { role: "user" | "assistant"; content: string; tools?: string[] }

const SUGGESTIONS = [
  "What is the overall flood situation in Nepal right now?",
  "How are the rivers near Biratnagar?",
  "Is there any heatwave risk in the Terai in the next 3 days?",
  "Which rivers are closest to their warning level, and are they rising?",
  "Are any data sources or our own devices down?",
  "काठमाडौंमा अहिले मौसम कस्तो छ?",
];
const TOOL_LABEL: Record<string, string> = {
  national_overview: "national overview", list_river_stations: "river gauges", get_station: "station detail", rain_near: "rain gauges",
  satellite_rain: "satellite rain", weather_extremes: "weather extremes", weather_at: "point weather", area_conditions: "area conditions",
  devices_status: "field devices", data_quality: "data quality", active_warnings: "warnings", geocode: "place lookup",
};

export default function AssistantPage() {
  const { can, api } = useAuth();
  const { data: status } = useSWR<{ configured: boolean; model: string }>("/api/v1/ai/status", fetcher);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const next: Msg[] = [...messages, { role: "user", content: q }];
    setMessages(next); setInput(""); setBusy(true); setError(null);
    try {
      const r = await api<{ answer: string; tools_used: string[] }>("/api/v1/ai/chat", {
        method: "POST", body: { messages: next.slice(-20).map(({ role, content }) => ({ role, content })) },
      });
      setMessages([...next, { role: "assistant", content: r.answer, tools: r.tools_used }]);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <PageHeader title="AI assistant" subtitle={`Ask about conditions anywhere in the deployment area. Answers come from live gauges, devices, satellite and weather data${status?.configured ? ` (${status.model})` : ""}. Advisory only.`}
                  actions={messages.length > 0 ? <Button variant="ghost" onClick={() => setMessages([])}>New conversation</Button> : undefined} />
      {!can("viewer") ? <SignInPrompt role="viewer" action="use the assistant" /> : status && !status.configured ? (
        <Notice kind="info">The assistant is switched off. Add <code>GEMINI_API_KEY</code> (free, from aistudio.google.com) or <code>ANTHROPIC_API_KEY</code> to <code>.env</code> and restart the backend.</Notice>
      ) : (
        <>
          <div className="min-h-[50vh] space-y-3" aria-live="polite">
            {messages.length === 0 && (
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => ask(s)} className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-left text-sm hover:bg-white/[0.06]">{s}</button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
                <div className={`max-w-[90%] rounded-xl px-4 py-2.5 text-sm ${m.role === "user" ? "bg-sky-600/30" : "border border-white/10 bg-white/[0.03]"}`}>
                  <div className="whitespace-pre-line">{m.content}</div>
                  {m.tools && m.tools.length > 0 && (
                    <div className="mt-2 text-[11px] text-slate-400">Checked: {[...new Set(m.tools)].map((t) => TOOL_LABEL[t] ?? t).join(", ")}</div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="animate-pulse text-sm text-slate-400">Checking live data…</div>}
            {error && <Notice kind="error">{error}</Notice>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="sticky bottom-0 mt-4 flex gap-2 bg-[#07141a] py-3">
            <input className={inputCls} placeholder="e.g. How is the Karnali at Chisapani right now?" value={input}
                   onChange={(e) => setInput(e.target.value)} maxLength={2000} aria-label="Your question" />
            <Button type="submit" variant="primary" disabled={busy || !input.trim()}>Ask</Button>
          </form>
          <p className="text-[11px] text-slate-500">AI answers can be wrong. Check the cited figures on the river and station pages before acting; warnings are always decided by authorised officials.</p>
        </>
      )}
    </div>
  );
}

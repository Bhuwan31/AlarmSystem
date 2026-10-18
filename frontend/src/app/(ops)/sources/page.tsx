"use client";

import Link from "next/link";
import useSWR from "swr";

import { Empty, PageHeader, Panel, StatusDot } from "@/components/ui";
import { fetcher } from "@/lib/api";
import { ago } from "@/lib/colors";
import { useStatus } from "@/lib/hooks";

interface QEvent { id: number; source_code: string | null; kind: string; detail: Record<string, unknown>; opened_at: string; station_name: string | null; station_id: number | null }

const HOW: Record<string, string> = {
  needs_credentials: "Add the credentials in .env and enable the source (see README).",
  disabled: "Switched off. Enable it in the data_sources table once access is arranged.",
  stale: "No successful update within its expected window. Risk levels that depend on it keep their last value with LOW confidence (SR-06).",
};

export default function SourcesPage() {
  const { data } = useStatus();
  const { data: events } = useSWR<QEvent[]>("/api/v1/quality-events", fetcher, { refreshInterval: 60_000 });
  return (
    <div className="space-y-4">
      <PageHeader title="Data sources" subtitle="Every input the system relies on, whether it is fresh, and open data-quality problems." />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => (
          <div key={s.code} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 font-semibold"><StatusDot state={s.state} />{s.name}</div>
              <span className="text-xs uppercase text-slate-400">{s.kind}</span>
            </div>
            <dl className="mt-2 space-y-1 text-xs text-slate-300">
              <div className="flex justify-between"><dt className="text-slate-400">State</dt><dd>{s.state.replace("_", " ")}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Last success</dt><dd>{ago(s.last_success_at)}</dd></div>
              {s.last_error && <div><dt className="text-slate-400">Last error</dt><dd className="break-words text-red-300">{s.last_error}</dd></div>}
              {s.licence && <div><dt className="text-slate-400">Licence / terms</dt><dd>{s.licence}</dd></div>}
            </dl>
            {HOW[s.state] && <p className="mt-2 text-xs text-amber-200">{HOW[s.state]}</p>}
          </div>
        ))}
      </div>
      <Panel title="Open data-quality events" note={`${events?.length ?? 0} open`}>
        {events?.length ? (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">Kind</th><th>Source / station</th><th>Detail</th><th>Since</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-white/5">
                  <td className="py-1.5">{e.kind}</td>
                  <td>{e.station_id ? <Link href={`/stations/${e.station_id}`} className="hover:underline">{e.station_name}</Link> : e.source_code}</td>
                  <td className="text-xs text-slate-400">{Object.entries(e.detail).map(([k, v]) => `${k}: ${v}`).join(" · ")}</td>
                  <td className="text-xs text-slate-400">{ago(e.opened_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>No open data problems.</Empty>}
      </Panel>
    </div>
  );
}

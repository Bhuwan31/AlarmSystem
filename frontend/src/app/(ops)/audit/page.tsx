"use client";

import { useState } from "react";
import useSWR from "swr";

import { Button, inputCls, Notice, PageHeader, SignInPrompt } from "@/components/ui";
import { useAuth } from "@/lib/auth";

interface Entry { id: number; at: string; actor: string; actor_label: string; action: string; entity: string; entity_id: string | null; payload: Record<string, unknown>; hash: string }

export default function AuditPage() {
  const { can, api } = useAuth();
  const [action, setAction] = useState("");
  const key = can("admin") ? `/api/v1/audit?limit=300${action ? `&action=${encodeURIComponent(action)}` : ""}` : null;
  const { data, error } = useSWR<Entry[]>(key, (p: string) => api<Entry[]>(p), { refreshInterval: 30_000 });
  const [check, setCheck] = useState<{ rows: number; intact: boolean; first_broken_id: number | null } | null>(null);

  if (!can("admin")) return <div className="space-y-4"><PageHeader title="Audit log" /><SignInPrompt role="admin" action="view the audit log" /></div>;
  return (
    <div className="space-y-4">
      <PageHeader title="Audit log" subtitle="Append-only and hash-chained: every row includes the hash of the previous one, so any edit or deletion is detectable."
                  actions={<Button variant="primary" onClick={async () => setCheck(await api("/api/v1/audit/verify"))}>Verify chain</Button>} />
      {check && (
        <Notice kind={check.intact ? "ok" : "error"}>
          {check.intact ? `Intact: all ${check.rows} entries chain correctly.` : `Broken at entry #${check.first_broken_id} — the log has been altered.`}
        </Notice>
      )}
      {error && <Notice kind="error">{(error as Error).message}</Notice>}
      <select className={`${inputCls} max-w-xs`} value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filter by action">
        <option value="">All actions</option>
        {["warning.", "siren.", "auth.", "user.", "shelter.", "device.", "profile."].map((a) => <option key={a} value={a}>{a.replace(".", "")}</option>)}
      </select>
      <div className="overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full min-w-[800px] text-sm">
          <thead className="bg-white/[0.03] text-left text-xs text-slate-400">
            <tr><th className="py-2 pl-3">#</th><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th><th className="pr-3">Hash</th></tr>
          </thead>
          <tbody>
            {data?.map((e) => (
              <tr key={e.id} className="border-t border-white/5 align-top">
                <td className="py-1.5 pl-3 tabular-nums text-slate-400">{e.id}</td>
                <td className="whitespace-nowrap text-xs">{new Date(e.at).toLocaleString()}</td>
                <td className="text-xs">{e.actor_label}</td>
                <td className="font-mono text-xs">{e.action}</td>
                <td className="text-xs">{e.entity}{e.entity_id ? ` ${e.entity_id.slice(0, 12)}` : ""}</td>
                <td className="max-w-md break-words text-xs text-slate-400">{JSON.stringify(e.payload)}</td>
                <td className="pr-3 font-mono text-[10px] text-slate-500">{e.hash.slice(0, 10)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import useSWR from "swr";

import { Button, Field, inputCls, Notice, PageHeader, Panel, SignInPrompt } from "@/components/ui";
import { fetcher, type Profile } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago } from "@/lib/colors";

interface U { id: string; email: string; name: string; role: string; active: boolean; mfa: boolean; created_at: string; last_login_at: string | null }
type Policies = { exercise_mode?: boolean; auto_publish_watch?: boolean; critical_timeout_s?: number; watch_fraction?: number;
                  watch_margin_m?: number; rise_rate_m_per_h?: number; hold_minutes?: number };

export default function AdminPage() {
  const { can } = useAuth();
  return (
    <div className="space-y-4">
      <PageHeader title="Administration" subtitle="Accounts, roles and the safety policies of this deployment. Every change is written to the audit log." />
      <MyTwoFactor />
      {!can("admin") ? <SignInPrompt role="admin" action="manage users and policies" /> : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Users />
          <PoliciesPanel />
        </div>
      )}
    </div>
  );
}

function MyTwoFactor() {
  const { user, mfa, api } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  if (!user) return null;
  return (
    <Panel title="Your two-factor sign-in" note={mfa ? "this session used two-factor" : user.mfa_enrolled ? "enrolled" : "not set up"}>
      {user.mfa_enrolled && !setup ? (
        <p className="text-sm text-slate-300">Two-factor is on for your account. {mfa ? "" : "Sign out and in again with your code to approve CRITICAL warnings."}</p>
      ) : !setup ? (
        <div className="space-y-2 text-sm">
          <p className="text-slate-300">Approving CRITICAL warnings requires two-factor. Use any authenticator app (Google Authenticator, Microsoft Authenticator, Aegis…).</p>
          <Button variant="primary" onClick={async () => { try { setSetup(await api("/api/v1/auth/totp/setup", { method: "POST" })); } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } }}>Set up two-factor</Button>
        </div>
      ) : (
        <div className="space-y-2 text-sm">
          <p className="text-slate-300">In your authenticator app choose “enter a setup key” and type this key (time-based, 6 digits):</p>
          <code className="block break-all rounded bg-black/30 p-2 text-base tracking-wider">{setup.secret.match(/.{1,4}/g)?.join(" ")}</code>
          <p className="text-xs text-slate-400">Or open this link on the phone with the app: <span className="break-all">{setup.otpauth_uri}</span></p>
          <div className="flex items-end gap-2">
            <Field label="Code from the app"><input className={`${inputCls} w-36`} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} /></Field>
            <Button variant="primary" onClick={async () => {
              try { await api("/api/v1/auth/totp/verify", { method: "POST", body: { code } }); setMsg({ kind: "ok", text: "Two-factor enabled. Sign out and sign in again with a code." }); setSetup(null); }
              catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
            }}>Confirm</Button>
          </div>
        </div>
      )}
      {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </Panel>
  );
}

function Users() {
  const { user, api } = useAuth();
  const { data, mutate } = useSWR<U[]>("/api/v1/users", (p: string) => api<U[]>(p));
  const [f, setF] = useState({ email: "", name: "", role: "operator", password: "" });
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  async function call(path: string, method: string, body: unknown, ok: string) {
    setMsg(null);
    try { await api(path, { method, body }); setMsg({ kind: "ok", text: ok }); mutate(); } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }
  return (
    <Panel title="Users" note={`${data?.length ?? 0} accounts`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="text-left text-xs text-slate-400"><tr><th className="py-1">User</th><th>Role</th><th>2FA</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id} className={`border-t border-white/5 ${u.active ? "" : "opacity-50"}`}>
                <td className="py-1.5"><div>{u.name}</div><div className="text-xs text-slate-400">{u.email}</div></td>
                <td>
                  <select className={`${inputCls} w-28 !py-1`} value={u.role} disabled={u.id === user?.id}
                          onChange={(e) => call(`/api/v1/users/${u.id}`, "PATCH", { role: e.target.value }, `Role changed for ${u.email}.`)} aria-label="Role">
                    {["viewer", "operator", "approver", "admin"].map((r) => <option key={r}>{r}</option>)}
                  </select>
                </td>
                <td className="text-xs">{u.mfa ? "on" : "off"}</td>
                <td className="text-xs text-slate-400">{ago(u.last_login_at)}</td>
                <td className="space-x-1 text-right">
                  {u.id !== user?.id && <Button className="!px-2 !py-0.5 text-xs" onClick={() => call(`/api/v1/users/${u.id}`, "PATCH", { active: !u.active }, `${u.active ? "Deactivated" : "Activated"} ${u.email}.`)}>{u.active ? "Deactivate" : "Activate"}</Button>}
                  {u.mfa && <Button className="!px-2 !py-0.5 text-xs" onClick={() => call(`/api/v1/users/${u.id}`, "PATCH", { reset_mfa: true }, `Two-factor reset for ${u.email}.`)}>Reset 2FA</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="mt-4 grid gap-2 border-t border-white/10 pt-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); call("/api/v1/users", "POST", f, `Created ${f.email}.`); setF({ ...f, email: "", name: "", password: "" }); }}>
        <Field label="Email"><input className={inputCls} type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Name"><input className={inputCls} required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Role"><select className={inputCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{["viewer", "operator", "approver", "admin"].map((r) => <option key={r}>{r}</option>)}</select></Field>
        <Field label="Temporary password" hint="At least 12 characters; ask them to change it"><input className={inputCls} type="password" required minLength={12} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        <div className="sm:col-span-2"><Button type="submit" variant="primary">Add user</Button></div>
      </form>
      {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </Panel>
  );
}

function PoliciesPanel() {
  const { api } = useAuth();
  const { data: profile, mutate } = useSWR<Profile & { policies: Policies }>("/api/v1/profile", fetcher);
  const [draft, setDraft] = useState<Policies>({});
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const p = { ...(profile?.policies ?? {}), ...draft };
  const num = (k: keyof Policies, label: string, step: number, hint: string) => (
    <Field label={label} hint={hint}>
      <input className={inputCls} type="number" step={step} value={(p[k] as number | undefined) ?? ""} onChange={(e) => setDraft({ ...draft, [k]: +e.target.value })} />
    </Field>
  );
  return (
    <Panel title="Safety policies" note={profile ? `${profile.name} · ${profile.timezone}` : ""}>
      <div className="space-y-3">
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={p.exercise_mode ?? true} onChange={(e) => setDraft({ ...draft, exercise_mode: e.target.checked })} />
          <span><b>Exercise mode</b><br /><span className="text-xs text-slate-400">All messages are prefixed EXERCISE and sirens only chirp. Turn off only after government sign-off.</span></span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={p.auto_publish_watch ?? false} onChange={(e) => setDraft({ ...draft, auto_publish_watch: e.target.checked })} />
          <span><b>Publish WATCH without approval</b><br /><span className="text-xs text-slate-400">WARNING and CRITICAL always need human approval.</span></span>
        </label>
        <div className="grid gap-2 sm:grid-cols-2">
          {num("watch_fraction", "Watch level (share of warning level)", 0.05, "Gauge-zero stations, e.g. 0.8")}
          {num("watch_margin_m", "Watch margin below warning (m)", 0.1, "Stations reporting sea-level height")}
          {num("rise_rate_m_per_h", "Fast-rise threshold (m/h)", 0.05, "Rule R4 adds one level")}
          {num("hold_minutes", "Hold before lowering (min)", 5, "Rule R10, avoids flapping")}
          {num("critical_timeout_s", "CRITICAL approval timeout (s)", 60, "Escalate if undecided")}
        </div>
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        <Button variant="primary" disabled={!Object.keys(draft).length} onClick={async () => {
          try { await api("/api/v1/profile/policies", { method: "PATCH", body: draft }); setDraft({}); mutate(); setMsg({ kind: "ok", text: "Policies saved and audited." }); }
          catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
        }}>Save policies</Button>
      </div>
    </Panel>
  );
}

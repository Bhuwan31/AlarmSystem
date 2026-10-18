"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Field, inputCls, Notice } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    const r = await login(email, password, needCode ? totp : undefined);
    setBusy(false);
    if (r.ok) { router.push("/"); return; }
    if (r.mfaRequired) setNeedCode(true);
    setError(r.message);
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[#07141a] p-4 text-slate-100">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-6">
        <div>
          <div className="text-xs font-semibold tracking-[0.2em] text-amber-400">AMHEWS</div>
          <h1 className="mt-1 text-xl font-semibold">Operator sign in</h1>
          <p className="mt-1 text-sm text-slate-400">For authorized staff. The public page needs no account.</p>
        </div>
        {error && <Notice kind={needCode && !totp ? "info" : "error"}>{error}</Notice>}
        <Field label="Email">
          <input className={inputCls} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputCls} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {needCode && (
          <Field label="6-digit code from your authenticator app">
            <input className={inputCls} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,8}" required autoFocus
                   value={totp} onChange={(e) => setTotp(e.target.value)} />
          </Field>
        )}
        <Button type="submit" variant="primary" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <div className="flex justify-between text-xs text-slate-400">
          <Link href="/" className="hover:underline">← Dashboard (read-only)</Link>
          <Link href="/public" className="hover:underline">Public page</Link>
        </div>
      </form>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Field, inputCls, Notice } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  // ?mode=register opens the sign-up form (read after mount: the page is statically rendered)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (new URLSearchParams(window.location.search).get("mode") === "register") setMode("register"); }, []);
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
    if (mode === "register") {
      const reg = await register(email, name, password);
      setBusy(false);
      if (reg.ok) { router.push("/alerts"); return; }
      setError(reg.message);
      return;
    }
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
          <h1 className="mt-1 text-xl font-semibold">{mode === "login" ? "Sign in" : "Create an account"}</h1>
          <p className="mt-1 text-sm text-slate-400">{mode === "login" ? "Staff and registered residents. The public page needs no account."
            : "For residents: report photos of floods or landslides and receive alerts for your area. Staff roles are granted by an administrator."}</p>
        </div>
        {error && <Notice kind={needCode && !totp ? "info" : "error"}>{error}</Notice>}
        {mode === "register" && (
          <Field label="Name">
            <input className={inputCls} autoComplete="name" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        )}
        <Field label="Email">
          <input className={inputCls} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputCls} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required
                 minLength={mode === "register" ? 10 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        {needCode && (
          <Field label="6-digit code from your authenticator app">
            <input className={inputCls} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,8}" required autoFocus
                   value={totp} onChange={(e) => setTotp(e.target.value)} />
          </Field>
        )}
        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </Button>
        <button type="button" className="w-full text-center text-xs text-sky-300 hover:underline"
                onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
          {mode === "login" ? "New here? Create a resident account" : "Already have an account? Sign in"}
        </button>
        <div className="flex justify-between text-xs text-slate-400">
          <Link href="/" className="hover:underline">← Dashboard (read-only)</Link>
          <Link href="/public" className="hover:underline">Public page</Link>
        </div>
      </form>
    </div>
  );
}

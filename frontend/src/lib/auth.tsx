"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { API_URL } from "./api";

export type Role = "viewer" | "operator" | "approver" | "admin";
const RANK: Record<Role, number> = { viewer: 0, operator: 1, approver: 2, admin: 3 };

export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  mfa_enrolled: boolean;
}

interface AuthState {
  user: SessionUser | null;
  mfa: boolean;
  ready: boolean;
  login: (email: string, password: string, totp?: string) => Promise<{ ok: true } | { ok: false; mfaRequired: boolean; message: string }>;
  register: (email: string, name: string, password: string) => Promise<{ ok: true } | { ok: false; message: string }>;
  logout: () => void;
  can: (role: Role) => boolean;
  api: <T = unknown>(path: string, init?: { method?: string; body?: unknown }) => Promise<T>;
  /** multipart/form-data request (file uploads) */
  apiForm: <T = unknown>(path: string, form: FormData) => Promise<T>;
  /** authenticated binary GET → object URL (caller revokes it) */
  apiBlobUrl: (path: string) => Promise<string>;
}

const Ctx = createContext<AuthState | null>(null);
const KEY = "amhews.session";

// Session lives in sessionStorage: it ends when the browser tab closes. A production deployment should
// move the token to an httpOnly cookie set by the backend.
function readSession(): { token: string; user: SessionUser; mfa: boolean } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function errorMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return "request failed";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<{ token: string; user: SessionUser; mfa: boolean } | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Restoring a browser-only session after mount is the intended use of an effect here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSession(readSession());
    setReady(true);
  }, []);

  const logout = useCallback(() => {
    try { sessionStorage.removeItem(KEY); } catch { /* storage unavailable */ }
    setSession(null);
  }, []);

  const api = useCallback(async <T,>(path: string, init?: { method?: string; body?: unknown }): Promise<T> => {
    const res = await fetch(`${API_URL}${path}`, {
      method: init?.method ?? "GET",
      headers: { "Content-Type": "application/json", ...(session ? { Authorization: `Bearer ${session.token}` } : {}) },
      body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && session) logout();
    if (!res.ok) throw new ApiError(res.status, errorMessage((data as { detail?: unknown }).detail));
    return data as T;
  }, [session, logout]);

  const apiForm = useCallback(async <T,>(path: string, form: FormData): Promise<T> => {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST", body: form, headers: session ? { Authorization: `Bearer ${session.token}` } : {},
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && session) logout();
    if (!res.ok) throw new ApiError(res.status, errorMessage((data as { detail?: unknown }).detail));
    return data as T;
  }, [session, logout]);

  const apiBlobUrl = useCallback(async (path: string): Promise<string> => {
    const res = await fetch(`${API_URL}${path}`, { headers: session ? { Authorization: `Bearer ${session.token}` } : {} });
    if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
    return URL.createObjectURL(await res.blob());
  }, [session]);

  const register = useCallback<AuthState["register"]>(async (email, name, password) => {
    const res = await fetch(`${API_URL}/api/v1/auth/register`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, name, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { ok: false, message: errorMessage(data.detail) };
    const s = { token: data.token, user: data.user, mfa: false };
    try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage unavailable */ }
    setSession(s);
    return { ok: true };
  }, []);

  const login = useCallback<AuthState["login"]>(async (email, password, totp) => {
    const res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, totp: totp || null }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const d = data.detail;
      return { ok: false, mfaRequired: !!(d && typeof d === "object" && d.mfa_required), message: errorMessage(d) };
    }
    const s = { token: data.token, user: data.user, mfa: data.mfa };
    try { sessionStorage.setItem(KEY, JSON.stringify(s)); } catch { /* storage unavailable */ }
    setSession(s);
    return { ok: true };
  }, []);

  const value = useMemo<AuthState>(() => ({
    user: session?.user ?? null, mfa: session?.mfa ?? false, ready, login, register, logout, api, apiForm, apiBlobUrl,
    can: (role) => !!session && RANK[session.user.role] >= RANK[role],
  }), [session, ready, login, register, logout, api, apiForm, apiBlobUrl]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}

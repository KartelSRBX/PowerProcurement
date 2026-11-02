"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

const KEY = "pp_name";
type Auth = { enabled: boolean; users_exist: boolean; user: { id: number; name: string; roles: string[] } | null; roles: Record<string, string>; forced_off?: boolean } | null;
const Ctx = createContext<{ person: string; setPerson: (v: string) => void; auth: Auth; refreshAuth: () => Promise<void> }>({
  person: "", setPerson: () => {}, auth: null, refreshAuth: async () => {},
});

/** The name actions are recorded under: the signed-in user when sign-in is on, otherwise the name typed at the top. */
export function PersonProvider({ children }: { children: React.ReactNode }) {
  const [typed, set] = useState("");
  const [auth, setAuth] = useState<Auth>(null);
  useEffect(() => {
    try { set(localStorage.getItem(KEY) ?? ""); } catch { /* storage blocked */ }
  }, []);
  const refreshAuth = useCallback(async () => {
    try { setAuth(await api<any>("/auth/state")); } catch { setAuth(null); }
  }, []);
  useEffect(() => {
    refreshAuth();
    window.addEventListener("pp-auth", refreshAuth);
    return () => window.removeEventListener("pp-auth", refreshAuth);
  }, [refreshAuth]);
  const setPerson = (v: string) => {
    set(v);
    try { localStorage.setItem(KEY, v); } catch { /* storage blocked */ }
  };
  const person = auth?.enabled && auth.user ? auth.user.name : typed;
  return <Ctx.Provider value={{ person, setPerson, auth, refreshAuth }}>{children}</Ctx.Provider>;
}

export const usePerson = () => useContext(Ctx);

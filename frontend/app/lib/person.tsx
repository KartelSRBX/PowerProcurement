"use client";

import { createContext, useContext, useEffect, useState } from "react";

const KEY = "pp_name";
const Ctx = createContext<{ person: string; setPerson: (v: string) => void }>({ person: "", setPerson: () => {} });

export function PersonProvider({ children }: { children: React.ReactNode }) {
  const [person, set] = useState("");
  useEffect(() => {
    try { set(localStorage.getItem(KEY) ?? ""); } catch { /* storage blocked */ }
  }, []);
  const setPerson = (v: string) => {
    set(v);
    try { localStorage.setItem(KEY, v); } catch { /* storage blocked */ }
  };
  return <Ctx.Provider value={{ person, setPerson }}>{children}</Ctx.Provider>;
}

export const usePerson = () => useContext(Ctx);

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "./api";

/** True when a provider and key are set, so the AI buttons will do something. */
export function useAi(): boolean | null {
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => {
    const load = () => api<any>("/settings").then((s) => setOn(s.ai.provider === "anthropic" && !!s.ai.key.set)).catch(() => setOn(false));
    load();
    window.addEventListener("pp-settings", load);
    return () => window.removeEventListener("pp-settings", load);
  }, []);
  return on;
}

export function AiOff({ what }: { what: string }) {
  return <span className="muted">AI is off: {what} <Link href="/settings">Add a key in Settings</Link> to switch it on.</span>;
}

export const aiTag = (by?: string | null) => (by ? <span className={`tag ${by.startsWith("AI") ? "acc" : ""}`} title="who wrote the first version of this text">{by}</span> : null);

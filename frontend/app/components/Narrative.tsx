"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { AiOff, useAi } from "../lib/ai";

/** "Explain in words": AI describes the numbers shown on the page. It never changes them. */
export default function Narrative({ topic, days, customer, category }: { topic: "messages" | "pricing"; days?: number; customer?: string; category?: string }) {
  const ai = useAi();
  const [out, setOut] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function run() {
    setErr(""); setBusy(true);
    try { setOut(await api("/analytics/narrative", { method: "POST", json: { topic, days: days ?? 30, customer: customer || null, category: category || null } })); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }
  return (
    <section>
      <div className="row"><button disabled={!ai || busy} onClick={run}>{busy ? "Reading..." : "Explain these numbers in words"}</button>
        {ai === false && <AiOff what="the charts and tables are complete without it." />}</div>
      {err && <div className="err">{err}</div>}
      {out && <><p><b>{out.headline}</b></p><ul>{out.points.map((p: string) => <li key={p}>{p}</li>)}</ul>
        <p className="muted">Written by {out.model} from the numbers on this page; check anything that matters against the charts.</p></>}
    </section>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

/** One screen: what needs a person today, read from records the app already keeps. Nothing is sent from here. */
export default function Today() {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<any>("/summary/today").then(setV).catch((e) => setErr(e.message)); }, []);
  if (!v) return <p>{err || "Loading..."}</p>;
  const busy = v.sections.filter((s: any) => s.count > 0), quiet = v.sections.filter((s: any) => s.count === 0);
  return (
    <>
      <h1>Today <span className={`tag ${v.total ? "warn" : "ok"}`}>{v.total ? `${v.total} to look at` : "nothing waiting"}</span></h1>
      <p className="muted">{new Date(v.date + "T00:00:00").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}.
        This page only collects what other pages already track; each line opens the place where it is handled. Limits (days of silence, days before an offer or a contract runs out) are in Settings.</p>
      {busy.map((s: any) => (
        <section key={s.key} data-testid={`sum-${s.key}`}>
          <h2><Link href={s.href}>{s.title}</Link> <span className="tag warn">{s.count}</span></h2>
          {s.note && <div className="muted">{s.note}</div>}
          {s.items.map((i: any, n: number) => (
            <div key={n} className="row" style={{ margin: ".25rem 0" }}><span className={`tag ${i.tone}`}>●</span><Link href={i.href}>{i.text}</Link></div>))}
          {s.more > 0 && <div className="muted">and {s.more} more: <Link href={s.href}>open the full list</Link></div>}
        </section>))}
      {quiet.length > 0 && <section><h2>Nothing waiting</h2>
        <div className="muted">{quiet.map((s: any) => s.title).join(" · ")}</div></section>}
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

/** What a letter says now compared with the plain template for the same facts. A hint for the reader; it blocks nothing. */
export function ChangesVsTemplate({ changes, draftedBy }: { changes: any; draftedBy?: string }) {
  if (!changes) return null;
  if (!changes.known) return <div className="muted" data-testid="changes">No template to compare with: this letter was drafted before templates were kept.</div>;
  const who = draftedBy?.startsWith("AI") ? "The AI wrote this text" : "The template wrote this text";
  if (!changes.changed) return <div className="muted" data-testid="changes">Same as the template. {who}, and nobody has changed it.</div>;
  const shown = changes.lines.filter((l: any) => l.op !== "same");
  return (
    <details open data-testid="changes" className="letter">
      <summary><b>Changed from the template:</b> {changes.added} line(s) added, {changes.removed} removed{draftedBy ? ` · drafted by ${draftedBy}` : ""}</summary>
      <pre className="body-text" style={{ margin: ".4rem 0 0" }}>
        {shown.map((l: any, i: number) => <div key={i} style={{ color: l.op === "add" ? "var(--ok, #1a7f37)" : "var(--bad, #b42318)" }}>{l.op === "add" ? "+ " : "− "}{l.text || " "}</div>)}
      </pre>
    </details>
  );
}

/** How long decisions on letters take, and how often the text differs from the template. */
export function ReviewStats({ days }: { days: number }) {
  const [s, setS] = useState<any>(null);
  useEffect(() => { api(`/approvals/stats?days=${days}`).then(setS).catch(() => setS(null)); }, [days]);
  if (!s) return null;
  const fmt = (m: number | null) => (m == null ? "—" : m < 90 ? `${m} min` : `${(m / 60).toFixed(1)} h`);
  const share = (x: { compared: number; changed: number }) => (x.compared ? `${x.changed} of ${x.compared} changed` : "nothing compared yet");
  return (
    <section data-testid="review-stats">
      <h2>Letter review</h2>
      {s.decided === 0 ? <p className="muted">No letter was decided in the last {s.days} days.</p> : (
        <table><thead><tr><th>Letter</th><th className="num">Decided</th><th className="num">Approved</th><th className="num">Rejected</th><th className="num">Median time</th><th className="num">Longest</th><th>Differs from template</th></tr></thead>
          <tbody>{s.kinds.map((k: any) => <tr key={k.kind}><td>{k.kind}</td><td className="num">{k.decided}</td><td className="num">{k.approved}</td><td className="num">{k.rejected}</td><td className="num">{fmt(k.median_minutes)}</td><td className="num">{fmt(k.longest_minutes)}</td><td>{k.compared ? `${k.changed} of ${k.compared}` : "—"}</td></tr>)}</tbody></table>
      )}
      <p className="muted">AI drafts: {share(s.by_source.AI)} · template drafts: {share(s.by_source.template)}. {s.note}{s.decided_without_time > 0 ? ` ${s.decided_without_time} older decision(s) have no recorded time.` : ""}</p>
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

const LABELS: Record<string, string> = {
  confirmed: "confirmed by a person", needs_review: "needs review", parsed: "parsed by AI", not_request: "not a request",
  electronics: "electronics", it_hardware: "IT-hardware", other: "other", sr: "Serbian", en: "English",
  accepted: "accepted", rejected: "rejected", counter: "counter-offer", silence: "silence",
};

function Bars({ data, max }: { data: [string, number][]; max?: number }) {
  const m = max ?? Math.max(1, ...data.map(([, v]) => v));
  if (data.length === 0) return <div className="muted">No data yet.</div>;
  return <>{data.map(([k, v]) => (
    <div className="bar" key={k}><span>{LABELS[k] ?? k}</span><div className="track"><div className="fill" style={{ width: `${(100 * v) / m}%` }} /></div><span className="num">{v}</span></div>
  ))}</>;
}

function Volume({ data }: { data: { day: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const w = 600, h = 110, bw = w / data.length;
  return (
    <svg viewBox={`0 0 ${w} ${h + 24}`} width="100%" role="img" aria-label="Incoming emails per day">
      {data.map((d, i) => {
        const bh = (d.count / max) * h;
        return <g key={d.day}><rect x={i * bw + 1} y={h - bh} width={bw - 2} height={bh} rx={2} fill="var(--accent)" opacity={d.count ? 0.9 : 0.15}><title>{d.day}: {d.count}</title></rect></g>;
      })}
      <text x="0" y={h + 20} fontSize="16" fill="var(--muted)">{data[0]?.day}</text>
      <text x={w} y={h + 20} fontSize="16" fill="var(--muted)" textAnchor="end">{data.at(-1)?.day}</text>
    </svg>
  );
}

export default function Analytics() {
  const [a, setA] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  useEffect(() => { api(`/analytics/messages?days=${days}`).then(setA).catch((e) => setErr(e.message)); }, [days]);
  if (!a) return <p>{err || "Loading..."}</p>;
  const t = a.totals;
  const kpis: [string, string | number][] = [
    ["incoming emails", t.inbound], ["unparsed", t.unparsed], ["requests", t.requests],
    ["outgoing sent", t.outbound_sent], ["drafts awaiting approval", t.outbound_drafts],
    ["average AI confidence", a.avg_confidence == null ? "—" : `${Math.round(a.avg_confidence * 100)}%`],
  ];
  const top = a.funnel[0].count || 1;
  return (
    <>
      <div className="kpis">{kpis.map(([l, v]) => <div className="kpi" key={l}><div className="v">{v}</div><div className="l">{l}</div></div>)}</div>
      <div className="grid2">
        <section>
          <h2>Incoming emails per day <select style={{ float: "right" }} value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={14}>14 days</option><option value={30}>30 days</option><option value={90}>90 days</option></select></h2>
          <Volume data={a.volume} />
        </section>
        <section>
          <h2>Funnel: from email to order</h2>
          {a.funnel.map((f: any) => (
            <div className="bar" key={f.stage}><span>{f.stage}</span><div className="track"><div className="fill" style={{ width: `${(100 * f.count) / top}%` }} /></div><span className="num">{f.count}</span></div>
          ))}
          <p className="muted">Counted from database records; the “confirmed by a person” step is required before any outgoing email.</p>
        </section>
        <section><h2>Request statuses</h2><Bars data={Object.entries(a.by_status)} /></section>
        <section><h2>Email languages</h2><Bars data={Object.entries(a.by_language)} /><h2 style={{ marginTop: "1rem" }}>Categories</h2><Bars data={Object.entries(a.by_category)} /></section>
        <section><h2>Top senders</h2><Bars data={a.top_senders.map((s: any) => [s.sender, s.count])} /></section>
        <section>
          <h2>Supplier RFQs</h2>
          <table><tbody>
            <tr><td>RFQs sent</td><td className="num">{a.rfq.sent}</td></tr>
            <tr><td>Answers received (offers)</td><td className="num">{a.rfq.answered}</td></tr>
            <tr><td>of which simulated by the demo simulator</td><td className="num">{a.rfq.demo_simulated}</td></tr>
          </tbody></table>
          <h2 style={{ marginTop: "1rem" }}>Customer answers to quotes</h2>
          <Bars data={Object.entries(a.outcomes)} />
        </section>
        <section><h2>Items per request</h2><Bars data={Object.entries(a.items_per_request).map(([k, v]) => [`${k} items`, v as number])} /></section>
      </div>
    </>
  );
}

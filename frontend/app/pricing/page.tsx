"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

const pct = (x: number | null | undefined, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);

function Chart({ data, field, suggested, max, label }: { data: any[]; field: "win_rate" | "expected_margin"; suggested?: number[]; max: number; label: string }) {
  const w = 600, h = 120, bw = w / data.length;
  return (
    <svg viewBox={`0 0 ${w} ${h + 40}`} width="100%" role="img" aria-label={label}>
      {data.map((b, i) => {
        const v = b[field] ?? 0;
        const bh = (v / max) * h;
        const best = suggested && b.from === suggested[0];
        return (
          <g key={i}>
            <rect x={i * bw + 3} y={h - bh} width={bw - 6} height={bh} rx={3} fill={best ? "var(--ok)" : "var(--accent)"} opacity={b.usable ? 0.9 : 0.25}>
              <title>{pct(b.from)}–{pct(b.to)}: {b.n} quotes, win rate {pct(b.win_rate)}</title>
            </rect>
            <text x={i * bw + bw / 2} y={h + 16} fontSize="15" textAnchor="middle" fill="var(--muted)">{Math.round(b.from * 100)}</text>
            <text x={i * bw + bw / 2} y={h + 34} fontSize="13" textAnchor="middle" fill="var(--muted)">n={b.n}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default function Pricing() {
  const [d, setD] = useState<any>(null);
  const [customer, setCustomer] = useState("");
  const [category, setCategory] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const q = new URLSearchParams();
      if (customer) q.set("customer", customer);
      if (category) q.set("category", category);
      setD(await api(`/analytics/pricing?${q}`)); setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [customer, category]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <p>{err || "Loading..."}</p>;
  const s = d.summary, sug = d.suggestion;
  const empty = Object.keys(d.sources).length === 0;
  const maxMargin = Math.max(0.01, ...d.buckets.map((b: any) => b.expected_margin ?? 0));

  return (
    <>
      {err && <div className="err">{err}</div>}
      <p className="muted">Counts how often a quote is accepted at each markup and which markup earns the most (markup × win rate). Quotes made here join the statistics once the customer's answer is recorded. Demo history is synthetic with planted patterns and says nothing about any real market.</p>
      <div className="row">
        <select value={customer} onChange={(e) => setCustomer(e.target.value)}><option value="">all customers</option>{d.by_customer.map((c: any) => <option key={c.customer}>{c.customer}</option>)}</select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">all categories</option>{d.by_category.map((c: any) => <option key={c.category}>{c.category}</option>)}</select>
        <button onClick={async () => { await api("/analytics/demo-history", { method: "POST", json: {} }); load(); }}>Load synthetic history</button>
        <span className="muted">sources: {empty ? "none yet" : Object.entries(d.sources).map(([k, v]) => `${k} ${v}`).join(", ")}</span>
      </div>
      {empty && <section><span className="muted">No quotes with outcomes yet. Load the synthetic history to see the analysis, or record customer answers on real quotes.</span></section>}
      {!empty && (
        <>
          <div className="kpis">
            <div className="kpi"><div className="v">{s.n}</div><div className="l">quotes in view</div></div>
            <div className="kpi"><div className="v">{pct(s.win_rate)}</div><div className="l">accepted</div></div>
            <div className="kpi"><div className="v">{pct(s.avg_markup, 1)}</div><div className="l">average markup</div></div>
            <div className="kpi"><div className="v">{pct(s.avg_counter_discount, 1)}</div><div className="l">avg discount asked in counters</div></div>
            <div className="kpi" style={{ borderTopColor: "var(--ok)" }}><div className="v">{sug.markup == null ? "–" : pct(sug.markup, 1)}</div><div className="l">suggested markup</div></div>
          </div>
          <section>
            <h2>Suggestion</h2>
            {sug.markup == null ? <span className="muted">{sug.note}</span> : (
              <>
                <p style={{ margin: 0 }}>Quote about <b>{pct(sug.markup, 1)}</b> markup: expected win rate {pct(sug.win_rate)}, margin per euro of cost {sug.expected_margin}. Based on {sug.basis}{sug.segment ? ` “${sug.segment}”` : ""}, {sug.n_segment} quotes, fitted curve 50% at {pct(sug.fit?.midpoint, 1)} markup.</p>
                {sug.at_edge_of_data && <p className="err">The best point is at the edge of the markups seen so far. The data cannot say whether going further would pay; treat it as a floor or ceiling, not an optimum.</p>}
                <p className="muted">A suggestion only: a person decides the markup on every quote.</p>
              </>
            )}
          </section>
          <div className="grid2">
            <section><h2>Win rate by markup (%)</h2><Chart data={d.buckets} field="win_rate" max={1} label="Win rate by markup" suggested={sug.markup == null ? undefined : [Math.floor(sug.markup / 0.05) * 0.05]} /><p className="muted">Faded bars have fewer than {d.thresholds.min_bucket_n} quotes.</p></section>
            <section><h2>Expected margin per euro of cost</h2><Chart data={d.buckets} field="expected_margin" max={maxMargin} label="Expected margin" suggested={sug.markup == null ? undefined : [Math.floor(sug.markup / 0.05) * 0.05]} /></section>
          </div>
          <section>
            <h2>By customer</h2>
            <table>
              <thead><tr><th>Customer</th><th>Category</th><th>Quotes</th><th>Accepted</th><th>Avg markup</th><th>Suggested</th><th>Basis</th></tr></thead>
              <tbody>{d.by_customer.map((c: any) => (
                <tr key={c.customer} className="click" onClick={() => setCustomer(c.customer)}>
                  <td>{c.customer}</td><td>{c.category}</td><td className="num">{c.n}</td><td className="num">{pct(c.win_rate)}</td><td className="num">{pct(c.avg_markup, 1)}</td>
                  <td className="num"><b>{c.suggestion.markup == null ? "–" : pct(c.suggestion.markup, 1)}</b></td><td className="muted">{c.suggestion.basis}</td>
                </tr>))}</tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}

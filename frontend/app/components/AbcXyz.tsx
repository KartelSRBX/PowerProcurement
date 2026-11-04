"use client";

import { useEffect, useState } from "react";
import { api, eur } from "../lib/api";

const CLASSES = ["A", "B", "C"];
const STEADY = ["X", "Y", "Z"];

/** ABC by spend and XYZ by the steadiness of monthly demand, from the purchase orders. Boundaries are set in Settings. */
export function AbcXyz() {
  const [d, setD] = useState<any>(null);
  const [pick, setPick] = useState<string | null>(null);
  useEffect(() => { api("/analytics/abc-xyz").then(setD).catch(() => setD(null)); }, []);
  if (!d) return null;
  const b = d.boundaries;
  const cell = (a: string, x: string) => d.matrix[a + x];
  const rows = d.rows.filter((r: any) => !pick || r.class === pick || (pick.endsWith("-") && r.abc === pick[0] && !r.xyz));
  return (
    <section data-testid="abcxyz">
      <h2>ABC / XYZ of the articles bought <a style={{ float: "right", fontWeight: 400 }} href="/api/analytics/abc-xyz.xlsx">Download Excel</a></h2>
      {d.rows.length === 0 ? <p className="muted">No purchase order with prices per article in the last {d.window_months} months, so there is nothing to classify yet.</p> : <>
        <p className="muted">A: articles that make up the first {b.a_pct}% of spend, B: up to {b.b_pct}%, C: the rest. X: monthly quantity varies by up to {b.x_max} (standard deviation over mean), Y: up to {b.y_max}, Z: more. {d.orders_used} order(s), {eur(d.total_spend_eur)} EUR, last {d.window_months} months.</p>
        {!d.xyz_available && <div className="err" data-testid="xyz-note">{d.xyz_note}</div>}
        <table><thead><tr><th></th>{(d.xyz_available ? STEADY : ["-"]).map((x) => <th key={x} className="num">{x === "-" ? "no XYZ yet" : x}</th>)}</tr></thead>
          <tbody>{CLASSES.map((a) => <tr key={a}><td><b>{a}</b></td>{(d.xyz_available ? STEADY : ["-"]).map((x) => {
            const c = cell(a, x); const code = a + x;
            return <td key={x} className="num"><a href="#" onClick={(e) => { e.preventDefault(); setPick(pick === code ? null : code); }}>{c.articles} · {eur(c.spend_eur)} EUR</a></td>;
          })}</tr>)}</tbody></table>
        <table style={{ marginTop: ".8rem" }}><thead><tr><th>Article</th><th className="num">Orders</th><th className="num">Quantity</th><th className="num">Spend EUR</th><th className="num">Share</th><th className="num">Cumulative</th><th>ABC</th><th className="num">Variation</th><th>XYZ</th></tr></thead>
          <tbody>{rows.map((r: any) => <tr key={r.key}><td>{r.label}</td><td className="num">{r.orders}</td><td className="num">{r.quantity}</td><td className="num">{eur(r.spend_eur)}</td><td className="num">{r.share_pct}%</td><td className="num">{r.cumulative_pct}%</td><td><span className="tag">{r.abc}</span></td><td className="num">{r.cv ?? "—"}</td><td>{r.xyz ? <span className="tag">{r.xyz}</span> : "—"}</td></tr>)}</tbody></table>
        {pick && <p className="muted">Showing class {pick.replace("-", "")} only. <a href="#" onClick={(e) => { e.preventDefault(); setPick(null); }}>Show all</a></p>}
        <p className="muted">{d.note} {d.orders_not_itemised > 0 ? `${d.orders_not_itemised} order(s) have no price per article and are left out. ` : ""}{d.orders_cancelled > 0 ? `${d.orders_cancelled} cancelled order(s) are not counted.` : ""}</p>
      </>}
    </section>
  );
}

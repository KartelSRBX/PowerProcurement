"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, eur } from "../lib/api";

const sign = (n: number | null) => (n == null ? "-" : `${n > 0 ? "+" : ""}${eur(n)}`);

export default function Savings() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<any>("/savings").then(setD).catch((e) => setErr(e.message)); }, []);
  if (!d) return <p>{err || "Loading..."}</p>;
  const t = d.totals;
  return (
    <>
      <h1>Savings ledger</h1>
      <p className="muted">For each order a person records a baseline: what the goods would have cost without the buyer’s work, and on what basis. <b>Negotiated</b> is the baseline minus what was agreed (the offer behind the order). <b>Realized</b> is the baseline minus the supplier’s invoice, counted only once a person has accepted that invoice. Goods without VAT, in EUR at the Settings rates; freight and duty are not in this ledger.</p>
      <div className="kpis" data-testid="savings-totals">
        <div className="kpi"><div className="v">{sign(t.negotiated_saving_eur)}</div><div className="l">negotiated saving, EUR · {t.negotiated_saving_pct ?? "-"}% of {eur(t.baseline_eur)} baseline · {t.orders} order(s)</div></div>
        <div className="kpi"><div className="v">{sign(t.realized_saving_eur)}</div><div className="l">realized saving, EUR · {t.realized_saving_pct ?? "-"}% of {eur(t.realized_baseline_eur)} · {t.realized_orders} order(s) with an accepted invoice{t.realized_accepted_with_difference > 0 && `, ${t.realized_accepted_with_difference} accepted with a difference`}</div></div></div>
      <div className="row"><a href="/api/savings/export.xlsx"><button>Export to Excel</button></a></div>
      {d.orders_without_baseline > 0 && <p className="muted">{d.orders_without_baseline} order(s) have no baseline yet and are not counted. Set one on the order’s page.</p>}
      {d.rows.length === 0 ? <p className="muted">No baselines yet.</p> :
        <table><thead><tr><th>Order</th><th>Supplier</th><th>Baseline</th><th>Agreed</th><th>Negotiated</th><th>Invoice</th><th>Realized</th></tr></thead><tbody>
          {d.rows.map((r: any) => <tr key={r.order_id}>
            <td><Link href={`/requests/${r.request_id}`}>PO #{r.order_id}</Link></td><td>{r.supplier}</td>
            <td className="num">{eur(r.baseline_eur)}<div className="muted">{r.basis_label}{r.note && `: ${r.note}`}</div></td>
            <td className="num">{eur(r.negotiated_eur)}</td>
            <td className={`num ${r.negotiated_saving_eur < 0 ? "bad" : ""}`}>{sign(r.negotiated_saving_eur)}<div className="muted">{r.negotiated_saving_pct}%</div></td>
            <td>{r.invoice_number ? <>{r.invoice_number}<div className="muted">{eur(r.invoiced_eur)} · {r.invoice_state}{r.invoice_differs && " (differs from the order)"}</div></> : <span className="muted">none</span>}</td>
            <td className={`num ${r.realized_saving_eur != null && r.realized_saving_eur < 0 ? "bad" : ""}`}>{r.realized_saving_eur == null ? <span className="muted">not yet</span> : <>{sign(r.realized_saving_eur)}<div className="muted">{r.realized_saving_pct}%</div></>}</td></tr>)}</tbody></table>}
    </>
  );
}

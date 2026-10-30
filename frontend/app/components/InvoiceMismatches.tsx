"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, eur } from "../lib/api";

const KINDS: Record<string, string> = { total: "total", price: "unit price", quantity: "quantity", missing_item: "missing item", lines_sum: "lines don't add up", foreign_line: "unknown line", duplicate_number: "duplicate number" };

/** Supplier invoices that differ from their orders, what differs, and the largest amount first. Nothing is changed from here. */
export function InvoiceMismatches() {
  const [d, setD] = useState<any>(null);
  const [kind, setKind] = useState("");
  const [show, setShow] = useState("open");
  const load = useCallback(() => api<any>(`/supplier-invoices/mismatches?show=${show}${kind ? `&kind=${kind}` : ""}`).then(setD).catch(() => setD(null)), [kind, show]);
  useEffect(() => { load(); }, [load]);
  if (!d || (d.count === 0 && !kind && show === "open")) return null;
  return (
    <section data-testid="invoice-mismatches">
      <h2>Invoices that differ from their orders <span className="tag bad">{d.count}</span></h2>
      <p className="muted">Each supplier invoice entered on an order is compared with the offer behind it (tolerance in Settings). The largest difference is first. Open the order to accept an invoice or correct the entry.</p>
      <div className="row">
        <label>Show <select value={show} onChange={(e) => setShow(e.target.value)}><option value="open">not yet accepted</option><option value="accepted">accepted with differences</option><option value="all">all</option></select></label>
        <label>Kind <select value={kind} onChange={(e) => setKind(e.target.value)}><option value="">any ({Object.values<number>(d.by_kind).reduce((a, b) => a + b, 0)} findings)</option>
          {Object.entries(KINDS).map(([k, l]) => <option key={k} value={k}>{l} ({d.by_kind[k]})</option>)}</select></label></div>
      {d.count === 0 ? <p className="muted">Nothing here.</p> :
        <table><thead><tr><th>Order</th><th>Supplier</th><th>Invoice</th><th>Difference</th><th>What differs</th></tr></thead><tbody>
          {d.rows.map((r: any) => <tr key={r.order_id}>
            <td><Link href={`/requests/${r.request_id}`}>PO #{r.order_id}</Link></td><td>{r.supplier}</td>
            <td>{r.number}<div className="muted">{r.invoice_date} · {eur(r.total_net)} {r.currency}</div></td>
            <td className={`num ${r.difference > 0 ? "bad" : ""}`}>{r.difference > 0 ? "+" : ""}{eur(r.difference)} {r.difference_in}</td>
            <td>{r.kinds.map((k: string) => <span key={k} className="tag bad" style={{ marginRight: 4 }}>{KINDS[k]}</span>)}
              {r.issues.map((i: any, n: number) => <div key={n} className="muted">{i.text}</div>)}
              {r.accepted_by && <div className="muted">accepted by {r.accepted_by}: {r.accept_reason}</div>}</td></tr>)}</tbody></table>}
    </section>
  );
}

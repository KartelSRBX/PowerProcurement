"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

/** Orders whose promised date has passed. The question to each supplier is only prepared here: a person approves it in Approvals. */
export function Overdue() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const load = useCallback(() => api<any[]>("/orders/overdue").then(setRows).catch(() => setRows(null)), []);
  useEffect(() => { load(); }, [load]);
  if (!rows || rows.length === 0) return null;

  async function ask(id?: number) {
    setNote(null);
    try {
      if (id) { await api(`/orders/${id}/delay-question`, { method: "POST" }); setNote({ ok: true, text: "The question is ready in Approvals." }); }
      else {
        const r = await api<any>("/orders/overdue/questions", { method: "POST" });
        setNote({ ok: true, text: `${r.letters.length} question(s) are ready in Approvals${r.skipped.length ? `; ${r.skipped.length} order(s) already have one` : ""}.` });
      }
      await load();
    } catch (e: any) { setNote({ ok: false, text: e.message }); }
  }
  const waiting = rows.filter((r) => r.question === "none").length;
  return (
    <section data-testid="overdue">
      <h2>Overdue deliveries <span className="tag bad">{rows.length}</span></h2>
      <p className="muted">The promised date has passed and the order is neither delivered nor cancelled. A question to the supplier is prepared for you and waits in Approvals; nothing is sent until a person approves it.</p>
      <table><thead><tr><th>Order</th><th>Supplier</th><th>Promised</th><th>Late</th><th>Status</th><th>Question</th><th></th></tr></thead><tbody>
        {rows.map((r) => <tr key={r.order_id}>
          <td><Link href={`/requests/${r.request_id}`}>PO #{r.order_id}</Link></td><td>{r.supplier}</td>
          <td>{new Date(r.promised_date + "T00:00:00").toLocaleDateString("en-GB")}</td>
          <td><span className="tag bad">{r.overdue_days} day(s)</span></td><td className="muted">{r.status_label}</td>
          <td>{r.question === "waiting" ? <Link href="/approvals">waits for approval</Link> : r.question === "sent" ? <span className="muted">asked {r.last_asked}</span> : <span className="muted">not asked</span>}</td>
          <td>{r.question === "none" && <button onClick={() => ask(r.order_id)}>Prepare question</button>}</td></tr>)}</tbody></table>
      <div className="row"><button className="primary" disabled={waiting === 0} onClick={() => ask()}>Prepare questions for all ({waiting})</button></div>
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
    </section>
  );
}

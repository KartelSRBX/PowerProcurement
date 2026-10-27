"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../../lib/api";

const STATUSES: [string, string][] = [["ordered", "ordered, no confirmation yet"], ["confirmed", "supplier confirmed the date"], ["shipped", "shipped"], ["delivered", "delivered"], ["cancelled", "cancelled"]];
const day = (iso?: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-GB") : "not set");

/** The delivery record of one order: the date the supplier is expected to deliver, where the goods are, and why dates moved. */
export function Delivery({ po, who }: { po: any; who: string }) {
  const [d, setD] = useState<any>(null);
  const [date, setDate] = useState("");
  const [status, setStatus] = useState("");
  const [delivered, setDelivered] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const v = await api<any>(`/orders/${po.id}/delivery`);
      setD(v); setDate(v.promised_date ?? ""); setStatus(v.status); setDelivered(""); setReason("");
    } catch (e: any) { setErr(e.message); }
  }, [po.id]);
  useEffect(() => { load(); }, [load]);

  async function save() {
    setErr("");
    const body: any = { changed_by: who, reason };
    if (date && date !== d.promised_date) body.promised_date = date;
    if (status !== d.status) { body.status = status; if (status === "delivered" && delivered) body.delivered_date = delivered; }
    try { setD(await api<any>(`/orders/${po.id}/delivery`, { method: "PUT", json: body })); await load(); }
    catch (e: any) { setErr(e.message); }
  }

  if (!d) return <div className="muted">{err || "Loading delivery..."}</div>;
  const changed = (date && date !== d.promised_date) || status !== d.status;
  const needsReason = d.promised_date && date && date !== d.promised_date;
  return (
    <div className="letter" data-testid="delivery">
      <div className="row"><b>Delivery</b>
        <span className={`tag ${d.status === "delivered" ? "ok" : d.overdue_days > 0 ? "bad" : "acc"}`}>{d.status_label}</span>
        {d.overdue_days > 0 && <span className="tag bad">{d.overdue_days} day(s) overdue</span>}
        <span>expected <b>{day(d.promised_date)}</b>{d.delivered_date && <> · delivered <b>{day(d.delivered_date)}</b></>}</span></div>
      {d.status === "ordered" && <div className="muted">The date is calculated from the offer’s lead time. Record the supplier’s own confirmation when it arrives.</div>}
      {!d.final && <div className="row">
        <label>Expected on <input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <label>Status <select value={status} onChange={(e) => setStatus(e.target.value)}>{STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {status === "delivered" && d.status !== "delivered" && <label>Delivered on <input type="date" value={delivered} onChange={(e) => setDelivered(e.target.value)} /></label>}
        <input style={{ flex: 1, minWidth: "14rem" }} placeholder={needsReason ? "Why the date moved (required)" : "Note (optional)"} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        <button className="primary" disabled={!who || !changed || (needsReason && !reason.trim())} onClick={save}>Save</button>
        {!who && <span className="muted">Enter your name at the top.</span>}</div>}
      {err && <div className="err">{err}</div>}
      <table><thead><tr><th>When</th><th>What</th><th>From</th><th>To</th><th>Why</th><th>By</th></tr></thead><tbody>
        {d.history.map((h: any) => <tr key={h.id}><td>{fmtDate(h.at)}</td>
          <td>{h.kind === "promised_date" ? "expected date" : h.kind === "delivered_date" ? "delivery date" : "status"}</td>
          <td>{h.old ?? "-"}</td><td>{h.new}</td><td className="muted">{h.reason}</td><td>{h.by}</td></tr>)}</tbody></table>
    </div>
  );
}

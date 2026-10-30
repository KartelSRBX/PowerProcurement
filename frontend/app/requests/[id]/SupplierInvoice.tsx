"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../../lib/api";

const money = (n: number | null | undefined, cur = "") => (n == null ? "-" : `${n.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`.trim());

/** The supplier's invoice for one order, typed in by a person, compared with the order, accepted by a named person. */
export function SupplierInvoice({ po, who }: { po: any; who: string }) {
  const [v, setV] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ number: "", date: new Date().toISOString().slice(0, 10), currency: "EUR", total: "", vat: "", note: "" });
  const [withLines, setWithLines] = useState(false);
  const [ln, setLn] = useState<Record<number, { q: string; p: string }>>({});
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      const [inv, its] = await Promise.all([api<any>(`/orders/${po.id}/supplier-invoice`), api<any[]>(`/requests/${po.request_id}/items`)]);
      setV(inv); setItems(its); setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [po.id, po.request_id]);
  useEffect(() => { load(); }, [load]);

  async function save() {
    setErr("");
    const lines = withLines ? items.filter((i) => ln[i.id]?.q).map((i) => ({ item_id: i.id, quantity: Number(ln[i.id].q), unit_price: Number(ln[i.id].p || 0) })) : null;
    try {
      setV(await api<any>(`/orders/${po.id}/supplier-invoice`, { method: "PUT", json: { entered_by: who, number: f.number, invoice_date: f.date, currency: f.currency, total_net: Number(f.total), vat_amount: f.vat === "" ? null : Number(f.vat), lines, note: f.note } }));
      setOpen(false);
    } catch (e: any) { setErr(e.message); }
  }
  async function act(path: string, init: any) {
    setErr("");
    try { setV(await api<any>(path, init)); setReason(""); } catch (e: any) { setErr(e.message); }
  }
  function edit() {
    const i = v.invoice;
    setF({ number: i.number, date: i.invoice_date, currency: i.currency, total: String(i.total_net), vat: i.vat_amount == null ? "" : String(i.vat_amount), note: i.note });
    setWithLines(!!i.lines);
    setLn(Object.fromEntries((i.lines ?? []).map((x: any) => [x.item_id, { q: String(x.quantity), p: String(x.unit_price) }])));
    setOpen(true);
  }

  if (!v) return <div className="muted">{err || "Loading invoice..."}</div>;
  const inv = v.invoice, c = v.comparison;
  const ok = (b: boolean | null) => (b == null ? "" : b ? "ok" : "bad");
  return (
    <div className="letter" data-testid="supplier-invoice">
      <div className="row"><b>Supplier invoice</b>
        {!inv && <span className="muted">none entered yet</span>}
        {inv && <><span>{inv.number} · {inv.invoice_date} · <b>{money(inv.total_net, inv.currency)}</b> without VAT{inv.vat_amount != null && <> (VAT {money(inv.vat_amount, inv.currency)})</>}</span>
          <span className={`tag ${c.status === "matches" ? "ok" : "bad"}`}>{c.status === "matches" ? "matches the order" : "differs from the order"}</span>
          {inv.accepted_by && <span className="tag ok">accepted by {inv.accepted_by}</span>}</>}
        {!open && !inv?.accepted_by && <button disabled={!who} onClick={() => (inv ? edit() : setOpen(true))}>{inv ? "Change" : "Enter invoice"}</button>}</div>

      {open && <div>
        <div className="row">
          <label>Number <input style={{ width: "9rem" }} value={f.number} onChange={(e) => setF({ ...f, number: e.target.value })} data-testid="inv-number" /></label>
          <label>Date <input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></label>
          <label>Currency <input style={{ width: "4rem" }} maxLength={3} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} /></label>
          <label>Total without VAT <input style={{ width: "8rem" }} value={f.total} onChange={(e) => setF({ ...f, total: e.target.value })} data-testid="inv-total" /></label>
          <label>VAT (optional) <input style={{ width: "6rem" }} value={f.vat} onChange={(e) => setF({ ...f, vat: e.target.value })} /></label></div>
        <div className="row"><label><input type="checkbox" checked={withLines} onChange={(e) => setWithLines(e.target.checked)} /> Enter the lines too (then quantity and unit price are checked per item)</label></div>
        {withLines && <table><thead><tr><th>Item</th><th>Ordered</th><th>Invoiced quantity</th><th>Unit price</th></tr></thead><tbody>
          {items.map((i) => <tr key={i.id}><td>{i.description}</td><td className="num">{i.quantity ?? "-"}</td>
            <td><input style={{ width: "6rem" }} value={ln[i.id]?.q ?? ""} onChange={(e) => setLn({ ...ln, [i.id]: { q: e.target.value, p: ln[i.id]?.p ?? "" } })} /></td>
            <td><input style={{ width: "6rem" }} value={ln[i.id]?.p ?? ""} onChange={(e) => setLn({ ...ln, [i.id]: { q: ln[i.id]?.q ?? "", p: e.target.value } })} /></td></tr>)}</tbody></table>}
        <div className="row"><input style={{ flex: 1, minWidth: "14rem" }} placeholder="Note (optional)" maxLength={300} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
          <button className="primary" disabled={!who || !f.number.trim() || !(Number(f.total) > 0)} onClick={save}>Save invoice</button>
          <button onClick={() => setOpen(false)}>Cancel</button></div>
      </div>}

      {inv && c && <>
        <div className="muted">Ordered {money(c.ordered_total, c.compared_in)} · invoiced {money(c.invoiced_total, c.compared_in)} · difference {money(c.difference, c.compared_in)}{c.difference_pct != null && ` (${c.difference_pct > 0 ? "+" : ""}${c.difference_pct}%)`} · tolerance {c.tolerance_pct}% (Settings)</div>
        {c.reasons.map((r: string, i: number) => <div key={i} className="err">{r}</div>)}
        {c.notes?.map((r: string, i: number) => <div key={i} className="muted">{r}</div>)}
        {c.lines.length > 0 && <table><thead><tr><th>Item</th><th>Ordered</th><th>Invoiced</th><th>Unit price ordered</th><th>Unit price invoiced</th></tr></thead><tbody>
          {c.lines.map((r: any) => <tr key={r.item_id}><td>{r.description}</td><td className="num">{r.ordered_quantity ?? "-"}</td>
            <td className={`num ${ok(r.quantity_ok)}`}>{r.invoiced_quantity ?? "not invoiced"}</td>
            <td className="num">{r.ordered_unit_price ?? "-"}</td>
            <td className={`num ${ok(r.price_ok)}`}>{r.invoiced_unit_price ?? "-"}{r.price_pct != null && ` (${r.price_pct > 0 ? "+" : ""}${r.price_pct}%)`}</td></tr>)}</tbody></table>}
        {inv.note && <div className="muted">Note: {inv.note}</div>}
        <div className="muted">Entered by {inv.entered_by}{inv.accepted_by && <> · accepted by {inv.accepted_by} on {fmtDate(inv.accepted_at)}{inv.accept_reason && <>: {inv.accept_reason}</>}</>}. Nothing is paid or posted from here.</div>
        {!inv.accepted_by && <div className="row">
          <input style={{ flex: 1, minWidth: "14rem" }} placeholder={c.status === "differs" ? "Why it is accepted anyway (required)" : "Note (optional)"} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="inv-reason" />
          <button className="primary" disabled={!who || (c.status === "differs" && reason.trim().length < 3)} onClick={() => act(`/orders/${po.id}/supplier-invoice/accept`, { method: "POST", json: { by: who, reason } })}>Accept invoice</button>
          <button disabled={!who} onClick={() => act(`/orders/${po.id}/supplier-invoice?removed_by=${encodeURIComponent(who)}`, { method: "DELETE" })}>Remove</button></div>}
      </>}
      {err && <div className="err">{err}</div>}
      {!who && <div className="muted">Enter your name at the top.</div>}
    </div>
  );
}

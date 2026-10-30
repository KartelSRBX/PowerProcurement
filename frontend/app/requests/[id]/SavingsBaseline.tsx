"use client";

import { useCallback, useEffect, useState } from "react";
import { api, eur } from "../../lib/api";

/** The baseline of one order for the savings ledger: what the goods would have cost, and on what basis a named person says so. */
export function SavingsBaseline({ po, who }: { po: any; who: string }) {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [basis, setBasis] = useState("manual");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try { setV(await api<any>(`/orders/${po.id}/savings`)); setErr(""); } catch (e: any) { setErr(e.message); }
  }, [po.id]);
  useEffect(() => { load(); }, [load]);

  async function save() {
    setErr("");
    try {
      setV(await api<any>(`/orders/${po.id}/savings/baseline`, { method: "PUT", json: { set_by: who, basis, amount_eur: basis === "manual" ? Number(amount) : null, note } }));
      setOpen(false); setAmount(""); setNote("");
    } catch (e: any) { setErr(e.message); }
  }
  async function clear() {
    setErr("");
    try { setV(await api<any>(`/orders/${po.id}/savings/baseline?cleared_by=${encodeURIComponent(who)}`, { method: "DELETE" })); }
    catch (e: any) { setErr(e.message); }
  }

  if (!v) return <div className="muted">{err || "Loading savings..."}</div>;
  const b = v.baseline;
  const saving = b ? b.amount_eur - v.negotiated_eur : null;
  return (
    <div className="letter" data-testid="savings-baseline">
      <div className="row"><b>Savings baseline</b>
        {b ? <><span><b>{eur(b.amount_eur)} EUR</b> · {b.label}{b.note && ` · ${b.note}`} · set by {b.set_by}</span>
          <span className={`tag ${saving! >= 0 ? "ok" : "bad"}`}>negotiated {saving! >= 0 ? "saving" : "overspend"} {eur(Math.abs(saving!))} EUR ({(100 * saving! / b.amount_eur).toFixed(1)}%)</span></>
          : <span className="muted">not set: agreed {eur(v.negotiated_eur)} EUR (goods, without VAT)</span>}
        {!open && <button disabled={!who} onClick={() => { setOpen(true); setBasis(v.candidates[0]?.basis ?? "manual"); }}>{b ? "Change" : "Set baseline"}</button>}
        {b && !open && <button disabled={!who} onClick={clear}>Clear</button>}</div>
      {open && <div>
        {v.candidates.map((c: any) => <div className="row" key={c.basis}><label><input type="radio" checked={basis === c.basis} onChange={() => setBasis(c.basis)} /> {c.label}: <b>{eur(c.amount_eur)} EUR</b></label><span className="muted">{c.detail}</span></div>)}
        <div className="row"><label><input type="radio" checked={basis === "manual"} onChange={() => setBasis("manual")} /> Typed by a person</label>
          {basis === "manual" && <><input style={{ width: "8rem" }} placeholder="Amount, EUR" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="bl-amount" />
            <input style={{ flex: 1, minWidth: "14rem" }} placeholder="Where it comes from (required)" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} data-testid="bl-note" /></>}
          <button className="primary" disabled={!who || (basis === "manual" && (!(Number(amount) > 0) || note.trim().length < 3))} onClick={save}>Save baseline</button>
          <button onClick={() => setOpen(false)}>Cancel</button></div>
      </div>}
      {err && <div className="err">{err}</div>}
    </div>
  );
}

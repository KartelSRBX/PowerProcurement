"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";
import { CHECK_LABEL, CHECK_TAG } from "../suppliers/Profile";

const FILTERS = ["", "unchecked", "working", "under_review", "not_working"];

export default function Checks() {
  const { person } = usePerson();
  const named = person.trim().length > 0;
  const [result, setResult] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [all, setAll] = useState<any[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [f, setF] = useState({ result: "working", contact_details: "", note: "" });
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [shown, everything] = await Promise.all([api<any[]>(`/suppliers/checks?result=${result}`), api<any[]>("/suppliers/checks")]);
      setRows(shown); setAll(everything); setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [result]);
  useEffect(() => { load(); }, [load]);

  const count = (r: string) => (r ? all.filter((x) => x.result === r).length : all.length);
  const cur = rows.find((r) => r.supplier_id === sel) ?? null;

  async function record() {
    if (!cur) return;
    setErr("");
    try {
      await api(`/suppliers/${cur.supplier_id}/checks`, { method: "POST", json: { ...f, checked_by: person } });
      setF({ result: "working", contact_details: "", note: "" });
      await load();
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <>
      <div className="tabs">
        {FILTERS.map((r) => (
          <div key={r} className={`tab ${result === r ? "active" : ""}`} onClick={() => { setResult(r); setSel(null); }}>
            {r ? CHECK_LABEL[r] : "All"} ({count(r)})
          </div>))}
      </div>
      {err && <div className="err">{err}</div>}
      <div className="split two">
        <div className="pane">
          <div className="pane-h"><span className="muted">Newest check per supplier. “Not working” suppliers are left out of new shortlists.</span></div>
          <table>
            <thead><tr><th>Supplier</th><th>Country</th><th>Result</th><th>Checked by</th><th>When</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.supplier_id} className={`click ${r.supplier_id === sel ? "sel" : ""}`} onClick={() => setSel(r.supplier_id)}>
                <td>{r.name}</td><td>{r.country}</td>
                <td><span className={`tag ${CHECK_TAG[r.result]}`}>{CHECK_LABEL[r.result]}</span></td>
                <td>{r.checked_by ?? ""}</td><td className="muted">{fmtDate(r.checked_at)}</td>
              </tr>))}</tbody>
          </table>
          {rows.length === 0 && <div className="pane-b muted">Nothing here.</div>}
        </div>
        <div className="pane">
          {!cur ? <div className="pane-b muted">Pick a supplier to record a check.</div> : (
            <>
              <div className="pane-h"><b>{cur.name}</b> <Link href="/suppliers" className="muted">open profile and history →</Link></div>
              <div className="pane-b">
                {cur.note && <p>Last note: {cur.note}{cur.contact_details ? ` (contact: ${cur.contact_details})` : ""}</p>}
                <div className="row">
                  <select value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}><option value="working">working</option><option value="under_review">under review</option><option value="not_working">not working</option></select>
                </div>
                <div className="row"><input placeholder="who we spoke to / contact" style={{ flex: 1 }} value={f.contact_details} onChange={(e) => setF({ ...f, contact_details: e.target.value })} /></div>
                <div className="row"><input placeholder="note" style={{ flex: 1 }} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></div>
                <div className="row"><button className="primary" disabled={!named} onClick={record}>Record check</button>{!named && <span className="muted">Enter your name at the top.</span>}</div>
              </div>
            </>)}
        </div>
      </div>
    </>
  );
}

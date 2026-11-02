"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

const TAG: Record<string, string> = { overdue: "bad", today: "bad", soon: "warn", later: "", no_date: "" };
const when = (s: string, days: number | null) =>
  s === "overdue" ? `${-(days ?? 0)} day(s) late` : s === "today" ? "today" : s === "no_date" ? "no date" : `in ${days} day(s)`;

/** Open requests that are marked urgent or carry a reply-by date: what still has to reach the customer as a quote. */
export function UrgentBoard() {
  const [v, setV] = useState<any>(null);
  useEffect(() => { api<any>("/requests/urgent").then(setV).catch(() => setV(null)); }, []);
  if (!v || v.items.length === 0) return null;
  const c = v.counts;
  return (
    <section data-testid="urgent-board">
      <h2>Urgent requests {c.overdue > 0 && <span className="tag bad">{c.overdue} late</span>} {c.today > 0 && <span className="tag bad">{c.today} due today</span>}</h2>
      <p className="muted">Requests a person marked urgent or gave a reply-by date, still waiting for a quote to the customer. A request leaves the board when its quote is sent.</p>
      <table><thead><tr><th>#</th><th>Customer</th><th>Subject</th><th>Reply by</th><th></th><th>Step</th><th>Next</th></tr></thead><tbody>
        {v.items.map((i: any) => (
          <tr key={i.request_id}>
            <td><Link href={`/requests/${i.request_id}`}>{i.request_id}</Link></td><td>{i.sender}</td><td>{i.subject}</td>
            <td>{i.respond_by ?? <span className="muted">not set</span>}</td>
            <td><span className={`tag ${TAG[i.state]}`}>{when(i.state, i.days_left)}</span> {i.urgent && <span className="tag bad">urgent</span>}</td>
            <td><span className="tag">{i.stage}</span></td><td className="muted">{i.next}{i.note ? ` · ${i.note}` : ""}</td>
          </tr>))}
      </tbody></table>
    </section>
  );
}

/** The flag and the reply-by date of one request, set by a named person. */
export function UrgencyPanel({ id, who }: { id: string | number; who: string }) {
  const [d, setD] = useState<any>(null);
  const [f, setF] = useState({ urgent: false, respond_by: "", note: "" });
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try {
      const r = await api<any>(`/requests/${id}/urgency`);
      setD(r); setF({ urgent: r.urgent, respond_by: r.respond_by ?? "", note: r.note ?? "" }); setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  async function save() {
    setErr("");
    try { await api(`/requests/${id}/urgency`, { method: "PUT", json: { changed_by: who, urgent: f.urgent, respond_by: f.respond_by || null, note: f.note } }); await load(); }
    catch (e: any) { setErr(e.message); }
  }
  if (!d) return err ? <div className="err">{err}</div> : null;
  return (
    <div className="letter" data-testid="urgency">
      <div className="row">
        <b>Urgency</b>
        {d.urgent && <span className="tag bad">urgent</span>}
        {d.respond_by && <span className={`tag ${TAG[d.state]}`}>reply by {d.respond_by}: {when(d.state, d.days_left)}</span>}
        {d.needed_by && <span className="muted">customer needs the goods by {d.needed_by}{d.needed_in_days != null ? ` (${d.needed_in_days} day(s))` : ""}</span>}
        {d.set_by && <span className="muted">set by {d.set_by}</span>}
      </div>
      <div className="row">
        <label><input type="checkbox" checked={f.urgent} onChange={(e) => setF({ ...f, urgent: e.target.checked })} /> urgent</label>
        <label>Reply to the customer by <input type="date" value={f.respond_by} onChange={(e) => setF({ ...f, respond_by: e.target.value })} /></label>
        <input placeholder="why (optional)" style={{ flex: 1 }} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        <button className="primary" disabled={!who} onClick={save}>Save</button>
      </div>
      {err && <div className="err">{err}</div>}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

const TAG: Record<string, string> = { ok: "ok", due_soon: "warn", overdue: "bad", never: "bad" };
const WORD: Record<string, string> = { ok: "current", due_soon: "due soon", overdue: "overdue", never: "never done" };
const today = () => new Date().toISOString().slice(0, 10);

/** Suppliers whose sanctions screening or beneficiary needs a person: overdue, never done, coming due. */
export function RecheckList({ onOpen }: { onOpen: (id: number) => void }) {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api<any>("/suppliers/rechecks").then(setV).catch((e) => setErr(e.message)); }, []);
  if (!v) return <div className="muted">{err || "Loading..."}</div>;
  const c = v.counts;
  return (
    <section data-testid="rechecks">
      <h2>Supplier re-checks</h2>
      <p className="muted">A sanctions screening and the beneficiary have to be repeated. The app downloads no list and decides nothing: a person checks a list they name and records the date and result.
        A screening counts for {v.default_months} months unless a supplier has its own period (Settings). Suppliers on hold are left out.</p>
      <div className="kpis">
        {([["need attention", c.attention], ["overdue", c.overdue], ["never screened", c.never], ["due within " + v.warn_days + " days", c.due_soon], ["no beneficiary", c.no_beneficiary]] as const).map(([l, n]) => (
          <div className="kpi" key={l}><div className="v" style={{ fontSize: "1.2rem" }}>{n}</div><div className="l">{l}</div></div>))}
      </div>
      {v.items.length === 0 && <div className="muted">Everything is current.</div>}
      <table><thead><tr><th>Supplier</th><th>Screening</th><th>Beneficiary</th><th>Why it is listed</th></tr></thead><tbody>
        {v.items.map((i: any) => (
          <tr key={i.supplier_id} className="click" onClick={() => onOpen(i.supplier_id)}>
            <td>{i.name} <span className="tag">{i.country}</span> {i.has_orders && <span className="tag">has orders</span>}</td>
            <td><span className={`tag ${TAG[i.screening.status]}`}>{WORD[i.screening.status]}</span>{i.screening.attention && <span className="tag bad">needs attention</span>}</td>
            <td><span className={`tag ${TAG[i.beneficiary.status]}`}>{i.beneficiary.status === "never" ? "not recorded" : WORD[i.beneficiary.status]}</span></td>
            <td className="muted">{i.reasons.join("; ")}</td>
          </tr>))}
      </tbody></table>
    </section>
  );
}

/** One supplier: the screening record, the re-check period and the beneficiary. */
export function CompliancePanel({ supplierId, person, onChanged }: { supplierId: number; person: string; onChanged?: () => void }) {
  const named = person.trim().length > 0;
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  const [s, setS] = useState({ checked_on: today(), list_name: "", result: "clear", note: "" });
  const [sched, setSched] = useState({ period: "", next: "" });
  const [b, setB] = useState({ owners: "", source: "business_register", confirmed_on: today(), note: "" });
  const [editB, setEditB] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api<any>(`/suppliers/${supplierId}/compliance`);
      setV(r); setErr("");
      setSched({ period: r.screening.own_period ? String(r.screening.period_months) : "", next: r.next_check_on ?? "" });
    } catch (e: any) { setErr(e.message); }
  }, [supplierId]);
  useEffect(() => { setEditB(false); load(); }, [load]);
  async function run(fn: () => Promise<any>, after?: () => void) {
    setErr("");
    try { setV(await fn()); after?.(); onChanged?.(); await load(); } catch (e: any) { setErr(e.message); }
  }
  if (!v) return <div className="muted">{err || "Loading re-checks..."}</div>;
  const sc = v.screening, ben = v.beneficiary;
  return (
    <section data-testid="compliance">
      <h2 style={{ marginTop: "1rem" }}>Sanctions screening and beneficiary</h2>
      <p className="muted">Check the supplier against a sanctions list yourself and record what you did. The app keeps the record and the next date; it does not download lists or decide a match.</p>
      {err && <div className="err">{err}</div>}
      <div className="row">
        <b>Screening</b><span className={`tag ${TAG[sc.status]}`}>{WORD[sc.status]}</span>
        {sc.due_on && <span className="muted">next by {sc.due_on} ({sc.basis})</span>}
        {sc.attention && <span className="tag bad">last result needs attention</span>}
      </div>
      {v.history.map((h: any) => (
        <div key={h.id} className="row" style={{ margin: ".2rem 0" }}>
          <span>{h.checked_on}</span><span>{h.list_name}</span><span className={`tag ${h.result === "clear" ? "ok" : "bad"}`}>{h.result_label}</span>
          <span className="muted">{h.checked_by}{h.note ? ` · ${h.note}` : ""}</span>
          <button disabled={!named} onClick={() => confirm("Remove this record?") && run(() => api(`/screenings/${h.id}?removed_by=${encodeURIComponent(person)}`, { method: "DELETE" }))}>remove</button>
        </div>))}
      <div className="row">
        <input type="date" value={s.checked_on} onChange={(e) => setS({ ...s, checked_on: e.target.value })} />
        <input list="screening-lists" placeholder="list checked (name it)" style={{ flex: 2 }} value={s.list_name} onChange={(e) => setS({ ...s, list_name: e.target.value })} />
        <datalist id="screening-lists">{v.list_names.map((n: string) => <option key={n} value={n} />)}</datalist>
        <select value={s.result} onChange={(e) => setS({ ...s, result: e.target.value })}>{Object.entries(v.results).map(([k, l]) => <option key={k} value={k}>{l as string}</option>)}</select>
        <input placeholder={s.result === "clear" ? "note (optional)" : "what was found (required)"} style={{ flex: 2 }} value={s.note} onChange={(e) => setS({ ...s, note: e.target.value })} />
        <button className="primary" disabled={!named || !s.list_name.trim()} onClick={() => run(() => api(`/suppliers/${supplierId}/screenings`, { method: "POST", json: { ...s, checked_by: person } }), () => setS({ ...s, list_name: "", note: "" }))}>Record screening</button>
      </div>
      <div className="row">
        <label>re-check every, months <input type="number" min={1} max={60} style={{ width: "5rem" }} placeholder={`${v.default_months}`} value={sched.period} onChange={(e) => setSched({ ...sched, period: e.target.value })} /></label>
        <label>or on <input type="date" value={sched.next} onChange={(e) => setSched({ ...sched, next: e.target.value })} /></label>
        <button disabled={!named} onClick={() => run(() => api(`/suppliers/${supplierId}/recheck-schedule`, { method: "PUT", json: { changed_by: person, period_months: sched.period ? Number(sched.period) : null, next_check_on: sched.next || null } }))}>Save schedule</button>
        <span className="muted">empty = the default of {v.default_months} months</span>
      </div>

      <div className="row" style={{ marginTop: ".8rem" }}>
        <b>Beneficiary</b>
        {!ben.recorded && <span className="tag bad">not recorded</span>}
        {ben.recorded && <span className={`tag ${TAG[ben.status]}`}>{WORD[ben.status]}</span>}
      </div>
      {ben.recorded && <div className="letter">
        <div>{ben.owners.length ? ben.owners.join(", ") : <span className="muted">no natural person named</span>}</div>
        <div className="muted">Source: {ben.source_label}{ben.note ? ` · ${ben.note}` : ""} · confirmed {ben.confirmed_on} by {ben.confirmed_by} · reconfirm by {ben.due_on}</div>
      </div>}
      {!editB && <button disabled={!named} onClick={() => { setB({ owners: ben.owners.join("\n"), source: ben.source ?? "business_register", confirmed_on: today(), note: ben.note ?? "" }); setEditB(true); }}>{ben.recorded ? "Record again" : "Record the beneficiary"}</button>}
      {editB && <div className="letter">
        <textarea rows={3} style={{ width: "100%" }} placeholder="owners, one name per line (leave empty and explain in the note if no person owns it)" value={b.owners} onChange={(e) => setB({ ...b, owners: e.target.value })} />
        <div className="row">
          <select value={b.source} onChange={(e) => setB({ ...b, source: e.target.value })}>{Object.entries(v.sources).map(([k, l]) => <option key={k} value={k}>source: {l as string}</option>)}</select>
          <input type="date" value={b.confirmed_on} onChange={(e) => setB({ ...b, confirmed_on: e.target.value })} />
          <input placeholder="note (needed for “other” or when no owner is named)" style={{ flex: 2 }} value={b.note} onChange={(e) => setB({ ...b, note: e.target.value })} />
        </div>
        <div className="row"><button className="primary" disabled={!named} onClick={() => run(() => api(`/suppliers/${supplierId}/beneficiary`, { method: "PUT", json: { confirmed_by: person, owners: b.owners.split("\n"), source: b.source, confirmed_on: b.confirmed_on, note: b.note } }), () => setEditB(false))}>Save</button><button onClick={() => setEditB(false)}>Cancel</button></div>
      </div>}
    </section>
  );
}

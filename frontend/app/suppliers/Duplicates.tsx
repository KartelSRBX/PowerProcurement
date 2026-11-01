"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

/** One pair of suppliers that may be the same company, with the reasons and the review buttons. */
function Pair({ p, person, onReview, onOpen }: { p: any; person: string; onReview: (a: number, b: number, verdict: string, note: string) => Promise<void>; onOpen?: (id: number) => void }) {
  const [note, setNote] = useState("");
  const named = person.trim().length > 0;
  const side = (s: any) => (onOpen ? <a href="#" onClick={(e) => { e.preventDefault(); onOpen(s.id); }}>{s.name}</a> : <b>{s.name}</b>);
  return (
    <div className="letter" data-testid="dup-pair">
      <div className="row">
        {side(p.a)} <span className="tag">{p.a.country}</span><span className="muted">{p.a.tax_id ? `tax no. ${p.a.tax_id}` : "no tax no."}</span>
        <b>↔</b>
        {side(p.b)} <span className="tag">{p.b.country}</span><span className="muted">{p.b.tax_id ? `tax no. ${p.b.tax_id}` : "no tax no."}</span>
      </div>
      {p.reasons.map((r: any) => <div key={r.kind}><span className={`tag ${r.kind === "name_similar" ? "" : "warn"}`}>{r.label}</span> <span className="muted">{r.detail}</span></div>)}
      {p.reappeared && <div className="err">A new signal appeared since it was marked “different”.</div>}
      {p.review && <div className="muted">Marked <b>{p.review.verdict === "same" ? "the same company" : "different companies"}</b> by {p.review.reviewed_by} on {fmtDate(p.review.reviewed_at)}: {p.review.note}</div>}
      <div className="row">
        <input placeholder="why (required)" style={{ flex: 1 }} value={note} onChange={(e) => setNote(e.target.value)} />
        <button disabled={!named || note.trim().length < 3} onClick={() => onReview(p.a.id, p.b.id, "different", note).then(() => setNote(""))}>Different companies</button>
        <button disabled={!named || note.trim().length < 3} onClick={() => onReview(p.a.id, p.b.id, "same", note).then(() => setNote(""))}>The same company</button>
      </div>
    </div>
  );
}

/** Suppliers that may be entered twice. Nothing is merged here: a person looks and records a verdict. */
export function DuplicatesList({ person, onOpen }: { person: string; onOpen: (id: number) => void }) {
  const [v, setV] = useState<any>(null);
  const [all, setAll] = useState(false);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { setV(await api<any>(`/suppliers/duplicates?include_reviewed=${all}`)); setErr(""); } catch (e: any) { setErr(e.message); }
  }, [all]);
  useEffect(() => { load(); }, [load]);
  async function review(a: number, b: number, verdict: string, note: string) {
    try { await api("/suppliers/duplicates/review", { method: "POST", json: { supplier_a_id: a, supplier_b_id: b, verdict, note, reviewed_by: person } }); await load(); }
    catch (e: any) { setErr(e.message); }
  }
  if (!v) return <div className="muted">{err || "Looking for duplicates..."}</div>;
  return (
    <section data-testid="duplicates">
      <h2>Possible duplicate suppliers</h2>
      <p className="muted">Pairs with the same tax number, the same bank account, or the same or a very similar name. The app only lists them: look, then mark each pair.
        {v.hidden > 0 && ` ${v.hidden} already marked as different are hidden.`}</p>
      <label><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> show pairs already marked</label>
      {err && <div className="err">{err}</div>}
      {v.pairs.length === 0 && <div className="muted">Nothing to review.</div>}
      {v.pairs.map((p: any) => <Pair key={`${p.a.id}-${p.b.id}`} p={p} person={person} onReview={review} onOpen={onOpen} />)}
    </section>
  );
}

/** The pairs that involve the supplier being looked at, at the top of its profile. */
export function DuplicateWarning({ d, person, onChanged }: { d: any; person: string; onChanged: () => void }) {
  const [err, setErr] = useState("");
  if (!d.possible_duplicates?.length) return null;
  async function review(a: number, b: number, verdict: string, note: string) {
    try { await api("/suppliers/duplicates/review", { method: "POST", json: { supplier_a_id: a, supplier_b_id: b, verdict, note, reviewed_by: person } }); onChanged(); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <div data-testid="dup-warning">
      <div className="err">May be the same company as {d.possible_duplicates.length} other supplier(s). Check before ordering or paying.</div>
      {err && <div className="err">{err}</div>}
      {d.possible_duplicates.map((p: any) => <Pair key={`${p.a.id}-${p.b.id}`} p={p} person={person} onReview={review} />)}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

const group = (a: string | null) => (a ? a.replace(/(.{4})/g, "$1 ").trim() : "-");

/** The line shown where an order is paid: the account in force, and a warning when it is new. */
export function PaysTo({ supplierId }: { supplierId: number }) {
  const [v, setV] = useState<any>(null);
  useEffect(() => { api<any>(`/suppliers/${supplierId}/bank`).then(setV).catch(() => setV(null)); }, [supplierId]);
  if (!v) return null;
  const c = v.current;
  return (
    <div className="row" data-testid="pays-to">
      <b>Pays to</b>
      {!c && <span className="tag warn">no confirmed bank account on file</span>}
      {c && <><span>{c.holder} · {group(c.account)}</span>
        {c.recent && <span className="tag warn">account changed {c.days_in_force} day(s) ago: check it before paying</span>}</>}
      {v.pending && <span className="tag warn">a new account is waiting for a second person</span>}
    </div>
  );
}

/** Bank details of one supplier: set or changed only as a proposal, with a record of the call, approved by another person. */
export function BankPanel({ supplierId, person }: { supplierId: number; person: string }) {
  const named = person.trim().length > 0;
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const empty = { account: "", holder: "", bank_name: "", swift: "", reason: "", callback_person: "", callback_source: "contract", callback_on: new Date().toISOString().slice(0, 10), callback_note: "" };
  const [f, setF] = useState(empty);
  const [comment, setComment] = useState("");

  const load = useCallback(async () => {
    try { setV(await api<any>(`/suppliers/${supplierId}/bank`)); setErr(""); } catch (e: any) { setErr(e.message); }
  }, [supplierId]);
  useEffect(() => { setOpen(false); setF(empty); load(); }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(fn: () => Promise<any>, after?: () => void) {
    setErr("");
    try { setV(await fn()); after?.(); } catch (e: any) { setErr(e.message); }
  }
  const propose = () => run(
    () => api<any>(`/suppliers/${supplierId}/bank/proposals`, { method: "POST", json: { ...f, proposed_by: person, callback_by: person, bank_name: f.bank_name || null, swift: f.swift || null } }),
    () => { setOpen(false); setF(empty); },
  );
  const decide = (id: number, approve: boolean) => run(
    () => api<any>(`/bank-proposals/${id}/decision`, { method: "POST", json: { decided_by: person, approve, comment } }),
    () => setComment(""),
  );
  const withdraw = (id: number) => run(() => api<any>(`/bank-proposals/${id}/withdraw?by=${encodeURIComponent(person)}`, { method: "POST" }));

  if (!v) return <div className="muted">{err || "Loading bank details..."}</div>;
  const c = v.current, p = v.pending;
  return (
    <section data-testid="bank">
      <h2 style={{ marginTop: "1rem" }}>Bank details</h2>
      <p className="muted">A mail saying “our account has changed” is the usual payment fraud. An account is set or changed only as a proposal with a record of the call that confirmed it
        (to a number from the contract or another source you trust, never from that mail), and a different person approves it. Until then the old account stays in force.</p>
      {err && <div className="err">{err}</div>}
      {c ? <div className="letter">
        <div className="row"><b>In force</b><span>{c.holder} · {group(c.account)}{c.bank_name ? ` · ${c.bank_name}` : ""}{c.swift ? ` · ${c.swift}` : ""}</span>
          <span className="tag">{c.kind === "iban" ? "IBAN" : "domestic number"}</span>
          {c.recent && <span className="tag warn">changed {c.days_in_force} day(s) ago</span>}</div>
        <div className="muted">Approved by {c.confirmed_by} on {fmtDate(c.confirmed_at)}</div>
      </div> : <div className="muted">No bank account confirmed yet.</div>}

      {p && <div className="letter" data-testid="bank-pending">
        <div className="row"><b>Waiting for a second person</b><span>{p.holder} · {group(p.account)}{p.bank_name ? ` · ${p.bank_name}` : ""}</span></div>
        <div className="muted">Proposed by {p.proposed_by} ({p.reason}). Call on {p.callback_on} by {p.callback_by} to {p.callback_person}; number from: {p.callback_source_label}{p.callback_note ? ` (${p.callback_note})` : ""}.</div>
        {p.warnings.map((w: string, i: number) => <div key={i} className="err">⚠ {w}</div>)}
        <div className="row">
          <input placeholder="comment (required to reject)" style={{ flex: 1 }} value={comment} onChange={(e) => setComment(e.target.value)} />
          <button className="primary" disabled={!named || person.trim().toLowerCase() === p.proposed_by.trim().toLowerCase()} title="A different person than the one who proposed it" onClick={() => decide(p.id, true)}>Approve</button>
          <button className="danger" disabled={!named} onClick={() => decide(p.id, false)}>Reject</button>
          <button disabled={!named || person.trim().toLowerCase() !== p.proposed_by.trim().toLowerCase()} onClick={() => withdraw(p.id)}>Withdraw</button>
        </div>
      </div>}

      {!p && !open && <button disabled={!named} onClick={() => setOpen(true)}>{c ? "Propose a new account" : "Propose an account"}</button>}
      {!p && open && <div className="letter">
        <div className="row">
          <input placeholder="IBAN or account number" style={{ flex: 2 }} value={f.account} onChange={(e) => setF({ ...f, account: e.target.value })} />
          <input placeholder="account holder (beneficiary)" style={{ flex: 2 }} value={f.holder} onChange={(e) => setF({ ...f, holder: e.target.value })} />
        </div>
        <div className="row">
          <input placeholder="bank (optional)" style={{ flex: 2 }} value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} />
          <input placeholder="SWIFT/BIC (optional)" value={f.swift} onChange={(e) => setF({ ...f, swift: e.target.value })} />
          <input placeholder="why is it set or changed" style={{ flex: 2 }} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
        </div>
        <div className="muted">The call that confirmed it (you are recorded as the caller):</div>
        <div className="row">
          <input placeholder="who at the supplier confirmed" style={{ flex: 2 }} value={f.callback_person} onChange={(e) => setF({ ...f, callback_person: e.target.value })} />
          <select value={f.callback_source} onChange={(e) => setF({ ...f, callback_source: e.target.value })}>
            {Object.entries(v.callback_sources).map(([k, label]) => <option key={k} value={k}>number from: {label as string}</option>)}
          </select>
          <input type="date" value={f.callback_on} onChange={(e) => setF({ ...f, callback_on: e.target.value })} />
          <input placeholder={f.callback_source === "other" ? "where the number came from (required)" : "note (optional)"} style={{ flex: 2 }} value={f.callback_note} onChange={(e) => setF({ ...f, callback_note: e.target.value })} />
        </div>
        <div className="row"><button className="primary" disabled={!named} onClick={propose}>Send for a second person</button><button onClick={() => setOpen(false)}>Cancel</button></div>
      </div>}

      {v.history.length > 0 && <table><thead><tr><th>Proposed</th><th>Account</th><th>By</th><th>Decision</th><th>Decided by</th><th>Comment</th></tr></thead><tbody>
        {v.history.map((h: any) => <tr key={h.id}><td>{fmtDate(h.proposed_at)}</td><td>{group(h.account)}</td><td>{h.proposed_by}</td>
          <td><span className={`tag ${h.status === "approved" ? "ok" : "warn"}`}>{h.status}</span></td><td>{h.decided_by ?? "-"}</td><td className="muted">{h.decision_comment ?? ""}</td></tr>)}
      </tbody></table>}
    </section>
  );
}

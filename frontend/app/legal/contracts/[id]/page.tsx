"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { Cite, ROLE_LABEL, Sev, STATE_LABEL } from "../../../lib/legal";
import { usePerson } from "../../../lib/person";

const OPEN = ["open", "to_lawyer"];

export default function ContractPage() {
  const id = useParams<{ id: string }>().id;
  const router = useRouter();
  const { person } = usePerson();
  const named = person.trim().length > 1;
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [show, setShow] = useState("open");
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api(`/legal/contracts/${id}`).then(setC).catch((e) => setErr(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (c?.ai_allowed) api(`/legal/contracts/${id}/ai-preview`).then(setPreview).catch(() => setPreview(null)); else setPreview(null); }, [c?.ai_allowed, id]);

  const act = async (fn: () => Promise<void>) => {
    setErr(""); setNote(null); setBusy(true);
    try { await fn(); await load(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const decide = (fid: number, state: string) => act(async () => {
    await api(`/legal/findings/${fid}/decision`, { method: "POST", json: { state, note: notes[fid] ?? "", by: person } });
  });
  const reanalyse = () => act(async () => { await api(`/legal/contracts/${id}/analyse`, { method: "POST", json: { by: person } }); setNote({ ok: true, text: "Checked again. Remarks you already decided on were kept." }); });
  const askAi = () => act(async () => {
    const r = await api<any>(`/legal/contracts/${id}/ai-review`, { method: "POST", json: { by: person } });
    setNote({ ok: true, text: `The AI added ${r.added} remark${r.added === 1 ? "" : "s"}${r.dropped ? `; ${r.dropped} dropped because the quoted words were not found in the contract` : ""}.${r.note ? " " + r.note : ""}` });
  });
  const toggleAi = (v: boolean) => act(async () => { await api(`/legal/contracts/${id}`, { method: "PATCH", json: { by: person, values: { ai_allowed: v } } }); });
  const remove = async () => {
    if (!confirm("Delete this contract and all its remarks?")) return;
    try { await api(`/legal/contracts/${id}?by=${encodeURIComponent(person)}`, { method: "DELETE" }); router.push("/legal"); } catch (e: any) { setErr(e.message); }
  };

  if (!c) return <p>{err || "Loading..."}</p>;
  const f: any[] = c.findings;
  const shown = f.filter((x) => (show === "open" ? OPEN.includes(x.state) : show === "all" ? true : x.state === show));
  const s = c.summary;
  const flagged = new Set<number>(c.clauses.filter((cl: any) => cl.findings.length).map((cl: any) => cl.id));
  const facts: [string, string][] = [
    ["Our side", ROLE_LABEL[c.role]],
    ["Payment", s.payment_days != null ? `${s.payment_days} days` : "not found"],
    ["Governing law", s.law ?? "not found"],
    ["Disputes", s.forum ?? "not found"],
    ["Incoterms", s.incoterms.length ? s.incoterms.join(", ") : "none"],
    ["Warranty", s.warranty_months != null ? `${s.warranty_months} months` : "not found"],
    ["Renewal", s.auto_renewal ? "automatic" : "no automatic renewal found"],
    ["Vienna Convention (CISG)", s.cisg_excluded ? "excluded" : "not excluded"],
  ];

  return (
    <>
      <p><Link href="/legal">← All contracts</Link></p>
      <h1>{c.title} <span className="tag">{c.counterparty || "no other party"}</span> {c.request_id && <Link className="tag" href={`/requests/${c.request_id}`}>request {c.request_id}</Link>}</h1>
      {err && <div className="err">{err}</div>}
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
      {!named && <div className="muted">Enter your name at the top: every decision is recorded with it.</div>}

      <div className="kpis">
        <div className="kpi"><div className="v" style={{ color: c.counts.red ? "var(--bad)" : undefined }}>{c.counts.red}</div><div className="l">Open risks</div></div>
        <div className="kpi"><div className="v">{c.counts.yellow}</div><div className="l">Open checks</div></div>
        <div className="kpi"><div className="v">{c.counts.info}</div><div className="l">Open notes</div></div>
        <div className="kpi"><div className="v">{c.score}</div><div className="l">Score (lower is better)</div></div>
      </div>

      <section><h2>Key terms found</h2>
        <div className="facts">{facts.map(([l, v]) => <div className="fact" key={l}><div className="l">{l}</div>{v}</div>)}</div>
        <div className="row">
          <button onClick={reanalyse} disabled={!named || busy}>Check again</button>
          <a href={`/api/legal/contracts/${id}/report.md`}><button>Report (Markdown)</button></a>
          <a href={`/api/legal/contracts/${id}/report.xlsx`}><button>Report (Excel)</button></a>
          <button className="danger" onClick={remove} disabled={!named}>Delete</button>
        </div>
      </section>

      <section><h2>Remarks</h2>
        <div className="row">
          {[["open", "Open"], ["accepted", "Accepted"], ["dismissed", "Dismissed"], ["to_lawyer", "With the lawyer"], ["all", "All"]].map(([k, l]) =>
            <button key={k} className={show === k ? "primary" : ""} onClick={() => setShow(k)}>{l} ({k === "all" ? f.length : f.filter((x) => x.state === k).length})</button>)}
        </div>
        {shown.length === 0 && <p className="muted">{f.length === 0 ? "No remarks: the playbook found nothing to flag in this contract." : "Nothing in this view."}</p>}
        {shown.map((x) => <div key={x.id} className={`finding ${x.severity} ${OPEN.includes(x.state) ? "" : "done"}`}>
          <h3><Sev s={x.severity} />{x.title}{x.by === "ai" && <span className="tag acc">AI</span>}<span className="tag">{STATE_LABEL[x.state]}</span></h3>
          {x.quote && <div className="quote">“{x.quote}”</div>}
          <div><b>Why it matters:</b> {x.risk}</div>
          <div className="ask"><b>Ask for:</b> {x.suggest}</div>
          <div>{x.citations.map((ct: any, i: number) => <Cite key={i} c={ct} />)}</div>
          {x.decided_by && <div className="muted">{STATE_LABEL[x.state]} by {x.decided_by}{x.note ? `: ${x.note}` : ""}</div>}
          <div className="row">
            <input style={{ flex: 1, minWidth: "12rem" }} placeholder="note (optional)" value={notes[x.id] ?? ""} onChange={(e) => setNotes({ ...notes, [x.id]: e.target.value })} />
            {x.state !== "accepted" && <button disabled={!named || busy} onClick={() => decide(x.id, "accepted")}>Accept the risk</button>}
            {x.state !== "dismissed" && <button disabled={!named || busy} onClick={() => decide(x.id, "dismissed")}>Not an issue</button>}
            {x.state !== "to_lawyer" && <button disabled={!named || busy} onClick={() => decide(x.id, "to_lawyer")}>Send to lawyer</button>}
            {x.state !== "open" && <button disabled={!named || busy} onClick={() => decide(x.id, "open")}>Reopen</button>}
          </div>
        </div>)}
      </section>

      <section><h2>AI reading</h2>
        <label className="row"><input type="checkbox" checked={c.ai_allowed} disabled={!named || busy} onChange={(e) => toggleAi(e.target.checked)} />Allow the AI to read this contract</label>
        {c.ai_allowed && preview && (preview.enabled
          ? <div className="row"><button className="primary" disabled={!named || busy} onClick={askAi}>Ask the AI</button>
            <span className="muted">Sends about {preview.chars_sent.toLocaleString("en")} characters (~{preview.approx_tokens.toLocaleString("en")} tokens) to the AI provider{preview.cut ? "; the rest of a long contract is cut off" : ""}. The AI only adds remarks; every quote it gives is checked against the contract text, and wrong ones are dropped.</span></div>
          : <p className="muted">AI is not set up (no Anthropic key in Settings), so this stays off.</p>)}
        {!c.ai_allowed && <p className="muted">Off. The contract text never leaves this server unless you allow it here and press the button.</p>}
      </section>

      <section><h2>Contract text · {c.clauses.length} clauses</h2>
        {c.clauses.map((cl: any) => <div key={cl.id} className={`clause ${flagged.has(cl.id) ? "hit" : ""}`}>
          <div className="head">{cl.heading || `Clause ${cl.position}`}{cl.clause_type && cl.clause_type !== "other" && <span className="tag">{cl.clause_type.replace(/_/g, " ")}</span>}
            {flagged.has(cl.id) && <span className="sev yellow">{cl.findings.length} remark{cl.findings.length === 1 ? "" : "s"}</span>}</div>
          <div className="body-text">{cl.text}</div>
        </div>)}
      </section>
    </>
  );
}

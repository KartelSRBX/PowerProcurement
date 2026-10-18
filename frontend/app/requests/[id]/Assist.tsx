"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "../../lib/api";
import { AiOff, aiTag } from "../../lib/ai";

type Ctx = { id: string; who: string; ai: boolean | null; d: any; act: (fn: () => Promise<unknown>) => Promise<void>; post: (p: string, j?: unknown) => Promise<any> };

/** Step 5: paste a supplier's answer, check what was read, save it as an offer. */
export function ReplyPanel({ id, who, ai, d, act, post }: Ctx) {
  const asked: any[] = d.rfqs.filter((r: any) => r.status === "sent");
  const [sid, setSid] = useState<number | "">("");
  const [text, setText] = useState("");
  const [rep, setRep] = useState<any>(null);
  const [form, setForm] = useState({ total_price: "", currency: "EUR", lead_time_days: "", covers_all_items: true, moq_ok: true });
  const [msg, setMsg] = useState("");

  async function read() {
    setMsg("");
    await act(async () => {
      const r = await post(`/requests/${id}/replies`, { supplier_id: Number(sid), text, entered_by: who });
      const p = r.proposal ?? {};
      setRep(r);
      setForm({ total_price: p.total_price ?? "", currency: p.currency ?? "EUR", lead_time_days: p.lead_time_days ?? "", covers_all_items: p.covers_all_items ?? true, moq_ok: p.moq_ok ?? true });
      setMsg(r.ai.used ? `Read by ${r.read_by}. Check every number against the supplier's text before saving.` : r.ai.note ?? "Type the numbers yourself.");
    });
  }
  async function save() {
    await act(async () => {
      await post(`/replies/${rep.id}/confirm`, { confirmed_by: who, total_price: Number(form.total_price), currency: form.currency, lead_time_days: Number(form.lead_time_days), covers_all_items: form.covers_all_items, moq_ok: form.moq_ok });
      setRep(null); setText(""); setMsg("Saved as an offer."); 
    });
  }
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });

  return (
    <div className="letter">
      <div className="row"><b>Enter a supplier's answer</b>{ai === false && <AiOff what="you type the numbers yourself." />}</div>
      {asked.length === 0 ? <p className="muted">Available after at least one letter to a supplier has been approved and sent.</p> : <>
        <div className="row"><select value={sid} onChange={(e) => { setSid(e.target.value ? Number(e.target.value) : ""); setRep(null); }}>
          <option value="">Which supplier answered?</option>
          {asked.map((r: any) => <option key={r.supplier_id} value={r.supplier_id}>{r.supplier}</option>)}</select></div>
        <textarea placeholder="Paste the supplier's email here" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row"><button className="primary" disabled={!who || !sid || !text.trim()} onClick={read}>{ai ? "Read with AI" : "Continue"}</button>
          {!who && <span className="muted">Enter your name at the top first.</span>}</div>
      </>}
      {msg && <p className="muted">{msg}</p>}
      {rep && <>
        {rep.warnings?.map((w: string) => <div key={w} className="err">{w}</div>)}
        {rep.problems?.map((w: string) => <div key={w} className="warn-note">{w}</div>)}
        {rep.missing?.length > 0 && <p className="muted">Still missing from the answer: {rep.missing.join("; ")}. The follow-up section below can ask for it.</p>}
        <div className="row">
          <label>Total price <input type="number" style={{ width: "8rem" }} value={form.total_price} onChange={(e) => set("total_price", e.target.value)} /></label>
          <select value={form.currency} onChange={(e) => set("currency", e.target.value)}><option>EUR</option><option>RSD</option><option>USD</option></select>
          <label>Lead time, days <input type="number" style={{ width: "5rem" }} value={form.lead_time_days} onChange={(e) => set("lead_time_days", e.target.value)} /></label>
          <label><input type="checkbox" checked={form.covers_all_items} onChange={(e) => set("covers_all_items", e.target.checked)} /> covers all items</label>
          <label><input type="checkbox" checked={form.moq_ok} onChange={(e) => set("moq_ok", e.target.checked)} /> minimum order fits</label>
        </div>
        {(rep.payment_terms || rep.warranty || rep.valid_until) && <p className="muted">{[rep.payment_terms && `terms: ${rep.payment_terms}`, rep.warranty && `warranty: ${rep.warranty}`, rep.valid_until && `valid until ${rep.valid_until}`].filter(Boolean).join(" · ")}</p>}
        <div className="row"><button className="primary" disabled={!form.total_price || !form.lead_time_days} onClick={save}>Save as offer</button>
          <span className="muted">Nothing counts as an offer until you save it.</span></div>
      </>}
    </div>
  );
}

/** Plain-language reading of the ranking table; the numbers stay the ones code computed. */
export function ExplainScores({ id, ai, w, disabled }: { id: string; ai: boolean | null; w: unknown; disabled: boolean }) {
  const [out, setOut] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function run() {
    setErr(""); setBusy(true);
    try { setOut(await api(`/requests/${id}/score/explain`, { method: "POST", json: w })); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }
  return <>
    <div className="row"><button disabled={disabled || !ai || busy} onClick={run}>{busy ? "Reading..." : "Explain in words"}</button>
      {ai === false && <AiOff what="the table above is still complete." />}</div>
    {err && <div className="err">{err}</div>}
    {out && <div className="letter"><p>{out.summary}</p>
      {out.ranked.filter((r: any) => out.suppliers[r.offer_id]).map((r: any) => <p key={r.offer_id} className="muted"><b>{r.supplier}:</b> {out.suppliers[r.offer_id]}</p>)}
      <p className="muted">Written by {out.model} from the numbers in the table. It does not change the ranking.</p></div>}
  </>;
}

/** Step 6: who needs a follow-up letter, and the drafts waiting for approval. */
export function Followups({ id, who, ai, d, act, post }: Ctx) {
  const [cands, setCands] = useState<any[] | null>(null);
  const [days, setDays] = useState("");
  const letters: any[] = d.letters.filter((l: any) => l.kind === "followup");
  const label = (k: string) => (k === "unanswered" ? "no answer yet" : "answer incomplete");
  return (
    <section><h2>Follow-ups to suppliers (letters wait for your approval)</h2>
      <p className="muted">Code decides who is late or incomplete (no answer after the set number of days, or an answer with gaps). {ai ? "AI writes the wording." : <AiOff what="the letters use the plain template." />}</p>
      <div className="row">
        <label>Silent for at least <input type="number" min={0} style={{ width: "4rem" }} placeholder="3" value={days} onChange={(e) => setDays(e.target.value)} /> day(s)</label>
        <button onClick={() => api<any[]>(`/requests/${id}/followups${days !== "" ? `?silent_days=${Number(days)}` : ""}`).then(setCands).catch(() => setCands([]))}>Who needs a follow-up?</button>
        <button className="primary" onClick={() => act(async () => { await post(`/requests/${id}/followups`, days !== "" ? { silent_days: Number(days) } : {}); setCands(null); })}>Draft follow-ups</button>
        <Link href="/approvals">Open the approval queue</Link>
      </div>
      {cands && (cands.length === 0 ? <p className="muted">Nobody needs a follow-up right now.</p>
        : <table><tbody>{cands.map((c) => <tr key={c.supplier_id}><td>{c.supplier}</td><td><span className="tag">{label(c.kind)}</span></td><td className="muted">{c.needs.join("; ")}</td></tr>)}</tbody></table>)}
      {letters.map((l) => <div className="letter" key={l.id}>
        <div className="row"><b>{l.supplier}</b><span className="tag">{l.status}</span>{aiTag(l.drafted_by)}<span className="muted">{l.reason}</span></div>
        <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>{l.body}</pre>
        {l.status === "draft" && <span className="muted">Waiting in the approval queue{who ? "" : ". Enter your name at the top to decide"}.</span>}
      </div>)}
    </section>
  );
}

/** Step 7: read the customer's answer into a proposed outcome, or draft a reminder. */
export function CustomerReply({ quote, who, ai, d, act, post }: Ctx & { quote: any }) {
  const [text, setText] = useState("");
  const [read, setRead] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const reminders: any[] = d.letters.filter((l: any) => l.kind === "reminder");
  const answered = d.outcomes.length > 0;
  const KIND: Record<string, string> = { accepted: "accepted", counter: "counter-offer", rejected: "rejected", silence: "no answer", unclear: "unclear" };
  return (
    <div className="letter">
      <div className="row"><b>Customer answer, read by AI</b>{ai === false && <AiOff what="use the buttons above." />}</div>
      <textarea placeholder="Paste the customer's reply here" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="row"><button disabled={!ai || !text.trim()} onClick={() => act(async () => { setMsg(""); setRead(await post(`/quotes/${quote.id}/customer-reply/read`, { text })); })}>Read with AI</button>
        <button disabled={!ai || answered} onClick={() => act(async () => { await post(`/quotes/${quote.id}/reminder`); setMsg("Reminder drafted. It waits in the approval queue."); })}>Draft a reminder</button>
        {msg && <span className="muted">{msg}</span>}</div>
      {read && <div className="row"><span>AI reads it as <b>{KIND[read.kind]}</b>{read.price ? ` at ${read.price} ${read.currency}` : ""}{read.reason ? ` (${read.reason})` : ""}.</span>
        {read.kind !== "unclear" && <button className="primary" disabled={!who} onClick={() => act(async () => { await post(`/quotes/${quote.id}/outcome`, { kind: read.kind, ...(read.kind === "counter" ? { price: read.price } : {}), confirmed_by: who }); setRead(null); setText(""); })}>Record this answer</button>}
        <span className="muted">Nothing is recorded until you press the button.</span></div>}
      {reminders.map((l) => <div key={l.id} className="muted">Reminder: {l.status}{aiTag(l.drafted_by)}</div>)}
    </div>
  );
}

/** Step 7: see and edit the invoice request before it goes to the supplier. */
export function InvoiceRequest({ po, who, act, post }: { po: any; who: string; act: (fn: () => Promise<unknown>) => Promise<void>; post: (p: string, j?: unknown) => Promise<any> }) {
  const [draft, setDraft] = useState<any>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  async function open() {
    await act(async () => { const x = await api<any>(`/orders/${po.id}/invoice-draft`); setDraft(x); setSubject(x.subject); setBody(x.body); });
  }
  if (!draft) return <button disabled={!who} onClick={open}>Prepare invoice request</button>;
  return <div>
    <div className="row"><span className="muted">To: {draft.to}</span>{aiTag(draft.drafted_by)}</div>
    <input style={{ width: "100%" }} value={subject} onChange={(e) => setSubject(e.target.value)} />
    <textarea value={body} onChange={(e) => setBody(e.target.value)} />
    <div className="row"><button className="primary" disabled={!who} onClick={() => act(async () => { await post(`/orders/${po.id}/invoice-request`, { approved_by: who, subject, body }); setDraft(null); })}>Approve and send to supplier (Mailpit)</button>
      <button onClick={() => setDraft(null)}>Cancel</button></div>
  </div>;
}


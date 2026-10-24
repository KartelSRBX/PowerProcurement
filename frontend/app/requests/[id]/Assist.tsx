"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, eur } from "../../lib/api";
import { AiOff, aiTag } from "../../lib/ai";

type Ctx = { id: string; who: string; ai: boolean | null; d: any; act: (fn: () => Promise<unknown>) => Promise<void>; post: (p: string, j?: unknown) => Promise<any> };

/** Step 5: paste a supplier's answer, check what was read, save it as an offer. */
export function ReplyPanel({ id, who, ai, d, act, post }: Ctx) {
  const asked: any[] = d.rfqs.filter((r: any) => r.status === "sent");
  const [sid, setSid] = useState<number | "">("");
  const [text, setText] = useState("");
  const [rep, setRep] = useState<any>(null);
  const [form, setForm] = useState({ total_price: "", currency: "EUR", lead_time_days: "", covers_all_items: true, moq_ok: true, valid_until: "", incoterm: "", incoterm_place: "", payment_days: "" });
  const [lines, setLines] = useState<Record<number, { unit_price: string; moq: string }>>({});
  const [msg, setMsg] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const toBase64 = (f: File) => new Promise<string>((ok, no) => {
    const fr = new FileReader();
    fr.onload = () => ok(String(fr.result).split(",")[1] ?? "");
    fr.onerror = () => no(new Error("the file could not be read in the browser"));
    fr.readAsDataURL(f);
  });
  function show(r: any, note?: string) {
    const p = r.proposal ?? r.extracted?.proposal ?? {};
    setRep(r);
    setForm({ total_price: p.total_price ?? "", currency: p.currency ?? "EUR", lead_time_days: p.lead_time_days ?? "", covers_all_items: p.covers_all_items ?? true, moq_ok: p.moq_ok ?? true, valid_until: /^\d{4}-\d{2}-\d{2}$/.test(r.valid_until ?? "") ? r.valid_until : "", incoterm: "", incoterm_place: "", payment_days: "" });
    setLines({});
    setMsg(note ?? (r.ai?.used ? `Read by ${r.read_by}. Check every number against the supplier's text before saving.` : r.ai?.note ?? "Type the numbers yourself."));
  }
  async function read() {
    setMsg("");
    await act(async () => {
      const r = file
        ? await post(`/requests/${id}/replies/file`, { supplier_id: Number(sid), filename: file.name, content_base64: await toBase64(file), entered_by: who })
        : await post(`/requests/${id}/replies`, { supplier_id: Number(sid), text, entered_by: who });
      show(r);
    });
  }
  const [mail, setMail] = useState<any[]>([]);
  useEffect(() => { api<any[]>(`/requests/${id}/mail`).then(setMail).catch(() => setMail([])); }, [id, d, rep]);
  const waiting = mail.filter((m) => m.waiting);
  const unsaved = mail.filter((m) => !m.waiting && m.reply?.status === "extracted");
  async function readMail(m: any) {
    setMsg("");
    await act(async () => { show(await post(`/mail/${m.id}/read`, { entered_by: who })); });
  }
  const items: any[] = d.items ?? [];
  const priced = Object.entries(lines).filter(([, l]) => l.unit_price !== "");
  const setLine = (id: number, k: "unit_price" | "moq", v: string) => setLines({ ...lines, [id]: { ...(lines[id] ?? { unit_price: "", moq: "" }), [k]: v } });
  const linesSum = priced.reduce((t, [id, l]) => t + Number(l.unit_price) * (items.find((i) => i.id === Number(id))?.quantity ?? 0), 0);
  async function save() {
    await act(async () => {
      await post(`/replies/${rep.id}/confirm`, { confirmed_by: who, total_price: Number(form.total_price), currency: form.currency, lead_time_days: Number(form.lead_time_days), covers_all_items: form.covers_all_items, moq_ok: form.moq_ok,
        valid_until: form.valid_until || null, incoterm: form.incoterm || null, incoterm_place: form.incoterm_place.trim() || null, payment_days: form.payment_days === "" ? null : Number(form.payment_days),
        lines: priced.length ? priced.map(([id, l]) => ({ item_id: Number(id), unit_price: Number(l.unit_price), moq: l.moq === "" ? null : Number(l.moq) })) : null });
      setRep(null); setText(""); setFile(null); setMsg("Saved as an offer.");
    });
  }
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });

  return (
    <div className="letter">
      {mail.length > 0 && <div className="letter">
        <div className="row"><b>Waiting to be read ({waiting.length})</b><span className="muted">Mail from suppliers that the inbox filed under this request. Attachments are not kept: upload an attached file in the form below.</span></div>
        {[...waiting, ...unsaved].map((m) => <div key={m.id} className="row">
          <span><b>{m.supplier}</b> · {m.subject}<div className="muted">{m.body.slice(0, 140)}{m.body.length > 140 ? "…" : ""} · {m.how_matched}</div></span>
          {m.waiting
            ? <button className="primary" disabled={!who} onClick={() => readMail(m)}>{ai ? "Read with AI" : "Read"}</button>
            : <button disabled={!who} onClick={() => show(m.reply, "Opened the earlier reading of this mail. Check every number against the supplier's text before saving.")}>Open the reading</button>}
        </div>)}
        {!who && <span className="muted">Enter your name at the top first.</span>}
      </div>}
      <div className="row"><b>Enter a supplier's answer</b>{ai === false && <AiOff what="you type the numbers yourself." />}</div>
      {asked.length === 0 ? <p className="muted">Available after at least one letter to a supplier has been approved and sent.</p> : <>
        <div className="row"><select value={sid} onChange={(e) => { setSid(e.target.value ? Number(e.target.value) : ""); setRep(null); }}>
          <option value="">Which supplier answered?</option>
          {asked.map((r: any) => <option key={r.supplier_id} value={r.supplier_id}>{r.supplier}</option>)}</select></div>
        <textarea placeholder="Paste the supplier's email here" value={text} onChange={(e) => { setText(e.target.value); setFile(null); }} disabled={!!file} />
        <div className="row"><label>or a file (PDF, Excel .xlsx, CSV, text) <input type="file" accept=".pdf,.xlsx,.xlsm,.csv,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          {file && <button onClick={() => setFile(null)}>Remove {file.name}</button>}</div>
        <div className="row"><button className="primary" disabled={!who || !sid || (!file && !text.trim())} onClick={read}>{ai ? "Read with AI" : "Continue"}</button>
          {!who && <span className="muted">Enter your name at the top first.</span>}</div>
      </>}
      {msg && <p className="muted">{msg}</p>}
      {rep && <>
        {rep.text?.startsWith("[File:") && <details><summary className="muted">Text read from the file (check it against the file)</summary><pre className="muted" style={{ whiteSpace: "pre-wrap", maxHeight: "14rem", overflow: "auto" }}>{rep.text}</pre></details>}
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
        <div className="row">
          <label>Price valid until <input type="date" value={form.valid_until} onChange={(e) => set("valid_until", e.target.value)} /></label>
          <label>Incoterms <select value={form.incoterm} onChange={(e) => set("incoterm", e.target.value)}><option value="">not stated</option>
            {["EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"].map((c) => <option key={c}>{c}</option>)}</select></label>
          <label>Named place <input style={{ width: "10rem" }} placeholder="e.g. Belgrade" value={form.incoterm_place} onChange={(e) => set("incoterm_place", e.target.value)} /></label>
          <label>Payment, days <input type="number" min={0} max={365} style={{ width: "5rem" }} value={form.payment_days} onChange={(e) => set("payment_days", e.target.value)} /></label>
        </div>
        <details><summary className="muted">Price per item (optional, lets you compare offers item by item)</summary>
          <table><thead><tr><th>Item</th><th>Qty</th><th>Unit price</th><th>Minimum order</th></tr></thead><tbody>
            {items.map((i) => <tr key={i.id}><td>{i.description}</td><td>{i.quantity} {i.unit}</td>
              <td><input type="number" min={0} style={{ width: "7rem" }} value={lines[i.id]?.unit_price ?? ""} onChange={(e) => setLine(i.id, "unit_price", e.target.value)} /></td>
              <td><input type="number" min={0} style={{ width: "6rem" }} value={lines[i.id]?.moq ?? ""} onChange={(e) => setLine(i.id, "moq", e.target.value)} /></td></tr>)}</tbody></table>
          {priced.length > 0 && <p className="muted">Sum of the lines: {linesSum.toFixed(2)} {form.currency}.{priced.length < items.length ? " Items without a price make this offer incomplete." : ""}{Math.abs(linesSum - Number(form.total_price)) > 0.01 * linesSum ? " It differs from the total above." : ""}
            {" "}<button onClick={() => set("total_price", linesSum.toFixed(2))}>Use as total</button></p>}
        </details>
        {(rep.payment_terms || rep.warranty || rep.valid_until) && <p className="muted">{[rep.payment_terms && `terms: ${rep.payment_terms}`, rep.warranty && `warranty: ${rep.warranty}`, rep.valid_until && `valid until ${rep.valid_until}`].filter(Boolean).join(" · ")}</p>}
        <div className="row"><button className="primary" disabled={!form.total_price || !form.lead_time_days} onClick={save}>Save as offer</button>
          <span className="muted">Nothing counts as an offer until you save it.</span></div>
      </>}
    </div>
  );
}

/** Offers side by side, item by item. Code does the arithmetic; an offer that cannot be set against the others says why. */
export function Comparison({ id, offers }: { id: string; offers: number }) {
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  async function run() {
    setErr("");
    try { setC(await api(`/requests/${id}/comparison`)); } catch (e: any) { setErr(e.message); }
  }
  return <>
    <div className="row"><button disabled={offers === 0} onClick={run}>Compare item by item</button>
      {c && <a href={`/api/requests/${id}/comparison.xlsx`}><button>Excel</button></a>}</div>
    {err && <div className="err">{err}</div>}
    {c && <>
      <table><thead><tr><th>Item</th>{c.offers.map((o: any) => <th key={o.offer_id}>{o.supplier}{o.currency !== "EUR" && <div className="muted">{o.currency} → EUR</div>}</th>)}</tr></thead><tbody>
        {c.items.map((i: any) => <tr key={i.id}><td>{i.description} <span className="muted">× {i.quantity} {i.unit}</span></td>
          {c.offers.map((o: any) => { const x = c.cells[o.offer_id]?.[i.id];
            return <td key={o.offer_id} style={x?.best ? { fontWeight: 600, color: "var(--good, green)" } : undefined}>{x ? <>{eur(x.unit_price_eur)}{x.best && " ✓"}{x.moq != null && <div className="muted">min {x.moq}</div>}</> : <span className="muted">no price</span>}</td>; })}</tr>)}
        <tr><td><b>Total, EUR</b></td>{c.offers.map((o: any) => <td key={o.offer_id}><b>{eur(o.total_eur)}</b></td>)}</tr>
        <tr><td>Terms</td>{c.offers.map((o: any) => <td key={o.offer_id} className="muted">{[o.incoterm && `${o.incoterm}${o.incoterm_place ? " " + o.incoterm_place : ""}`, o.payment_days != null && `pay in ${o.payment_days} d`, `${o.lead_time_days} d lead`].filter(Boolean).join(" · ")}</td>)}</tr>
        <tr><td>Can be compared?</td>{c.offers.map((o: any) => <td key={o.offer_id}>{o.comparable ? "yes" : <span className="err">no</span>}
          {[...o.not_comparable, ...o.notes].map((n: string) => <div key={n} className="muted">{n}</div>)}</td>)}</tr>
      </tbody></table>
      <p className="muted">Unit prices are in EUR at the demo rates in Settings. The ✓ marks the lowest price among offers that can be compared; offers that cannot are never marked.</p>
    </>}
  </>;
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
        {read.kind !== "unclear" && <button className="primary" disabled={!who} onClick={() => act(async () => { await post(`/quotes/${quote.id}/outcome`, { kind: read.kind, ...(read.kind === "counter" ? { price: read.price, currency: read.currency } : {}), confirmed_by: who }); setRead(null); setText(""); })}>Record this answer</button>}
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


/** After the purchase order: a confirmation to the customer and a delivery question to the supplier. */
export function OrderLetters({ po, who, ai, d, act, post }: Ctx & { po: any }) {
  const mine: any[] = d.letters.filter((l: any) => l.order_id === po.id);
  const label = (k: string) => (k === "confirmation" ? "order confirmation to the customer" : "delivery question to the supplier");
  return (
    <div>
      <div className="row">
        <button onClick={() => act(() => post(`/orders/${po.id}/customer-confirmation`))}>Draft order confirmation to the customer</button>
        <button onClick={() => act(() => post(`/orders/${po.id}/delivery-question`))}>Ask the supplier about delivery</button>
        {ai === false && <AiOff what="the letters use plain templates." />}
      </div>
      {mine.map((l) => <div className="row" key={l.id}><span className="tag">{label(l.kind)}</span><span className="tag">{l.status}</span>{aiTag(l.drafted_by)}
        {l.status === "draft" && <Link href="/approvals">waiting in the approval queue</Link>}</div>)}
    </div>
  );
}

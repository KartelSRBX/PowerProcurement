"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, eur } from "../../lib/api";
import { usePerson } from "../../lib/person";
import { AiOff, aiTag, useAi } from "../../lib/ai";
import { TasksPanel } from "./Tasks";
import { LegalPanel } from "./LegalPanel";
import { Comparison, CustomerReply, ExplainScores, Followups, InvoiceRequest, OrderLetters, ReplyPanel } from "./Assist";

export default function RequestPage() {
  const id = useParams<{ id: string }>().id;
  const { person: name } = usePerson();
  const [err, setErr] = useState("");
  const [d, setD] = useState<any>({});
  const [w, setW] = useState({ price: 30, lead_time: 20, reliability: 20, terms: 15, external_risk: 15 });
  const [ranked, setRanked] = useState<any[]>([]);
  const [markup, setMarkup] = useState(15);
  const [cur, setCur] = useState("EUR");
  const ai = useAi();

  const refresh = useCallback(async () => {
    const [pipeline, items, shortlist, rfqs, offers, quotes, orders, events, outcomes, letters] = await Promise.all(
      ["pipeline", "items", "shortlist", "rfqs", "offers", "quotes", "orders", "price-events", "outcomes", "letters"].map((p) => api(`/requests/${id}/${p}`)),
    );
    setD({ pipeline, items, shortlist, rfqs, offers, quotes, orders, events, outcomes, letters });
  }, [id]);

  useEffect(() => { refresh().catch((e) => setErr(e.message)); }, [refresh]);

  const busy = useRef(false);  // a double click must not send or record twice
  async function act(fn: () => Promise<unknown>) {
    if (busy.current) return;
    busy.current = true;
    setErr("");
    try { await fn(); await refresh(); } catch (e: any) { setErr(e.message); } finally { busy.current = false; }
  }
  const post = (path: string, json: unknown = {}) => api(path, { method: "POST", json });
  const who = name.trim();
  const ctx = { id, who, ai, d, act, post };

  if (!d.pipeline) return <p>{err || "Loading..."}</p>;
  const lastQuote = d.quotes.at(-1);
  const sentQuote = [...d.quotes].reverse().find((q: any) => q.status === "sent");

  return (
    <>
      <h1>Request #{id} <span className="tag">{d.pipeline.stage}</span></h1>
      <p className="muted">Next: {d.pipeline.next}</p>
            {err && <div className="err">{err}</div>}

      <section><h2>Items</h2>
        <table><tbody>{d.items.map((i: any) => <tr key={i.id}><td>{i.quantity ?? "?"} ×</td><td>{i.description}</td></tr>)}</tbody></table>
      </section>

      <section><h2>Steps 2-3 · Suppliers and target prices</h2>
        <button className="primary" onClick={() => act(() => post(`/requests/${id}/discover`))}>Find suppliers and prices</button>
        <p className="muted">Prices come from synthetic price lists and are labelled unconfirmed. {ai ? "AI may add suggestions; they arrive unticked." : <AiOff what="the pool comes from the rules alone." />}</p>
        {d.shortlist.length > 0 && <table><thead><tr><th>Ask?</th><th>Supplier</th><th>Why</th></tr></thead><tbody>
          {d.shortlist.map((s: any) => <tr key={s.id}>
            <td><input type="checkbox" checked={s.selected} onChange={(e) => act(() => post(`/requests/${id}/shortlist/${s.supplier_id}`, { selected: e.target.checked }))} /></td>
            <td>{s.supplier} ({s.country})</td><td className="muted">{s.reason.startsWith("AI suggestion") && <span className="tag acc">AI</span>} {s.reason}</td></tr>)}</tbody></table>}
      </section>

      <section><h2>Step 4 · Letters to suppliers (nothing is sent until you approve)</h2>
        <button onClick={() => act(() => post(`/requests/${id}/rfqs/draft`))} disabled={d.shortlist.length === 0}>Draft letters</button>
        {d.rfqs.map((r: any) => <div className="letter" key={r.id}>
          <div className="row"><b>{r.supplier}</b><span className="tag">{r.language}</span><span className="tag">{r.status}</span>{aiTag(r.drafted_by)}</div>
          {r.status === "draft" ? <>
            <textarea defaultValue={r.body} onBlur={(e) => e.target.value !== r.body && act(() => api(`/rfqs/${r.id}`, { method: "PATCH", json: { body: e.target.value } }))} />
            <div className="row">
              <button className="primary" disabled={!who} onClick={() => act(() => post(`/rfqs/${r.id}/decision`, { approve: true, decided_by: who }))}>Approve and send to Mailpit</button>
              <button disabled={!who} onClick={() => act(() => post(`/rfqs/${r.id}/decision`, { approve: false, decided_by: who }))}>Reject</button></div>
          </> : <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>{r.body}</pre>}
        </div>)}
      </section>

      <section><h2>Step 5 · Offers and scoring</h2>
        <ReplyPanel {...ctx} />
        <div className="row"><button onClick={() => act(() => post(`/requests/${id}/offers/simulate`))}>Simulate supplier answers (demo only)</button>
          <span className="muted">{d.offers.length} offer(s)</span></div>
        <div className="row">{Object.keys(w).map((k) => <label key={k}>{k.replace("_", " ")} {(w as any)[k]}
          <input type="range" min={0} max={100} value={(w as any)[k]} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} /></label>)}
          <button onClick={() => act(async () => setRanked(await post(`/requests/${id}/score`, w) as any[]))} disabled={d.offers.length === 0}>Score</button></div>
        {ranked.length > 0 && <table><thead><tr><th>Supplier</th><th>Total</th><th>price</th><th>lead</th><th>reliab.</th><th>terms</th><th>risk</th><th>Cost EUR</th><th>Days</th><th></th></tr></thead><tbody>
          {ranked.map((r) => <tr key={r.offer_id}><td>{r.supplier} ({r.country}){r.flags.length > 0 && <div className="muted">{r.flags.join("; ")}</div>}{r.term_flags?.length > 0 && <div className="muted">{r.term_flags.join("; ")}</div>}{(r.incoterm || r.payment_days != null || r.valid_until) && <div className="muted">{[r.incoterm && `${r.incoterm}${r.incoterm_place ? " " + r.incoterm_place : ""}`, r.payment_days != null && `pay in ${r.payment_days} d`, r.valid_until && `valid until ${r.valid_until}`].filter(Boolean).join(" · ")}</div>}</td>
            {r.excluded ? <td colSpan={5} className="err">Excluded: {r.excluded}</td> : <><td><b>{r.total}</b></td>{["price", "lead_time", "reliability", "terms", "external_risk"].map((c) => <td key={c}>{r.scores[c]}</td>)}</>}
            <td>{eur(r.landed_cost_eur)}<div><span className={`tag ${r.cost_source === "calculation" ? "ok" : "warn"}`} title={r.cost_note || "saved in the Calculator"}>{r.cost_source}</span> <Link href={`/calculator?request=${id}&offer=${r.offer_id}`}>calculate</Link></div></td><td>{r.lead_time_days}</td>
            <td>{!r.excluded && <button disabled={!who} onClick={() => act(() => post(`/requests/${id}/quotes`, { offer_id: r.offer_id, markup: markup / 100, currency: cur, created_by: who }))}>Quote this</button>}</td></tr>)}</tbody></table>}
        <div className="row"><label>Markup % <input type="number" style={{ width: "5rem" }} value={markup} onChange={(e) => setMarkup(Number(e.target.value))} /></label>
          <select value={cur} onChange={(e) => setCur(e.target.value)}><option>EUR</option><option>RSD</option><option>USD</option></select>
          <span className="muted">Scores are computed by code, not by AI. Demo exchange rates.</span></div>
        <ExplainScores id={id} ai={ai} w={w} disabled={d.offers.length === 0} />
        <Comparison id={id} offers={d.offers.length} />
      </section>

      <Followups {...ctx} />

      <section><h2>Steps 6-7 · Customer quote and outcome</h2>
        {d.quotes.map((q: any) => <div className="letter" key={q.id}>
          <div className="row"><b>Quote #{q.id}: {eur(q.price)} {q.currency}</b><span className="tag">markup {(q.markup * 100).toFixed(1)}%</span><span className="tag">cost {eur(q.cost_eur)} EUR</span><span className="tag">{q.status}</span>{aiTag(q.drafted_by)}
            {q.price_eur < q.cost_eur && <span className="err">below cost</span>}</div>
          {q.status === "draft" ? <>
            <textarea defaultValue={q.body} onBlur={(e) => e.target.value !== q.body && act(() => api(`/quotes/${q.id}`, { method: "PATCH", json: { body: e.target.value } }))} />
            <div className="row"><button className="primary" disabled={!who} onClick={() => act(() => post(`/quotes/${q.id}/decision`, { approve: true, decided_by: who }))}>Approve and send to customer (Mailpit)</button>
              <button disabled={!who} onClick={() => act(() => post(`/quotes/${q.id}/decision`, { approve: false, decided_by: who }))}>Reject</button></div></> : null}
        </div>)}
        {sentQuote && <div className="row"><b>Customer answer:</b>
          {["accepted", "rejected", "silence"].map((k) => <button key={k} disabled={!who} onClick={() => act(() => post(`/quotes/${sentQuote.id}/outcome`, { kind: k, confirmed_by: who }))}>{k}</button>)}
          <button disabled={!who} onClick={() => { const p = Number(prompt(`Price named by the customer (${sentQuote.currency})`)); if (p) act(() => post(`/quotes/${sentQuote.id}/outcome`, { kind: "counter", price: p, confirmed_by: who })); }}>counter-offer</button></div>}
        {sentQuote && <CustomerReply {...ctx} quote={sentQuote} />}
        {d.outcomes.map((o: any) => <div key={o.id} className="muted">Outcome: {o.kind}{o.price ? ` at ${o.price} ${o.currency}` : ""} (confirmed by {o.confirmed_by})</div>)}
      </section>

      <section><h2>Step 8 · Purchase order and invoice request</h2>
        <p className="muted">Only possible after the customer accepted. The budget check must pass.</p>
        <button className="primary" disabled={!who || !lastQuote} onClick={() => act(() => post(`/requests/${id}/orders`, { approved_by: who }))}>Approve purchase order</button>
        {d.orders.map((o: any) => <div className="letter" key={o.id}>
          <div className="row"><b>PO #{o.id}</b><span className="tag">cost {eur(o.total_eur)} EUR</span><span className="tag">budget checks: {o.budget_checks.within_po_limit && o.budget_checks.not_below_cost ? "passed" : "failed"}</span></div>
          {o.invoice_requested_by ? <span className="muted">Invoice requested by {o.invoice_requested_by}</span>
            : <InvoiceRequest po={o} who={who} act={act} post={post} />}
          <OrderLetters {...ctx} po={o} />
        </div>)}
      </section>

      <LegalPanel id={id} />

      <TasksPanel id={id} who={who} stage={d.pipeline.stage} act={act} post={post} />

      <section><h2>Price journal</h2>
        <table><thead><tr><th>When</th><th>What</th><th>Amount</th><th>By</th></tr></thead><tbody>
          {d.events.map((e: any) => <tr key={e.id}><td>{new Date(e.created_at).toLocaleString()}</td><td>{e.kind}</td><td>{eur(e.amount)} {e.currency}</td><td>{e.actor}{e.actor_id ? ` (${e.actor_id})` : ""}</td></tr>)}</tbody></table>
      </section>
    </>
  );
}

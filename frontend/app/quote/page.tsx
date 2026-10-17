"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, eur } from "../lib/api";
import { usePerson } from "../lib/person";

function Inner() {
  const { person } = usePerson();
  const who = person.trim();
  const params = useSearchParams();
  const [reqs, setReqs] = useState<any[]>([]);
  const [rid, setRid] = useState(params.get("request") ?? "");
  const [d, setD] = useState<any>(null);
  const [ranked, setRanked] = useState<any[]>([]);
  const [offerId, setOfferId] = useState<number | null>(null);
  const [markup, setMarkup] = useState(15);
  const [cur, setCur] = useState("EUR");
  const [prev, setPrev] = useState<any>(null);
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    if (!rid) { setD(null); return; }
    const [pipeline, items, offers, quotes] = await Promise.all(["pipeline", "items", "offers", "quotes"].map((p) => api(`/requests/${rid}/${p}`)));
    setD({ pipeline, items, offers, quotes });
  }, [rid]);

  useEffect(() => { api<any[]>("/requests").then((r) => setReqs(r.filter((x) => x.status === "confirmed"))).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { setRanked([]); setOfferId(null); setPrev(null); refresh().catch((e) => setErr(e.message)); }, [refresh]);
  useEffect(() => {
    api("/config").then((c: any) => setMarkup(Math.round(c.default_markup * 100))).catch(() => {});
  }, []);
  useEffect(() => {
    if (!rid || offerId == null) { setPrev(null); return; }
    const t = setTimeout(() => api(`/requests/${rid}/quote-preview?offer_id=${offerId}&markup=${markup / 100}&currency=${cur}`).then(setPrev).catch((e) => setErr(e.message)), 150);
    return () => clearTimeout(t);
  }, [rid, offerId, markup, cur]);

  async function act(fn: () => Promise<unknown>) {
    setErr("");
    try { await fn(); await refresh(); } catch (e: any) { setErr(e.message); }
  }
  const post = (path: string, json: unknown = {}) => api(path, { method: "POST", json });

  return (
    <>
      <div className="row">
        <select value={rid} onChange={(e) => setRid(e.target.value)}><option value="">select a confirmed request</option>
          {reqs.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.sender} · {r.subject}</option>)}</select>
        {rid && <Link href={`/requests/${rid}`}>full pipeline →</Link>}
        {d && <span className="tag acc">stage: {d.pipeline.stage}</span>}
      </div>
      {err && <div className="err">{err}</div>}
      {!rid && <p className="muted">Select a request. The offer is built from scored supplier answers, a markup and your approval; nothing reaches the customer without it.</p>}
      {d && (
        <div className="quote-grid">
          <section>
            <h2>1 · Supplier offers</h2>
            <table><tbody>{d.items.map((i: any) => <tr key={i.id}><td className="num">{i.quantity ?? "?"} ×</td><td>{i.description}</td></tr>)}</tbody></table>
            <div className="row">
              <button onClick={() => act(() => post(`/requests/${rid}/offers/simulate`))}>Simulate supplier answers (demo)</button>
              <button className="primary" disabled={d.offers.length === 0} onClick={() => act(async () => setRanked((await post(`/requests/${rid}/score`)) as any[]))}>Score</button>
              <span className="muted">offers: {d.offers.length}. Supplier letters are prepared on the request page.</span>
            </div>
            {ranked.length > 0 && (
              <table>
                <thead><tr><th></th><th>Supplier</th><th>Score</th><th>Cost, EUR</th><th>Lead time, days</th></tr></thead>
                <tbody>{ranked.map((r) => (
                  <tr key={r.offer_id} className={r.excluded ? "" : "click"} style={r.excluded ? { opacity: 0.6 } : undefined} onClick={() => !r.excluded && setOfferId(r.offer_id)}>
                    <td><input type="radio" disabled={!!r.excluded} checked={offerId === r.offer_id} readOnly /></td>
                    <td>{r.supplier} ({r.country}){r.flags.length > 0 && <div className="muted">{r.flags.join("; ")}</div>}{r.excluded && <div className="err">excluded: {r.excluded}</div>}</td>
                    <td className="num">{r.excluded ? "—" : <b>{r.total}</b>}</td><td className="num">{eur(r.landed_cost_eur)}</td><td className="num">{r.lead_time_days}</td>
                  </tr>))}</tbody>
              </table>
            )}
            <p className="muted">Scores are computed by code with fixed formulas, not by AI. Cost includes estimated duties and delivery.</p>
          </section>

          <section>
            <h2>2 · Customer price</h2>
            <div className="row">
              <label>Markup, % <input type="number" style={{ width: "5rem" }} value={markup} onChange={(e) => setMarkup(Number(e.target.value))} /></label>
              <input type="range" min={-10} max={60} value={markup} onChange={(e) => setMarkup(Number(e.target.value))} />
              <select value={cur} onChange={(e) => setCur(e.target.value)}><option>EUR</option><option>RSD</option><option>USD</option></select>
            </div>
            {!prev && <p className="muted">Pick a supplier offer on the left.</p>}
            {prev && (
              <>
                <div className="kpis">
                  <div className="kpi"><div className="v">{eur(prev.landed_cost_eur)}</div><div className="l">cost, EUR</div></div>
                  <div className="kpi"><div className="v">{eur(prev.price)}</div><div className="l">customer price, {prev.currency}</div></div>
                  <div className="kpi" style={{ borderTopColor: prev.below_cost ? "var(--bad)" : "var(--ok)" }}><div className="v">{eur(prev.margin_eur)}</div><div className="l">margin, EUR</div></div>
                </div>
                {prev.below_cost && <div className="err">Price is below cost: this quote cannot be taken to an order.</div>}
                <button className="primary" disabled={!who || !!prev.excluded} onClick={() => act(() => post(`/requests/${rid}/quotes`, { offer_id: offerId, markup: markup / 100, currency: cur, created_by: who }))}>Create quote draft</button>
                {!who && <span className="muted"> Enter your name at the top.</span>}
              </>
            )}
          </section>

          <section className="wide">
            <h2>3 · Letters to the customer</h2>
            {d.quotes.length === 0 && <p className="muted">No drafts yet.</p>}
            {d.quotes.map((q: any) => (
              <div className="letter" key={q.id}>
                <div className="row"><b>Quote #{q.id}: {eur(q.price)} {q.currency}</b><span className="tag">markup {(q.markup * 100).toFixed(1)}%</span><span className="tag">cost {eur(q.cost_eur)} EUR</span>
                  <span className={`tag ${q.status === "sent" ? "ok" : q.status === "rejected" ? "bad" : "warn"}`}>{q.status === "draft" ? "draft" : q.status === "sent" ? "sent" : "rejected"}</span></div>
                {q.status === "draft" ? (
                  <>
                    <div className="muted">Subject: {q.subject}</div>
                    <textarea defaultValue={q.body} onBlur={(e) => e.target.value !== q.body && act(() => api(`/quotes/${q.id}`, { method: "PATCH", json: { body: e.target.value } }))} />
                    <div className="row">
                      <button className="primary" disabled={!who} onClick={() => act(() => post(`/quotes/${q.id}/decision`, { approve: true, decided_by: who }))}>Approve and send to customer (to Mailpit)</button>
                      <button disabled={!who} onClick={() => act(() => post(`/quotes/${q.id}/decision`, { approve: false, decided_by: who }))}>Reject</button>
                    </div>
                  </>
                ) : <pre className="body-text muted">{q.body}</pre>}
              </div>))}
            {d.quotes.some((q: any) => q.status === "sent") && <p className="muted">Customer answer, purchase order and invoice request: <Link href={`/requests/${rid}`}>on the request page</Link>.</p>}
          </section>
        </div>
      )}
    </>
  );
}

export default function Quote() {
  return <Suspense fallback={<p>Loading...</p>}><Inner /></Suspense>;
}

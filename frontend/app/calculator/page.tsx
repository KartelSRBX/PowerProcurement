"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, eur, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

type Row = { key: number; description: string; quantity: string; unit_price: string; hs_code: string; duty_pct: string; vat_pct: string; hint?: any; choices?: any[]; hintErr?: string };

const num = (s: string) => (s.trim() === "" || isNaN(Number(s)) ? null : Number(s));
const blank = (key: number): Row => ({ key, description: "", quantity: "1", unit_price: "", hs_code: "", duty_pct: "", vat_pct: "" });
const pct = (v: unknown) => (typeof v === "number" ? `${v.toLocaleString("en", { maximumFractionDigits: 2 })}%` : String(v ?? "-"));
const SHARED: [string, string, string][] = [
  ["origin", "Origin charges", "loading and export clearance"],
  ["freight", "Main carriage", "freight to the border"],
  ["insurance", "Insurance", "a quoted premium"],
  ["inland", "Transport inside the country", "from the border to the warehouse"],
  ["clearance", "Customs agent and fees", ""],
];

function Inner() {
  const params = useSearchParams();
  const { person } = usePerson();
  const [reqs, setReqs] = useState<any[]>([]);
  const [rid, setRid] = useState(params.get("request") ?? "");
  const [draft, setDraft] = useState<any>(null);
  const [offerId, setOfferId] = useState(params.get("offer") ?? "");
  const [currency, setCurrency] = useState("EUR");
  const [incoterm, setIncoterm] = useState("");
  const [rules, setRules] = useState<string[]>([]);
  const [country, setCountry] = useState("");
  const [rows, setRows] = useState<Row[]>([blank(1)]);
  const [cost, setCost] = useState<Record<string, string>>({});
  const [insPct, setInsPct] = useState("");
  const [inlandIn, setInlandIn] = useState("");
  const [vat, setVat] = useState("");
  const [recoverable, setRecoverable] = useState(true);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState("");
  const [notes, setNotes] = useState<string[]>([]);
  const [saved, setSaved] = useState<any>(null);
  const [saveNote, setSaveNote] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { api<any[]>("/requests").then(setReqs).catch(() => setReqs([])); }, []);
  useEffect(() => { api<any>("/legal/incoterms").then((d) => setRules(d.rules.map((x: any) => x.code))).catch(() => setRules([])); }, []);

  const fill = useCallback((inp: any) => {
    setCurrency(inp.currency); setIncoterm(inp.incoterm ?? "");
    setRows(inp.lines.map((l: any, i: number) => ({ key: i + 1, description: l.description, quantity: String(l.quantity), unit_price: String(l.unit_price), hs_code: l.hs_code ?? "", duty_pct: l.duty_pct == null ? "" : String(l.duty_pct), vat_pct: l.vat_pct == null ? "" : String(l.vat_pct) })));
    setCost(Object.fromEntries(SHARED.map(([k]) => [k, inp[k] == null ? "" : String(inp[k])])));
    setInsPct(inp.insurance_pct == null ? "" : String(inp.insurance_pct));
    setInlandIn(inp.inland_in_price ? String(inp.inland_in_price) : "");
    setVat(inp.vat_pct == null ? "" : String(inp.vat_pct));
    setRecoverable(inp.vat_recoverable !== false);
  }, []);

  const load = useCallback(async (request: string, offer: string) => {
    setErr(""); setNotes([]); setSaved(null); setSaveNote(null);
    if (!request) { setDraft(null); return; }
    try {
      const d = await api<any>(`/requests/${request}/landed-draft${offer ? `?offer_id=${offer}` : ""}`);
      setDraft(d);
      if (offer) { setCountry(d.origin_country ?? ""); }
      if (offer && d.saved) { fill(d.saved.inputs); setSaved(d.saved); }
      else {
        if (offer) { setCurrency(d.currency); setIncoterm(d.incoterm ?? ""); }
        setRows(d.lines.map((l: any, i: number) => ({ ...blank(i + 1), description: l.description, quantity: String(l.quantity), unit_price: l.unit_price == null ? "" : String(l.unit_price) })));
      }
      setNotes(d.notes);
    } catch (e: any) { setErr(e.message); }
  }, [fill]);
  useEffect(() => { load(rid, offerId); }, [rid, offerId, load]);

  const body = () => ({
    currency,
    incoterm: incoterm || null,
    lines: rows.map((r) => ({ description: r.description.trim(), quantity: num(r.quantity), unit_price: num(r.unit_price), hs_code: r.hs_code.trim() || null, duty_pct: num(r.duty_pct), vat_pct: num(r.vat_pct) })),
    ...Object.fromEntries(SHARED.map(([k]) => [k, num(cost[k] ?? "")])),
    insurance_pct: num(insPct),
    inland_in_price: num(inlandIn) ?? 0,
    vat_pct: num(vat),
    vat_recoverable: recoverable,
  });
  const ready = rows.length > 0 && rows.every((r) => r.description.trim() && (num(r.quantity) ?? 0) > 0 && (num(r.unit_price) ?? 0) > 0);

  useEffect(() => {
    if (!ready) { setRes(null); return; }
    const t = setTimeout(() => {
      api<any>("/pricing/landed", { method: "POST", json: body() }).then((d) => { setRes(d); setErr(""); }).catch((e) => { setRes(null); setErr(e.message); });
    }, 300);
    return () => clearTimeout(t);
  }, [rows, currency, incoterm, cost, insPct, inlandIn, vat, recoverable]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setSaveNote(null);
    try {
      const d = await api<any>(`/offers/${offerId}/cost`, { method: "PUT", json: { ...body(), saved_by: person } });
      setSaved(d);
      setSaveNote({ ok: true, text: d.used ? "Saved. Scoring and quotes for this offer now use this calculation." : "Saved, but it is incomplete, so scoring and quotes still use the flat estimate until every figure is given." });
    } catch (e: any) { setSaveNote({ ok: false, text: e.message }); }
  }
  async function unsave() {
    setSaveNote(null);
    try { await api(`/offers/${offerId}/cost`, { method: "DELETE" }); setSaved(null); setSaveNote({ ok: true, text: "Removed. This offer is judged by the flat estimate again." }); }
    catch (e: any) { setSaveNote({ ok: false, text: e.message }); }
  }
  const set = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  async function pick(key: number, code: string) {
    try {
      const d = await api<any>(`/duties/${encodeURIComponent(code)}${country ? `?origin=${encodeURIComponent(country)}` : ""}`);
      set(key, { hint: d, choices: undefined, hs_code: code });
    } catch (e: any) { set(key, { hintErr: e.message }); }
  }
  async function lookup(r: Row) {
    set(r.key, { hint: undefined, choices: undefined, hintErr: undefined });
    try {
      const found = await api<any[]>(`/duties/search?q=${encodeURIComponent(r.hs_code)}&limit=12`);
      if (found.length === 0) set(r.key, { hintErr: "this code is not in the registry" });
      else if (found.length === 1) await pick(r.key, found[0].code);
      else set(r.key, { choices: found });
    } catch (e: any) { set(r.key, { hintErr: e.message }); }
  }
  const needsInlandIn = incoterm === "DAP" || incoterm === "DPU";

  return (
    <div className="pane" style={{ maxWidth: 1100 }}>
      <div className="pane-h"><b>Calculator</b> <span className="muted">what the goods cost once they are in the warehouse</span></div>
      <div className="pane-b">
        <p className="muted">Code does the arithmetic; you give every figure. The Incoterms rule decides which costs the supplier’s price already includes. A figure left empty is counted as zero and the result says so: it is then a lower bound, not a price to decide on.</p>

        <h3>Start from a request</h3>
        <div className="row">
          <select value={rid} onChange={(e) => { setRid(e.target.value); setOfferId(""); }}><option value="">no request, type the items</option>
            {reqs.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.sender} · {r.subject}</option>)}</select>
          {draft && <select value={offerId} onChange={(e) => setOfferId(e.target.value)}><option value="">items only</option>
            {draft.offers.map((o: any) => <option key={o.id} value={o.id}>{o.supplier} · {o.total_price} {o.currency}</option>)}</select>}
          {rid && <Link href={`/requests/${rid}`}>request pipeline</Link>}
        </div>
        {notes.map((n) => <div key={n} className="muted">{n}</div>)}

        <h3>Order</h3>
        <div className="row">
          <label>Prices in <select value={currency} onChange={(e) => setCurrency(e.target.value)}>{["EUR", "USD", "RSD"].map((c) => <option key={c}>{c}</option>)}</select></label>
          <label>Incoterms <select value={incoterm} onChange={(e) => setIncoterm(e.target.value)}><option value="">not stated</option>{rules.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label>Origin country <input style={{ width: "3.5rem" }} maxLength={2} placeholder="CN" value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} /></label>
        </div>
        <table>
          <thead><tr><th>Item</th><th>Quantity</th><th>Unit price</th><th>Tariff code</th><th>Duty, %</th><th>VAT, % (if different)</th><th></th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.key}>
              <td><input aria-label="item" style={{ width: "100%" }} value={r.description} onChange={(e) => set(r.key, { description: e.target.value })} /></td>
              <td><input aria-label="quantity" style={{ width: "5rem" }} inputMode="decimal" value={r.quantity} onChange={(e) => set(r.key, { quantity: e.target.value })} /></td>
              <td><input aria-label="unit price" style={{ width: "6rem" }} inputMode="decimal" value={r.unit_price} onChange={(e) => set(r.key, { unit_price: e.target.value })} /></td>
              <td><span className="row" style={{ margin: 0 }}><input aria-label="tariff code" style={{ width: "8rem" }} placeholder="8517 13" value={r.hs_code} onChange={(e) => set(r.key, { hs_code: e.target.value, hint: undefined, choices: undefined, hintErr: undefined })} />
                <button disabled={!r.hs_code.trim()} onClick={() => lookup(r)}>Find duty</button></span>
                {r.hintErr && <div className="err">{r.hintErr}</div>}
                {r.choices && <div className="muted">{r.choices.length >= 12 ? "12 or more lines start with this; narrow the code or pick one:" : "pick the tariff line:"}
                  {r.choices.map((c: any) => <div key={c.code}><button onClick={() => pick(r.key, c.code)}>{c.code_text}</button> {c.description}</div>)}</div>}
                {r.hint && <div className="muted">{r.hint.description}<br />
                  general {r.hint.applicable.mfn.rate != null ? <button onClick={() => set(r.key, { duty_pct: String(r.hint.applicable.mfn.rate) })}>use {pct(r.hint.applicable.mfn.rate)}</button> : <b>{r.hint.applicable.mfn.text || "see the tariff line"}</b>}
                  {r.hint.applicable.preferential && <> · {r.hint.applicable.preferential.agreement} {r.hint.applicable.preferential.rate != null ? <button onClick={() => set(r.key, { duty_pct: String(r.hint.applicable.preferential.rate) })}>use {pct(r.hint.applicable.preferential.rate)}</button> : r.hint.applicable.preferential.text} (needs proof of origin)</>}
                  {r.hint.freshness?.note && <div className="err">{r.hint.freshness.note}</div>}
                  {r.hint.applicable.notes.filter((n: string) => !n.startsWith("a preferential")).map((n: string) => <div key={n}>{n}</div>)}</div>}</td>
              <td><input aria-label="duty" style={{ width: "5rem" }} inputMode="decimal" value={r.duty_pct} onChange={(e) => set(r.key, { duty_pct: e.target.value })} /></td>
              <td><input aria-label="item VAT" style={{ width: "5rem" }} inputMode="decimal" value={r.vat_pct} onChange={(e) => set(r.key, { vat_pct: e.target.value })} /></td>
              <td><button disabled={rows.length < 2} onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}>Remove</button></td>
            </tr>))}</tbody>
        </table>
        <div className="row"><button onClick={() => setRows((rs) => [...rs, blank(Math.max(0, ...rs.map((r) => r.key)) + 1)])}>Add an item</button></div>

        <h3>Costs of the whole shipment, in {currency}</h3>
        <p className="muted">Split over the items by their value. Leave empty what the supplier’s price already contains or what you do not know yet.</p>
        <div className="row">
          {SHARED.map(([k, label, help]) => (
            <label key={k} title={help}>{label} <input aria-label={label} style={{ width: "7rem" }} inputMode="decimal" value={cost[k] ?? ""} onChange={(e) => setCost({ ...cost, [k]: e.target.value })} /></label>))}
          <label>or insurance rate, % <input aria-label="insurance rate" style={{ width: "4.5rem" }} inputMode="decimal" value={insPct} onChange={(e) => setInsPct(e.target.value)} /></label>
          {needsInlandIn && <label title="Part of the price that pays for transport after the border; it is not part of the customs value">Transport after the border inside the price <input aria-label="inland in price" style={{ width: "7rem" }} inputMode="decimal" value={inlandIn} onChange={(e) => setInlandIn(e.target.value)} /></label>}
        </div>
        <div className="row">
          <label>VAT, % <input aria-label="VAT" style={{ width: "4.5rem" }} inputMode="decimal" value={vat} onChange={(e) => setVat(e.target.value)} /></label>
          <label><input type="checkbox" checked={recoverable} onChange={(e) => setRecoverable(e.target.checked)} /> import VAT is reclaimed as input VAT</label>
        </div>

        {err && <div className="err">{err}</div>}
        {!ready && <p className="muted">Fill in a name, a quantity and a price for each item to see the result.</p>}
        {res && <Result res={res} />}
        {offerId && <div className="letter" data-testid="save-box">
          <b>Use this for the offer</b>
          <div className="muted">Saving makes this calculation the landed cost of the chosen offer in scoring, quote preview, quotes and the purchase order, as long as it is complete and the offer’s price does not change. Without one, a flat estimate by country is used.</div>
          {saved && <div>Saved by {saved.saved_by} on {fmtDate(saved.saved_at)}: {eur(saved.landed_cost_eur)} EUR · {saved.used ? <span className="tag ok">in use</span> : <span className="tag warn">not in use: {!saved.complete ? "incomplete" : "the offer’s price changed"}</span>}</div>}
          <div className="row"><button className="primary" disabled={!person.trim() || !res} onClick={save}>{saved ? "Save again" : "Save for this offer"}</button>
            {saved && <button onClick={unsave}>Remove the saved calculation</button>}
            {!person.trim() && <span className="muted">Enter your name at the top: a person saves a calculation.</span>}</div>
          {saveNote && <div className={saveNote.ok ? "ok-note" : "err"}>{saveNote.text}</div>}
        </div>}
      </div>
    </div>
  );
}

function Result({ res }: { res: any }) {
  const t = res.total;
  return (
    <section data-testid="result">
      <h3>Result {res.complete ? <span className="tag ok">all figures given</span> : <span className="tag warn">incomplete: a lower bound</span>}</h3>
      {t.included_by_seller.length > 0 && <p className="muted">The supplier’s price ({res.incoterm}) already includes: {t.included_by_seller.join(", ")}.</p>}
      {res.you_pay && <div className="letter" data-testid="you-pay">
        <b>{res.you_pay.summary}</b>
        <table style={{ marginTop: ".4rem" }}><tbody>{res.you_pay.lines.map((l: any) => <tr key={l.key}>
          <td>{l.short}</td><td>{l.pays === "you" ? <span className="tag warn">you pay</span> : <span className="tag ok">in the price</span>}</td><td className="muted">{l.text}</td></tr>)}</tbody></table>
        <div className="muted">{res.you_pay.watch}</div>
        <div className="muted">{res.you_pay.source}</div>
      </div>}
      {res.warnings.length > 0 && <ul>{res.warnings.map((w: string) => <li key={w} className="muted">{w}</li>)}</ul>}
      <table>
        <thead><tr><th>Item</th><th>Share</th><th>Goods, EUR</th><th>Customs value</th><th>Duty</th><th>Landed cost</th><th>Per unit</th><th>VAT</th><th>Cash out</th></tr></thead>
        <tbody>{res.lines.map((l: any, i: number) => (
          <tr key={i}><td>{l.description}</td><td className="num">{l.share_pct}%</td><td className="num">{eur(l.value_eur)}</td><td className="num">{eur(l.result.customs_value_eur)}</td>
            <td className="num">{eur(l.result.duty_eur)}</td><td className="num"><b>{eur(l.result.landed_cost_eur)}</b></td><td className="num">{eur(l.landed_per_unit_eur)}</td>
            <td className="num">{eur(l.result.vat_eur)}</td><td className="num">{eur(l.result.cash_out_eur)}</td></tr>))}
          <tr><td><b>Total</b></td><td /><td className="num">{eur(res.lines.reduce((s: number, l: any) => s + l.value_eur, 0))}</td><td className="num">{eur(t.customs_value_eur)}</td>
            <td className="num">{eur(t.duty_eur)}</td><td className="num" data-testid="landed-total"><b>{eur(t.landed_cost_eur)}</b></td><td /><td className="num">{eur(t.vat_eur)}</td><td className="num">{eur(t.cash_out_eur)}</td></tr></tbody>
      </table>
      <h3>Where the money goes</h3>
      <table style={{ maxWidth: 560 }}>
        <tbody>{t.lines.map((ln: any) => <tr key={ln.key}><td>{ln.label}</td><td className="num">{eur(ln.amount_eur)}</td><td className="muted">{ln.note}</td></tr>)}</tbody>
      </table>
      <p className="muted">All amounts in EUR{res.currency !== "EUR" ? `, converted at the rate in Settings (${res.currency === "RSD" ? res.fx.RSD : res.fx.USD} per EUR)` : ""}. {res.rounding}. The rules are simplified for imports into Serbia: have a tax adviser check them before they decide a purchase.</p>
    </section>
  );
}

export default function Calculator() {
  return <Suspense fallback={<p>Loading...</p>}><Inner /></Suspense>;
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, eur } from "../lib/api";
import { usePerson } from "../lib/person";

const blank = { name: "", country: "RS", email: "", categories: "electronics", languages: "sr,en", age_years: 0, deals_count: 0, payment_terms_days: 0, warranty_months: 12, vat_verified: false, framework_contract: false };
const today = new Date().toISOString().slice(0, 10);
const blankLine = { keyword: "", description: "", unit_price: 0, currency: "EUR", moq: 1, lead_time_days: 7, valid_until: `${new Date().getFullYear() + 1}-12-31` };

export default function Suppliers() {
  const { person } = usePerson();
  const [rows, setRows] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [category, setCategory] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [d, setD] = useState<any>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<any>(blank);
  const [line, setLine] = useState<any>(blankLine);
  const [err, setErr] = useState("");

  const load = useCallback(() => api<any[]>("/suppliers/overview").then(setRows).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const open = useCallback((id: number) => { setSel(id); setAdding(false); api(`/suppliers/${id}`).then(setD).catch((e) => setErr(e.message)); }, []);

  async function run(fn: () => Promise<unknown>, reopen?: number) {
    setErr("");
    try { await fn(); await load(); if (reopen) open(reopen); } catch (e: any) { setErr(e.message); }
  }
  const patch = (changes: any) => run(() => api(`/suppliers/${sel}`, { method: "PATCH", json: { changes, changed_by: person } }), sel!);

  const countries = useMemo(() => [...new Set(rows.map((r) => r.country))].sort(), [rows]);
  const cats = useMemo(() => [...new Set(rows.flatMap((r) => r.categories))].sort() as string[], [rows]);
  const shown = rows.filter((r) =>
    (!q || `${r.name} ${r.email}`.toLowerCase().includes(q.toLowerCase())) && (!country || r.country === country) && (!category || r.categories.includes(category)));

  return (
    <>
      {err && <div className="err">{err}</div>}
      <div className="split two">
        <div className="pane">
          <div className="pane-h">
            <div className="row" style={{ margin: 0 }}>
              <input placeholder="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
              <select value={country} onChange={(e) => setCountry(e.target.value)}><option value="">all countries</option>{countries.map((c) => <option key={c}>{c}</option>)}</select>
              <select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">all categories</option>{cats.map((c) => <option key={c}>{c}</option>)}</select>
              <button className="primary" onClick={() => { setAdding(true); setSel(null); setD(null); }}>+ Supplier</button>
            </div>
            <div className="muted">{shown.length} of {rows.length}</div>
          </div>
          <table>
            <thead><tr><th>Supplier</th><th>Country</th><th>Deals</th><th>Payment, days</th><th>Price lines</th></tr></thead>
            <tbody>{shown.map((r) => (
              <tr key={r.id} className={`click ${r.id === sel ? "sel" : ""}`} onClick={() => open(r.id)}>
                <td>{r.name} {r.sanctioned && <span className="tag bad">sanctioned</span>} {r.flags.length > 0 && <span className="tag warn">flags: {r.flags.length}</span>}</td>
                <td>{r.country}</td><td className="num">{r.deals_count}</td><td className="num">{r.payment_terms_days}</td><td className="num">{r.catalog_lines}</td>
              </tr>))}</tbody>
          </table>
        </div>

        <div className="pane"><div className="pane-b">
          {adding && (
            <>
              <h2>New supplier</h2>
              <div className="row"><input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <input style={{ width: "4rem" }} maxLength={2} placeholder="RS" value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} />
                <input placeholder="email sales team" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
              <div className="row"><label>categories <input value={form.categories} onChange={(e) => setForm({ ...form, categories: e.target.value })} /></label>
                <label>languages <input style={{ width: "6rem" }} value={form.languages} onChange={(e) => setForm({ ...form, languages: e.target.value })} /></label></div>
              <div className="row">
                {([["age_years", "years in business"], ["deals_count", "deals"], ["payment_terms_days", "payment, days"], ["warranty_months", "warranty, months"]] as const).map(([k, l]) => (
                  <label key={k}>{l} <input type="number" style={{ width: "5rem" }} value={form[k]} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} /></label>))}
              </div>
              <div className="row"><label><input type="checkbox" checked={form.vat_verified} onChange={(e) => setForm({ ...form, vat_verified: e.target.checked })} /> VAT ID verified</label>
                <label><input type="checkbox" checked={form.framework_contract} onChange={(e) => setForm({ ...form, framework_contract: e.target.checked })} /> framework contract</label></div>
              <button className="primary" disabled={!person.trim() || !form.name.trim() || !form.email.trim()} onClick={() => run(async () => {
                const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
                const r = await api("/suppliers", { method: "POST", json: { ...form, categories: list(form.categories), languages: list(form.languages), changed_by: person } });
                setAdding(false); setForm(blank); open(r.id);
              })}>Save</button>
              {!person.trim() && <span className="muted"> Enter your name at the top.</span>}
            </>
          )}
          {!adding && !d && <div className="muted">Pick a supplier on the left or add a new one. Every change is logged under your name.</div>}
          {!adding && d && d.id === sel && (
            <>
              <h2>{d.name} <span className="tag">{d.country}</span> {d.sanctioned && <span className="tag bad">sanctioned: excluded from mailings</span>}</h2>
              <div className="muted">{d.email} · categories: {d.categories.join(", ")} · languages: {d.languages.join(", ")}</div>
              <div className="kpis" style={{ marginTop: ".8rem" }}>
                {([["RFQs sent", d.history.rfqs_sent], ["offers", d.history.offers], ["orders", d.history.purchase_orders], ["purchased, EUR", eur(d.history.purchase_total_eur)]] as const).map(([l, v]) => (
                  <div className="kpi" key={l}><div className="v" style={{ fontSize: "1.2rem" }}>{v}</div><div className="l">{l}</div></div>))}
              </div>
              <div className="row">
                <span className="tag">years in business: {d.age_years}</span><span className="tag">deals: {d.deals_count}</span><span className="tag">payment: {d.payment_terms_days} days</span><span className="tag">warranty: {d.warranty_months} mo.</span>
                <span className={`tag ${d.vat_verified ? "ok" : "warn"}`}>{d.vat_verified ? "VAT ID verified" : "VAT ID not verified"}</span>
                {d.framework_contract && <span className="tag ok">framework contract</span>}
              </div>
              {d.flags.map((f: any, i: number) => <div key={i} className="muted">⚑ {f.label} ({f.criterion}, −{f.penalty})</div>)}
              <div className="row">
                <button disabled={!person.trim()} onClick={() => patch({ deals_count: d.deals_count + 1 })}>+1 deal</button>
                <button disabled={!person.trim()} onClick={() => patch({ vat_verified: !d.vat_verified })}>{d.vat_verified ? "remove VAT mark" : "mark VAT ID verified"}</button>
                <button className={d.sanctioned ? "" : "danger"} disabled={!person.trim()} onClick={() => confirm(d.sanctioned ? "Remove the sanctions mark?" : "Mark this supplier as sanctioned? It will disappear from matching and mailings.") && patch({ sanctioned: !d.sanctioned })}>{d.sanctioned ? "remove sanctions mark" : "mark: sanctioned"}</button>
              </div>
              <h2 style={{ marginTop: "1rem" }}>Price list ({d.catalog.length})</h2>
              <table>
                <thead><tr><th>Article / key</th><th>Price</th><th>≈ EUR</th><th>MOQ</th><th>Lead time, days</th><th>Until</th></tr></thead>
                <tbody>{d.catalog.map((c: any) => (
                  <tr key={c.id}><td>{c.description}<div className="muted">{c.keyword} · {c.source}</div></td><td className="num">{c.unit_price} {c.currency}</td><td className="num">{eur(c.price_eur)}</td><td className="num">{c.moq}</td><td className="num">{c.lead_time_days}</td>
                    <td>{c.valid_until} {c.expired && <span className="tag bad">expired</span>}</td></tr>))}</tbody>
              </table>
              <div className="letter"><b>Add a price line</b>
                <div className="row"><input placeholder="key (e.g. lm358)" value={line.keyword} onChange={(e) => setLine({ ...line, keyword: e.target.value })} />
                  <input placeholder="description" style={{ flex: 1 }} value={line.description} onChange={(e) => setLine({ ...line, description: e.target.value })} /></div>
                <div className="row">
                  <label>price <input type="number" step="0.01" style={{ width: "6rem" }} value={line.unit_price} onChange={(e) => setLine({ ...line, unit_price: Number(e.target.value) })} /></label>
                  <select value={line.currency} onChange={(e) => setLine({ ...line, currency: e.target.value })}><option>EUR</option><option>RSD</option><option>USD</option></select>
                  <label>MOQ <input type="number" style={{ width: "5rem" }} value={line.moq} onChange={(e) => setLine({ ...line, moq: Number(e.target.value) })} /></label>
                  <label>lead time, days <input type="number" style={{ width: "4.5rem" }} value={line.lead_time_days} onChange={(e) => setLine({ ...line, lead_time_days: Number(e.target.value) })} /></label>
                  <label>valid until <input type="date" min={today} value={line.valid_until} onChange={(e) => setLine({ ...line, valid_until: e.target.value })} /></label>
                  <button className="primary" disabled={!person.trim() || !line.keyword.trim() || line.unit_price <= 0} onClick={() => run(async () => { await api(`/suppliers/${sel}/catalog`, { method: "POST", json: { ...line, changed_by: person } }); setLine(blankLine); }, sel!)}>Add</button>
                </div>
              </div>
            </>
          )}
        </div></div>
      </div>
    </>
  );
}

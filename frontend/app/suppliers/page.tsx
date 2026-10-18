"use client";

import { useCallback, useEffect, useState } from "react";
import { api, eur } from "../lib/api";
import { usePerson } from "../lib/person";
import { CHECK_LABEL, CHECK_TAG, ChecksPanel, ProfilePanel, STATUSES, TIERS } from "./Profile";

const blank = { name: "", country: "RS", email: "", categories: "electronics", languages: "sr,en", age_years: 0, deals_count: 0, payment_terms_days: 0, warranty_months: 12, vat_verified: false, framework_contract: false };
const today = new Date().toISOString().slice(0, 10);
const CSV_TEMPLATE = "keyword,description,unit_price,currency,moq,lead_time_days,valid_until\nlm358,LM358 dual op-amp,0.21,EUR,100,5,2027-12-31\n";
const blankLine = { keyword: "", description: "", unit_price: 0, currency: "EUR", moq: 1, lead_time_days: 7, valid_until: `${new Date().getFullYear() + 1}-12-31` };

export default function Suppliers() {
  const { person } = usePerson();
  const [rows, setRows] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [category, setCategory] = useState("");
  const [brand, setBrand] = useState("");
  const [tier, setTier] = useState("");
  const [check, setCheck] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("name");
  const [dir, setDir] = useState("asc");
  const [facets, setFacets] = useState<any>({ countries: [], categories: [], brands: [], tiers: [], statuses: [], checks: [] });
  const [sel, setSel] = useState<number | null>(null);
  const [d, setD] = useState<any>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<any>(blank);
  const [line, setLine] = useState<any>(blankLine);
  const [err, setErr] = useState("");
  const [csv, setCsv] = useState("");
  const [prev, setPrev] = useState<any>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams({ q, country, category, brand, tier, check, status, sort, dir });
    const fp = new URLSearchParams({ country, category });
    return Promise.all([api<any[]>(`/suppliers/overview?${p}`), api<any>(`/suppliers/facets?${fp}`)])
      .then(([r, f]) => { setRows(r); setFacets(f); }).catch((e) => setErr(e.message));
  }, [q, country, category, brand, tier, check, status, sort, dir]);
  useEffect(() => { const t = setTimeout(load, 150); return () => clearTimeout(t); }, [load]);
  const open = useCallback((id: number) => { setCsv(""); setPrev(null); setSel(id); setAdding(false); api(`/suppliers/${id}`).then(setD).catch((e) => setErr(e.message)); }, []);

  async function run(fn: () => Promise<unknown>, reopen?: number) {
    setErr("");
    try { await fn(); await load(); if (reopen) open(reopen); } catch (e: any) { setErr(e.message); }
  }
  const patch = (changes: any) => run(() => api(`/suppliers/${sel}`, { method: "PATCH", json: { changes, changed_by: person } }), sel!);

  const shown = rows;
  const sortBy = (key: string) => { if (sort === key) setDir(dir === "asc" ? "desc" : "asc"); else { setSort(key); setDir("asc"); } };
  const Th = ({ k, children }: { k: string; children: React.ReactNode }) => (
    <th onClick={() => sortBy(k)} style={{ cursor: "pointer", userSelect: "none" }} aria-sort={sort === k ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      {children}{sort === k ? (dir === "asc" ? " ▲" : " ▼") : ""}
    </th>
  );
  const nameOf = (v: string) => v.replace("_", " ");

  return (
    <>
      {err && <div className="err">{err}</div>}
      <div className="split two">
        <div className="pane">
          <div className="pane-h">
            <div className="row" style={{ margin: 0 }}>
              <input placeholder="Search name, email, brand, product type" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
              <button className="primary" onClick={() => { setAdding(true); setSel(null); setD(null); }}>+ Supplier</button>
            </div>
            <div className="row" style={{ margin: ".4rem 0 0" }}>
              <select value={country} onChange={(e) => { setCountry(e.target.value); setCategory(""); setBrand(""); }}><option value="">all countries</option>{facets.countries.map((c: any) => <option key={c.value} value={c.value}>{c.value} ({c.count})</option>)}</select>
              <select value={category} onChange={(e) => { setCategory(e.target.value); setBrand(""); }}><option value="">all categories</option>{facets.categories.map((c: any) => <option key={c.value} value={c.value}>{c.value} ({c.count})</option>)}</select>
              <select value={brand} onChange={(e) => setBrand(e.target.value)}><option value="">all brands</option>{facets.brands.map((c: any) => <option key={c.value} value={c.value}>{c.value} ({c.count})</option>)}</select>
              <select value={tier} onChange={(e) => setTier(e.target.value)}><option value="">any role</option>{TIERS.map((t) => <option key={t} value={t}>{nameOf(t)}</option>)}</select>
              <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">any status</option>{STATUSES.map((t) => <option key={t} value={t}>{nameOf(t)}</option>)}</select>
              <select value={check} onChange={(e) => setCheck(e.target.value)}><option value="">any check</option>{Object.keys(CHECK_LABEL).map((t) => <option key={t} value={t}>{CHECK_LABEL[t]}</option>)}</select>
              {(country || category || brand || tier || status || check || q) && <button onClick={() => { setQ(""); setCountry(""); setCategory(""); setBrand(""); setTier(""); setStatus(""); setCheck(""); }}>Clear</button>}
            </div>
            <div className="muted">{shown.length} suppliers · click a column title to sort</div>
          </div>
          <table>
            <thead><tr><Th k="name">Supplier</Th><Th k="country">Country</Th><Th k="partner_status">Status</Th><Th k="check">Check</Th><Th k="deals_count">Deals</Th><Th k="payment_terms_days">Payment, days</Th><Th k="stock_delivery_days">Stock, days</Th><Th k="brands">Brands</Th><Th k="catalog_lines">Price lines</Th></tr></thead>
            <tbody>{shown.map((r) => (
              <tr key={r.id} className={`click ${r.id === sel ? "sel" : ""}`} onClick={() => open(r.id)}>
                <td>{r.name} {r.sanctioned && <span className="tag bad">sanctioned</span>} {r.flags.length > 0 && <span className="tag warn">flags: {r.flags.length}</span>}</td>
                <td>{r.country}</td><td>{r.partner_status ? nameOf(r.partner_status) : <span className="muted">–</span>}</td>
                <td><span className={`tag ${CHECK_TAG[r.check_result]}`}>{CHECK_LABEL[r.check_result]}</span></td>
                <td className="num">{r.deals_count}</td><td className="num">{r.payment_terms_days}</td><td className="num">{r.stock_delivery_days ?? "–"}</td><td className="num">{r.brands.length}</td><td className="num">{r.catalog_lines}</td>
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
              <ProfilePanel d={d} person={person} run={run} reopen={d.id} />
              <ChecksPanel d={d} person={person} run={run} reopen={d.id} />
              <h2 style={{ marginTop: "1rem" }}>Price list ({d.catalog.length})</h2>
              <table>
                <thead><tr><th>Article / key</th><th>Price</th><th>≈ EUR</th><th>MOQ</th><th>Lead time, days</th><th>Until</th></tr></thead>
                <tbody>{d.catalog.map((c: any) => (
                  <tr key={c.id}><td>{c.description}<div className="muted">{c.keyword} · {c.source}</div></td><td className="num">{c.unit_price} {c.currency}</td><td className="num">{eur(c.price_eur)}</td><td className="num">{c.moq}</td><td className="num">{c.lead_time_days}</td>
                    <td>{c.valid_until} {c.expired && <span className="tag bad">expired</span>}</td></tr>))}</tbody>
              </table>
              <div className="letter"><b>Import a price list (CSV)</b>
                <p className="muted">Columns: keyword, description, unit_price, currency (EUR/RSD/USD), moq (optional), lead_time_days, valid_until (YYYY-MM-DD). Comma, semicolon or tab separated; decimal comma is fine. A keyword the supplier already has is updated. If any row is invalid nothing is imported.</p>
                <div className="row">
                  <input type="file" accept=".csv,.txt,text/csv" onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setCsv(await f.text()); setPrev(null); } }} />
                  <a href={`data:text/csv;charset=utf-8,${encodeURIComponent(CSV_TEMPLATE)}`} download="price-list-template.csv">download template</a>
                </div>
                <textarea placeholder="…or paste CSV here" value={csv} onChange={(e) => { setCsv(e.target.value); setPrev(null); }} />
                <div className="row">
                  <button disabled={!csv.trim() || !person.trim()} onClick={() => run(async () => setPrev(await api(`/suppliers/${sel}/catalog/import`, { method: "POST", json: { csv, changed_by: person, dry_run: true } })))}>Validate</button>
                  <button className="primary" disabled={!prev || prev.invalid > 0 || prev.applied} onClick={() => run(async () => { await api(`/suppliers/${sel}/catalog/import`, { method: "POST", json: { csv, changed_by: person, dry_run: false } }); setCsv(""); setPrev(null); }, sel!)}>{prev && prev.invalid > 0 ? "Fix errors first" : `Import ${prev ? prev.to_add + prev.to_update : 0} rows`}</button>
                  {prev && <span className={prev.invalid ? "err" : "ok-text"}>{prev.total} rows: {prev.to_add} new, {prev.to_update} updates, {prev.invalid} invalid</span>}
                </div>
                {prev && (
                  <table>
                    <thead><tr><th>Line</th><th>Key</th><th>Price</th><th>MOQ</th><th>Lead time</th><th>Valid until</th><th>Result</th></tr></thead>
                    <tbody>{prev.rows.map((r: any) => (
                      <tr key={r.line}><td className="num">{r.line}</td><td>{r.data.keyword}</td><td className="num">{r.data.unit_price} {r.data.currency}</td><td className="num">{r.data.moq}</td><td className="num">{r.data.lead_time_days}</td><td>{r.data.valid_until}</td>
                        <td>{r.ok ? <span className={`tag ${r.action === "add" ? "ok" : "acc"}`}>{r.action}</span> : <span className="err">{r.errors.join("; ")}</span>}</td></tr>))}</tbody>
                  </table>
                )}
              </div>
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

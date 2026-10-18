"use client";

import { useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

export const TIERS = ["vendor", "distributor", "sub_distributor", "reseller"];
export const STATUSES = ["new", "approved", "preferred", "on_hold"];
export const PAYMENTS = ["prepayment", "on_delivery", "deferred", "credit"];
export const CHECK_TAG: Record<string, string> = { working: "ok", under_review: "warn", not_working: "bad", unchecked: "" };
export const CHECK_LABEL: Record<string, string> = { working: "working", under_review: "under review", not_working: "not working", unchecked: "not checked" };
const label = (s: string) => s.replace("_", " ");
const list = (s: string) => [...new Set(s.split(",").map((x) => x.trim()).filter(Boolean))];

export function ProfilePanel({ d, person, run, reopen }: { d: any; person: string; run: (fn: () => Promise<unknown>, reopen?: number) => Promise<void>; reopen: number }) {
  const named = person.trim().length > 0;
  const [f, setF] = useState<any>(null);
  const [disc, setDisc] = useState({ brand: "", description: "" });
  useEffect(() => {
    setF({
      brands: d.brands.join(", "), product_types: d.product_types.join(", "), brand_tiers: { ...d.brand_tiers },
      stock_delivery_days: d.stock_delivery_days ?? "", payment_type: d.payment_type ?? "", partner_status: d.partner_status ?? "",
      website: d.website ?? "", contract_note: d.contract_note ?? "", has_credit_line: d.has_credit_line,
      credit_line_note: d.credit_line_note ?? "", rebates: d.rebates ?? "",
    });
  }, [d]);
  if (!f) return null;
  const brands = list(f.brands);
  const save = () => run(() => api(`/suppliers/${d.id}`, { method: "PATCH", json: { changed_by: person, changes: {
    brands, product_types: list(f.product_types),
    brand_tiers: Object.fromEntries(brands.filter((b) => f.brand_tiers[b]).map((b) => [b, f.brand_tiers[b]])),
    stock_delivery_days: f.stock_delivery_days === "" ? null : Number(f.stock_delivery_days),
    payment_type: f.payment_type || null, partner_status: f.partner_status || null, website: f.website || null,
    contract_note: f.contract_note || null, has_credit_line: f.has_credit_line, credit_line_note: f.credit_line_note || null, rebates: f.rebates || null,
  } } }), reopen);
  return (
    <>
      <h2 style={{ marginTop: "1rem" }}>Profile</h2>
      <div className="row">
        <label>Status <select value={f.partner_status} onChange={(e) => setF({ ...f, partner_status: e.target.value })}><option value="">not set</option>{STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        <label>Payment <select value={f.payment_type} onChange={(e) => setF({ ...f, payment_type: e.target.value })}><option value="">not set</option>{PAYMENTS.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        <label>Stock delivery, days <input type="number" min={0} style={{ width: "5rem" }} value={f.stock_delivery_days} onChange={(e) => setF({ ...f, stock_delivery_days: e.target.value })} /></label>
      </div>
      <div className="row"><label style={{ flex: 1 }}>Brands (comma separated) <input style={{ width: "100%" }} value={f.brands} onChange={(e) => setF({ ...f, brands: e.target.value })} /></label></div>
      {brands.length > 0 && (
        <div className="row">{brands.map((b) => (
          <label key={b}>{b} <select value={f.brand_tiers[b] ?? ""} onChange={(e) => setF({ ...f, brand_tiers: { ...f.brand_tiers, [b]: e.target.value } })}>
            <option value="">role not set</option>{TIERS.map((t) => <option key={t} value={t}>{label(t)}</option>)}</select></label>))}
        </div>
      )}
      <div className="row"><label style={{ flex: 1 }}>Product types (comma separated) <input style={{ width: "100%" }} value={f.product_types} onChange={(e) => setF({ ...f, product_types: e.target.value })} /></label></div>
      <div className="row">
        <label style={{ flex: 1 }}>Website <input style={{ width: "100%" }} value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} /></label>
        <label style={{ flex: 1 }}>Contract note <input style={{ width: "100%" }} value={f.contract_note} onChange={(e) => setF({ ...f, contract_note: e.target.value })} /></label>
      </div>
      <div className="row">
        <label><input type="checkbox" checked={f.has_credit_line} onChange={(e) => setF({ ...f, has_credit_line: e.target.checked })} /> credit line</label>
        <input placeholder="credit line note" style={{ flex: 1 }} value={f.credit_line_note} onChange={(e) => setF({ ...f, credit_line_note: e.target.value })} />
        <input placeholder="rebates" style={{ flex: 1 }} value={f.rebates} onChange={(e) => setF({ ...f, rebates: e.target.value })} />
      </div>
      <div className="row"><button className="primary" disabled={!named} onClick={save}>Save profile</button>{!named && <span className="muted">Enter your name at the top.</span>}</div>

      <h2 style={{ marginTop: "1rem" }}>Discounts by brand</h2>
      {d.discounts.length === 0 && <div className="muted">None recorded.</div>}
      {d.discounts.map((x: any) => (
        <div key={x.id} className="row" style={{ margin: ".2rem 0" }}><b>{x.brand}</b><span>{x.description}</span>
          <button disabled={!named} onClick={() => run(() => api(`/suppliers/discounts/${x.id}?changed_by=${encodeURIComponent(person)}`, { method: "DELETE" }), reopen)}>remove</button></div>))}
      <div className="row">
        <input list="brand-list" placeholder="brand" style={{ width: "10rem" }} value={disc.brand} onChange={(e) => setDisc({ ...disc, brand: e.target.value })} />
        <datalist id="brand-list">{brands.map((b) => <option key={b} value={b} />)}</datalist>
        <input placeholder="e.g. 5% from 100 pcs" style={{ flex: 1 }} value={disc.description} onChange={(e) => setDisc({ ...disc, description: e.target.value })} />
        <button disabled={!named || !disc.brand.trim() || !disc.description.trim()} onClick={() => run(async () => { await api(`/suppliers/${d.id}/discounts`, { method: "POST", json: { ...disc, changed_by: person } }); setDisc({ brand: "", description: "" }); }, reopen)}>Add discount</button>
      </div>
    </>
  );
}

export function ChecksPanel({ d, person, run, reopen }: { d: any; person: string; run: (fn: () => Promise<unknown>, reopen?: number) => Promise<void>; reopen: number }) {
  const named = person.trim().length > 0;
  const [f, setF] = useState({ result: "working", contact_details: "", note: "" });
  return (
    <>
      <h2 style={{ marginTop: "1rem" }}>Checks <span className={`tag ${CHECK_TAG[d.check_result]}`}>{CHECK_LABEL[d.check_result]}</span></h2>
      <div className="muted">The newest check counts. A supplier whose newest check says “not working” is left out of new shortlists.</div>
      {d.checks.map((c: any) => (
        <div key={c.id} className="row" style={{ margin: ".25rem 0" }}>
          <span className={`tag ${CHECK_TAG[c.result]}`}>{CHECK_LABEL[c.result]}</span>
          <span>{c.checked_by}</span><span className="muted">{fmtDate(c.checked_at)}</span>
          {c.contact_details && <span className="muted">contact: {c.contact_details}</span>}{c.note && <span>{c.note}</span>}
        </div>))}
      <div className="row">
        <select value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}><option value="working">working</option><option value="under_review">under review</option><option value="not_working">not working</option></select>
        <input placeholder="who we spoke to / contact" style={{ flex: 1 }} value={f.contact_details} onChange={(e) => setF({ ...f, contact_details: e.target.value })} />
        <input placeholder="note" style={{ flex: 1 }} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
        <button className="primary" disabled={!named} onClick={() => run(async () => { await api(`/suppliers/${d.id}/checks`, { method: "POST", json: { ...f, checked_by: person } }); setF({ result: "working", contact_details: "", note: "" }); }, reopen)}>Record check</button>
      </div>
    </>
  );
}

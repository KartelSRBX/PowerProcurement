"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";
import { Duties } from "./Duties";

export default function Settings() {
  const { person } = usePerson();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [provider, setProvider] = useState("mock");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [fxSource, setFxSource] = useState("manual");
  const [rsd, setRsd] = useState("");
  const [usd, setUsd] = useState("");
  const [dhWeight, setDhWeight] = useState("0");
  const [dhMin, setDhMin] = useState("3");
  const [invTol, setInvTol] = useState("1");
  const [sig, setSig] = useState({ price: "10", pct: "25", days: "3" });

  const load = useCallback(async () => {
    try {
      const s = await api<any>("/settings");
      setD(s); setProvider(s.ai.provider); setModel(s.ai.model);
      setFxSource(s.fx.source); setRsd(String(s.fx.manual_rsd_per_eur)); setUsd(String(s.fx.manual_usd_per_eur));
      setDhWeight(String(s.scoring.delivery_history_weight)); setDhMin(String(s.scoring.delivery_history_min_orders));
      setInvTol(String(s.invoices.tolerance_pct));
      setSig({ price: String(s.signals.price_rise_pct), pct: String(s.signals.lead_rise_pct), days: String(s.signals.lead_rise_days) });
      setErr("");
    } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const named = person.trim().length > 0;
  async function run(fn: () => Promise<void>) {
    setErr(""); setNote(null);
    try { await fn(); } catch (e: any) { setErr(e.message); }
  }
  const saveAi = (clear = false) => run(async () => {
    const s = await api<any>("/settings/ai", { method: "PUT", json: { changed_by: person, provider, model, api_key: key, clear_key: clear } });
    setD(s); setKey(""); setProvider(s.ai.provider); window.dispatchEvent(new Event("pp-settings")); setNote({ ok: true, text: clear ? "Key removed." : "Saved." });
  });
  const testAi = () => run(async () => {
    const r = await api<any>("/settings/ai/test", { method: "POST", json: {} });
    setNote({ ok: r.ok, text: r.detail });
  });
  const saveFx = () => run(async () => {
    const s = await api<any>("/settings/fx", { method: "PUT", json: { changed_by: person, source: fxSource, rsd_per_eur: Number(rsd), usd_per_eur: Number(usd) } });
    setD(s); setNote({ ok: true, text: "Exchange rates saved." });
  });
  const saveScoring = () => run(async () => {
    const s = await api<any>("/settings/scoring", { method: "PUT", json: { changed_by: person, delivery_history_weight: Number(dhWeight), delivery_history_min_orders: Number(dhMin) } });
    setD(s); setNote({ ok: true, text: "Scoring settings saved." });
  });
  const saveSignals = () => run(async () => {
    const s = await api<any>("/settings/signals", { method: "PUT", json: { changed_by: person, price_rise_pct: Number(sig.price), lead_rise_pct: Number(sig.pct), lead_rise_days: Number(sig.days) } });
    setD(s); setNote({ ok: true, text: "Signal thresholds saved." });
  });
  const saveInvoices = () => run(async () => {
    const s = await api<any>("/settings/invoices", { method: "PUT", json: { changed_by: person, tolerance_pct: Number(invTol) } });
    setD(s); setNote({ ok: true, text: "Invoice tolerance saved." });
  });
  const refreshFx = () => run(async () => {
    const s = await api<any>("/settings/fx/refresh", { method: "POST", json: { changed_by: person } });
    setD(s); setFxSource("nbs"); setNote({ ok: true, text: `Fetched National Bank of Serbia rates for ${s.fetched}.` });
  });

  if (!d) return <p>{err || "Loading..."}</p>;
  const k = d.ai.key;
  return (
    <>
      {err && <div className="err">{err}</div>}
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
      {!named && <div className="muted">Enter your name at the top: every change here is recorded with it.</div>}

      <section>
        <h2>AI (Anthropic Claude)</h2>
        <p className="muted">Used to read customer emails into requests. Without a key the app still works end to end on templates. Calls are billed to your key, so set a spend limit in the Anthropic console first.</p>
        <div className="row">
          <label>Provider <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="mock">mock (no calls, recorded answers)</option><option value="anthropic">anthropic (live)</option></select></label>
          <label>Model <input value={model} onChange={(e) => setModel(e.target.value)} /></label>
        </div>
        <div className="row">
          <label>API key <input type="password" autoComplete="off" placeholder={k.set ? `saved (${k.hint}), leave empty to keep` : "sk-ant-..."} value={key} onChange={(e) => setKey(e.target.value)} style={{ minWidth: "22rem" }} /></label>
          <button className="primary" disabled={!named} onClick={() => saveAi(false)}>Save</button>
          <button disabled={!k.set} onClick={testAi}>Test key</button>
          {k.source === "app" && <button disabled={!named} onClick={() => confirm("Remove the saved key?") && saveAi(true)}>Remove key</button>}
        </div>
        <p className="muted">
          {k.set ? `A key is set (${k.source === "env" ? "from the server environment" : "saved here"}, ends in ${k.hint}).` : "No key set."}{" "}
          The key is stored encrypted on the server and is never shown again or sent back to the browser. If you move the database to another machine, enter the key again.
        </p>
      </section>

      <section>
        <h2>Exchange rates</h2>
        <p className="muted">Used to turn RSD and USD prices into EUR everywhere (matching, offers, quotes). The National Bank of Serbia publishes middle rates daily; the app reads them through a public JSON mirror (<code>{d.fx.url}</code>) and keeps every fetched rate.</p>
        <div className="row">
          <label><input type="radio" checked={fxSource === "nbs"} onChange={() => setFxSource("nbs")} /> National Bank of Serbia (middle rate)</label>
          <label><input type="radio" checked={fxSource === "manual"} onChange={() => setFxSource("manual")} /> Manual</label>
        </div>
        <div className="row">
          <label>RSD per 1 EUR <input value={rsd} onChange={(e) => setRsd(e.target.value)} disabled={fxSource === "nbs"} /></label>
          <label>USD per 1 EUR <input value={usd} onChange={(e) => setUsd(e.target.value)} disabled={fxSource === "nbs"} /></label>
          <button className="primary" disabled={!named} onClick={saveFx}>Save</button>
          <button disabled={!named} onClick={refreshFx}>Fetch from NBS now</button>
        </div>
        <p className="muted">In use now: 1 EUR = {d.fx.rsd_per_eur.toFixed(4)} RSD = {d.fx.usd_per_eur.toFixed(4)} USD ({d.fx.source === "nbs" ? `NBS, rate date ${d.fx.rate_date ?? "–"}` : "manual"}). With NBS selected the app refreshes the rate about every six hours; if the fetch fails it keeps the last good one.</p>
        {d.fx.history.length > 0 && (
          <table>
            <thead><tr><th>Rate date</th><th>RSD per EUR</th><th>USD per EUR</th><th>Fetched</th></tr></thead>
            <tbody>{d.fx.history.map((h: any, i: number) => (
              <tr key={i}><td>{h.rate_date}</td><td className="num">{h.rsd_per_eur.toFixed(4)}</td><td className="num">{h.usd_per_eur.toFixed(4)}</td><td className="muted">{fmtDate(h.fetched_at)}</td></tr>
            ))}</tbody>
          </table>
        )}
      </section>
      <section>
        <h2>Scoring</h2>
        <p className="muted">Delivery history is an extra criterion in the supplier ranking, worked out from the delivery records of the supplier’s delivered orders (the share that came on time, against the date in force and against the first date). Weight 0 keeps it off. A supplier counts only with at least the number of delivered orders below; for a supplier with fewer, the criterion is left out and the ranking says so. The other weights are set on each request.</p>
        <div className="row">
          <label>Weight of delivery history (0–100) <input type="number" min={0} max={100} style={{ width: "5rem" }} value={dhWeight} onChange={(e) => setDhWeight(e.target.value)} data-testid="dh-weight" /></label>
          <label>Delivered orders needed <input type="number" min={2} max={50} style={{ width: "5rem" }} value={dhMin} onChange={(e) => setDhMin(e.target.value)} data-testid="dh-min" /></label>
          <button className="primary" disabled={!named || !(Number(dhWeight) >= 0 && Number(dhWeight) <= 100) || !(Number(dhMin) >= 2 && Number(dhMin) <= 50)} onClick={saveScoring}>Save</button>
        </div>
        <p className="muted">{d.scoring.delivery_history_weight > 0 ? `In use: weight ${d.scoring.delivery_history_weight}, from ${d.scoring.delivery_history_min_orders} delivered orders.` : "Off."}</p>
      </section>
      <section>
        <h2>Article signals</h2>
        <p className="muted">On a request, an offer is flagged when its unit price for an article is this many percent above the last price paid (from an accepted invoice with lines) or ordered for the same article, or when its lead time is longer than the last order’s by both the days and the percent below. The history is this company’s own orders only; a flag is a warning and never changes a score.</p>
        <div className="row">
          <label>Price rise, % <input type="number" min={0} max={500} style={{ width: "5rem" }} value={sig.price} onChange={(e) => setSig({ ...sig, price: e.target.value })} data-testid="sig-price" /></label>
          <label>Lead time rise, % <input type="number" min={0} max={1000} style={{ width: "5rem" }} value={sig.pct} onChange={(e) => setSig({ ...sig, pct: e.target.value })} /></label>
          <label>and at least, days <input type="number" min={0} max={365} style={{ width: "5rem" }} value={sig.days} onChange={(e) => setSig({ ...sig, days: e.target.value })} /></label>
          <button className="primary" disabled={!named || [sig.price, sig.pct, sig.days].some((x) => x === "" || Number(x) < 0)} onClick={saveSignals}>Save</button>
        </div>
        <p className="muted">In use: price +{d.signals.price_rise_pct}%, lead time +{d.signals.lead_rise_pct}% and +{d.signals.lead_rise_days} days.</p>
      </section>

      <section>
        <h2>Supplier invoices</h2>
        <p className="muted">An invoice entered on an order is compared with the offer behind it. A difference up to this share of the order total (and of each unit price) counts as a match; quantities must match exactly. Rounding of a few cents is always allowed.</p>
        <div className="row">
          <label>Tolerance, % <input type="number" min={0} max={20} step={0.1} style={{ width: "5rem" }} value={invTol} onChange={(e) => setInvTol(e.target.value)} data-testid="inv-tol" /></label>
          <button className="primary" disabled={!named || !(Number(invTol) >= 0 && Number(invTol) <= 20) || invTol === ""} onClick={saveInvoices}>Save</button>
        </div>
        <p className="muted">In use: {d.invoices.tolerance_pct}%.</p>
      </section>
      <Duties />
    </>
  );
}

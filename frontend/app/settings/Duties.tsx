"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

const pct = (v: unknown) => (typeof v === "number" ? `${v.toLocaleString("en", { maximumFractionDigits: 2 })}%` : String(v ?? "-"));

/** Customs tariff registry: what was loaded and from where, a search by code or words, the rates for one code. */
export function Duties() {
  const { person } = usePerson();
  const named = person.trim().length > 0;
  const [sum, setSum] = useState<any>(null);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[] | null>(null);
  const [open, setOpen] = useState<any>(null);
  const [origin, setOrigin] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [rateDate, setRateDate] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const loadSummary = useCallback(() => api<any>("/duties/summary").then(setSum).catch(() => setSum(null)), []);
  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => {
    if (!q.trim()) { setRows(null); return; }
    const t = setTimeout(() => api<any[]>(`/duties/search?q=${encodeURIComponent(q)}&limit=40`).then(setRows).catch(() => setRows([])), 250);
    return () => clearTimeout(t);
  }, [q, sum]);
  const show = useCallback((code: string, o: string) =>
    api<any>(`/duties/${code}${o ? `?origin=${encodeURIComponent(o)}` : ""}`).then(setOpen).catch((e) => setNote({ ok: false, text: e.message })), []);
  useEffect(() => { if (open) show(open.code, origin); }, [origin]); // eslint-disable-line react-hooks/exhaustive-deps

  async function upload() {
    if (!file) return;
    setNote(null);
    try {
      const b64: string = await new Promise((ok, no) => {
        const fr = new FileReader();
        fr.onload = () => ok(String(fr.result).split(",")[1] ?? "");
        fr.onerror = () => no(new Error("the file could not be read in the browser"));
        fr.readAsDataURL(file);
      });
      const r = await api<any>("/duties/import/csv", { method: "POST", json: { content_base64: b64, source, rate_date: rateDate || null, imported_by: person } });
      setNote({ ok: true, text: `Loaded ${r.rows} tariff lines; ${r.to_check} need a look. The earlier registry was replaced.` });
      setFile(null); setSum(r); setOpen(null);
    } catch (e: any) { setNote({ ok: false, text: e.message }); }
  }

  return (
    <section>
      <h2>Customs duties</h2>
      <p className="muted">The registry holds the lines of an official customs tariff as printed: the general duty and the rates under trade agreements.
        Nothing is typed in from memory. A preferential rate needs proof of origin, so it is shown beside the general rate and never chosen for you.</p>
      {sum && sum.rows > 0
        ? <p><b>{sum.rows.toLocaleString("en")}</b> lines · {sum.source}{sum.rate_date ? ` · rates from ${sum.rate_date}` : ""} · loaded by {sum.imported_by} on {fmtDate(sum.imported_at)} · <b>{sum.to_check.toLocaleString("en")}</b> lines need a look (a sub-case, a table reference or a specific duty)</p>
        : <p className="muted">Empty. Load a tariff below.</p>}

      {sum && sum.rows > 0 && <>
        <div className="row"><input style={{ flex: 1, minWidth: "16rem" }} placeholder="Code (8517 13) or words from the description" value={q} onChange={(e) => setQ(e.target.value)} />
          <label>Origin country <input style={{ width: "3.5rem" }} maxLength={2} placeholder="CN" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} /></label></div>
        {rows && rows.length === 0 && <p className="muted">Nothing found.</p>}
        {rows && rows.length > 0 && <table><thead><tr><th>Code</th><th>Description</th><th>Unit</th><th>General duty</th><th></th></tr></thead><tbody>
          {rows.map((r) => <tr key={r.code}><td className="num">{r.code_text}</td>
            <td>{r.description}<div className="muted">{r.heading}</div></td><td>{r.unit || "-"}</td>
            <td>{r.mfn_rate != null ? pct(r.mfn_rate) : <span className="err">{r.mfn_text || "see tariff"}</span>}{r.has_exceptions && <div className="muted">has sub-cases</div>}</td>
            <td><button onClick={() => show(r.code, origin)}>Rates</button></td></tr>)}</tbody></table>}
        {open && <div className="letter">
          <div className="row"><b>{open.code_text}</b><span>{open.description}</span><button onClick={() => setOpen(null)}>Close</button></div>
          <div>General duty: <b>{open.applicable.mfn.rate != null ? pct(open.applicable.mfn.rate) : open.applicable.mfn.text}</b>
            {open.applicable.origin && <> · for origin {open.applicable.origin}: {open.applicable.preferential
              ? <b>{open.applicable.preferential.rate != null ? pct(open.applicable.preferential.rate) : open.applicable.preferential.text} ({open.applicable.preferential.agreement})</b>
              : "no agreement rate, the general duty applies"}</>}</div>
          {open.applicable.notes.map((n: string) => <div key={n} className="muted">{n}</div>)}
          <table><thead><tr><th>Agreement</th><th>Rate</th></tr></thead><tbody>
            {Object.entries(open.agreements).map(([k, v]) => <tr key={k}><td>{k}</td><td>{pct(v)}</td></tr>)}</tbody></table>
          <p className="muted">{open.source}{open.rate_date ? ` · from ${open.rate_date}` : ""}</p>
        </div>}
      </>}

      <h3>Load a tariff</h3>
      <p className="muted">From a table (CSV with the columns code, description, heading, unit, mfn_rate, mfn_text, has_exceptions, notes, agreements) made by the loader.
        The official PDF is read on the server by a command, which also saves that table: <code>uv run python -m app.duty.loader --pdf tariff.pdf --source "..." --by "your name" --csv-out tariff.csv</code>.
        Loading replaces the whole registry.</p>
      <div className="row">
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input placeholder="Which tariff (name, gazette)" value={source} onChange={(e) => setSource(e.target.value)} />
        <label>rates from <input type="date" value={rateDate} onChange={(e) => setRateDate(e.target.value)} /></label>
        <button className="primary" disabled={!named || !file || !source.trim()} onClick={upload}>Load</button>
      </div>
      {!named && <div className="muted">Enter your name at the top: a person loads the tariff.</div>}
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
    </section>
  );
}

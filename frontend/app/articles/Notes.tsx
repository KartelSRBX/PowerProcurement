"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

const REL: Record<string, string> = { replacement: "replacement (the second takes over from the first)", equivalent: "equivalent (either can stand in for the other)" };

/** What a person knows about an article: manufacturer, end of life, and links to replacements. The app only repeats it on offers. */
export function Notes({ person }: { person: string }) {
  const named = person.trim().length > 0;
  const [d, setD] = useState<{ records: any[]; alternates: any[] }>({ records: [], alternates: [] });
  const [err, setErr] = useState("");
  const [r, setR] = useState({ part: "", brand: "", eol: false, since: "", note: "" });
  const [a, setA] = useState({ part: "", alt: "", kind: "replacement", note: "" });
  const load = useCallback(() => api<any>("/articles/notes").then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn: () => Promise<unknown>) => { setErr(""); try { await fn(); await load(); } catch (e: any) { setErr(e.message); } };
  const saveRecord = () => run(async () => {
    await api("/articles/notes", { method: "PUT", json: { set_by: person, part_number: r.part, brand: r.brand || null, eol: r.eol, eol_since: r.eol && r.since ? r.since : null, eol_note: r.eol ? r.note : "" } });
    setR({ part: "", brand: "", eol: false, since: "", note: "" });
  });
  const saveLink = () => run(async () => {
    await api("/articles/alternates", { method: "POST", json: { set_by: person, part_number: a.part, alt_part_number: a.alt, kind: a.kind, note: a.note } });
    setA({ part: "", alt: "", kind: "replacement", note: "" });
  });
  return (
    <div data-testid="article-notes">
      <p className="muted">Entered by a person, repeated by the app where an offer for the article is weighed: a manufacturer (so a supplier that is not marked authorized for it is flagged), an end-of-life mark, and links to replacements. The app decides none of it. An article is its part number (letters and digits, case ignored).</p>
      {err && <div className="err">{err}</div>}
      <h2>Manufacturer and end of life</h2>
      <div className="row">
        <input placeholder="Part number" style={{ width: "12rem" }} value={r.part} onChange={(e) => setR({ ...r, part: e.target.value })} data-testid="rec-part" />
        <input placeholder="Manufacturer (brand)" style={{ width: "12rem" }} value={r.brand} onChange={(e) => setR({ ...r, brand: e.target.value })} data-testid="rec-brand" />
        <label><input type="checkbox" checked={r.eol} onChange={(e) => setR({ ...r, eol: e.target.checked })} data-testid="rec-eol" /> end of life</label>
        {r.eol && <><input type="date" value={r.since} onChange={(e) => setR({ ...r, since: e.target.value })} title="since, if known" /><input placeholder="Note (last-time buy, source)" style={{ flex: 1, minWidth: "12rem" }} value={r.note} onChange={(e) => setR({ ...r, note: e.target.value })} /></>}
        <button className="primary" disabled={!named || !r.part.trim() || (!r.brand.trim() && !r.eol)} onClick={saveRecord}>Save</button>
      </div>
      {d.records.length > 0 && <table><thead><tr><th>Article</th><th>Manufacturer</th><th>End of life</th><th>By</th><th></th></tr></thead><tbody>
        {d.records.map((x) => <tr key={x.id}><td>{x.label}</td><td>{x.brand ?? <span className="muted">-</span>}</td>
          <td>{x.eol ? <><span className="tag bad">end of life</span> {x.eol_since && `since ${x.eol_since}`} <span className="muted">{x.eol_note}</span></> : <span className="muted">no</span>}</td><td>{x.set_by}</td>
          <td><button disabled={!named} onClick={() => run(() => api(`/articles/notes/${x.id}?removed_by=${encodeURIComponent(person)}`, { method: "DELETE" }))}>remove</button></td></tr>)}</tbody></table>}

      <h2>Replacements and equivalents</h2>
      <div className="row">
        <input placeholder="Article (part number)" style={{ width: "12rem" }} value={a.part} onChange={(e) => setA({ ...a, part: e.target.value })} data-testid="alt-part" />
        <select value={a.kind} onChange={(e) => setA({ ...a, kind: e.target.value })}>{Object.entries(REL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input placeholder="Other article (part number)" style={{ width: "12rem" }} value={a.alt} onChange={(e) => setA({ ...a, alt: e.target.value })} data-testid="alt-other" />
        <input placeholder="Note (what differs, source)" style={{ flex: 1, minWidth: "12rem" }} value={a.note} onChange={(e) => setA({ ...a, note: e.target.value })} />
        <button className="primary" disabled={!named || !a.part.trim() || !a.alt.trim()} onClick={saveLink}>Link</button>
      </div>
      {d.alternates.length > 0 && <table><thead><tr><th>Article</th><th>Link</th><th>Other article</th><th>Note</th><th>By</th><th></th></tr></thead><tbody>
        {d.alternates.map((x) => <tr key={x.id}><td>{x.label}</td><td>{x.kind === "replacement" ? "is replaced by" : "is equivalent to"}</td><td>{x.alternate_label}</td><td className="muted">{x.note}</td><td>{x.set_by}</td>
          <td><button disabled={!named} onClick={() => run(() => api(`/articles/alternates/${x.id}?removed_by=${encodeURIComponent(person)}`, { method: "DELETE" }))}>remove</button></td></tr>)}</tbody></table>}
      {!named && <p className="muted">Enter your name at the top.</p>}
    </div>
  );
}

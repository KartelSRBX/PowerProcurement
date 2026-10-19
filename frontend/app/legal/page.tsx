"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { Cite, ROLE_LABEL, Sev, toBase64 } from "../lib/legal";
import { usePerson } from "../lib/person";

const TABS: [string, string][] = [["contracts", "Contracts"], ["norms", "Norm base"], ["incoterms", "Incoterms"], ["playbook", "Playbook"], ["settings", "Settings"]];

export default function LegalPage() {
  const [tab, setTab] = useState("contracts");
  return (
    <>
      <h1>Legal · contract review</h1>
      <p className="muted">
        Reads a contract, finds the clauses that matter, and flags the risky ones against your playbook and the loaded law. Rules in code decide what is a risk; a person decides what to do about it.
        This is a first screening to help a manager or lawyer, not legal advice.
      </p>
      <div className="tabs">{TABS.map(([k, l]) => <div key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)}>{l}</div>)}</div>
      {tab === "contracts" && <Contracts />}
      {tab === "norms" && <Norms />}
      {tab === "incoterms" && <Incoterms />}
      {tab === "playbook" && <Playbook />}
      {tab === "settings" && <LegalSettings />}
    </>
  );
}

/* ---------------------------------------------------------------- contracts */

function Contracts() {
  const router = useRouter();
  const { person } = usePerson();
  const named = person.trim().length > 1;
  const [pf, setPf] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ title: "", counterparty: "", role: "buy", request_id: "", expires_on: "", ai_allowed: false, text: "" });
  const [file, setFile] = useState<File | null>(null);
  const [adding, setAdding] = useState<boolean | null>(null);

  const load = useCallback(() => api("/legal/portfolio").then(setPf).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setErr(""); setBusy(true);
    try {
      const body: any = { by: person, title: f.title, counterparty: f.counterparty, role: f.role, ai_allowed: f.ai_allowed };
      if (f.request_id) body.request_id = Number(f.request_id);
      if (f.expires_on) body.expires_on = f.expires_on;
      if (file) { body.filename = file.name; body.content_base64 = await toBase64(file); } else body.text = f.text;
      const c = await api<any>("/legal/contracts", { method: "POST", json: body });
      router.push(`/legal/contracts/${c.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  if (!pf) return <p>{err || "Loading..."}</p>;
  const formOpen = adding ?? pf.contracts === 0;
  return (
    <>
      {err && <div className="err">{err}</div>}
      <div className="kpis">
        <div className="kpi"><div className="v">{pf.contracts}</div><div className="l">Contracts</div></div>
        <div className="kpi"><div className="v" style={{ color: pf.open_red ? "var(--bad)" : undefined }}>{pf.open_red}</div><div className="l">Open risks</div></div>
        <div className="kpi"><div className="v">{pf.open_yellow}</div><div className="l">Open checks</div></div>
        <div className="kpi"><div className="v">{pf.average_payment_days ?? "—"}</div><div className="l">Avg payment days</div></div>
      </div>

      <div className="row"><button className={formOpen ? "" : "primary"} onClick={() => setAdding(!formOpen)}>{formOpen ? "Hide the form" : "Add a contract"}</button></div>
      <div className="grid2">
        {formOpen && <section><h2>Add a contract</h2>
          {!named && <div className="muted">Enter your name at the top first: it is recorded with every decision.</div>}
          <div className="grid2">
            <label>Title<br /><input style={{ width: "100%" }} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Supply agreement, Volt GmbH" /></label>
            <label>Other party<br /><input style={{ width: "100%" }} value={f.counterparty} onChange={(e) => setF({ ...f, counterparty: e.target.value })} /></label>
            <label>Our side<br /><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
              <option value="buy">We buy (the other party is our supplier)</option><option value="sell">We sell (the other party is our customer)</option></select></label>
            <label>Linked request number (optional)<br /><input style={{ width: "7rem" }} value={f.request_id} onChange={(e) => setF({ ...f, request_id: e.target.value.replace(/\D/g, "") })} /></label>
            <label>Expires on (optional)<br /><input type="date" value={f.expires_on} onChange={(e) => setF({ ...f, expires_on: e.target.value })} /></label>
            <label className="row"><input type="checkbox" checked={f.ai_allowed} onChange={(e) => setF({ ...f, ai_allowed: e.target.checked })} />Allow the AI to read this contract</label>
          </div>
          <p className="muted">Off by default. When on, the contract text is sent to the AI provider only when you press “Ask the AI” on the contract page; you see how much is sent first.</p>
          <label>Paste the text, or upload a file (.docx, .pdf, .txt)<br />
            <textarea style={{ minHeight: "9rem" }} disabled={!!file} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} /></label>
          <div className="row">
            <input type="file" accept=".docx,.pdf,.txt,.html,.htm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="primary" disabled={!named || busy || !f.title.trim() || (!file && f.text.trim().length < 50)} onClick={create}>{busy ? "Reading..." : "Review the contract"}</button>
          </div>
        </section>}

        <section><h2>Where the bottlenecks are</h2>
          {pf.bottlenecks.length === 0 ? <p className="muted">Nothing yet. Add a contract to see which problems repeat across contracts.</p>
            : <table><tbody>{pf.bottlenecks.map((b: any) => <tr key={b.rule + b.title}><td>{b.title}</td><td className="num">{b.contracts} contract{b.contracts === 1 ? "" : "s"}</td></tr>)}</tbody></table>}
          {pf.expiring_90_days.length > 0 && <><h2 style={{ marginTop: "1rem" }}>Ending within 90 days</h2>
            {pf.expiring_90_days.map((x: any) => <div key={x.id}><Link href={`/legal/contracts/${x.id}`}>{x.title}</Link> <span className="muted">{x.expires_on}</span></div>)}</>}
          {pf.auto_renewing.length > 0 && <><h2 style={{ marginTop: "1rem" }}>Renew automatically</h2>
            {pf.auto_renewing.map((x: any) => <div key={x.id}><Link href={`/legal/contracts/${x.id}`}>{x.title}</Link></div>)}</>}
          {pf.counterparties.length > 0 && <><h2 style={{ marginTop: "1rem" }}>Risk by other party</h2>
            <table><tbody>{pf.counterparties.map((c: any) => <tr key={c.counterparty}><td>{c.counterparty}</td><td className="num">{c.contracts}</td><td className="num">score {c.average_score}</td></tr>)}</tbody></table></>}
        </section>
      </div>

      <section><h2>All contracts</h2>
        {pf.table.length === 0 ? <p className="muted">No contracts yet.</p> :
          <table><thead><tr><th>Title</th><th>Other party</th><th>Side</th><th>Law</th><th>Forum</th><th>Payment</th><th>Incoterms</th><th>Risks</th><th>Score</th></tr></thead>
            <tbody>{pf.table.map((t: any) => <tr key={t.id}>
              <td><Link href={`/legal/contracts/${t.id}`}>{t.title}</Link></td><td>{t.counterparty}</td><td>{ROLE_LABEL[t.role]}</td>
              <td>{t.law ?? "—"}</td><td>{t.forum ?? "—"}</td><td className="num">{t.payment_days != null ? `${t.payment_days} d` : "—"}</td>
              <td>{t.incoterms?.join(", ") || "—"}</td>
              <td>{t.red > 0 && <span className="sev red">{t.red}</span>} {t.yellow > 0 && <span className="sev yellow">{t.yellow}</span>}</td>
              <td className="num">{t.score}</td></tr>)}</tbody></table>}
      </section>
    </>
  );
}

/* ---------------------------------------------------------------- norm base */

function Norms() {
  const { person } = usePerson();
  const named = person.trim().length > 1;
  const [d, setD] = useState<any>(null);
  const [jur, setJur] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState<any>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[] | null>(null);

  const load = useCallback(() => api("/legal/sources").then(setD).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (key: string, fn: () => Promise<void>) => {
    setNote(null); setBusy(key);
    try { await fn(); await load(); } catch (e: any) { setNote({ ok: false, text: e.message }); } finally { setBusy(""); }
  };
  const fetchOne = (k: string) => run(k, async () => {
    const r = await api<any>(`/legal/sources/${k}/fetch`, { method: "POST", json: { by: person } });
    setNote({ ok: true, text: `${k}: ${r.articles} articles loaded.` });
  });
  const upload = (k: string, file: File) => run(k, async () => {
    const r = await api<any>(`/legal/sources/${k}/upload`, { method: "POST", json: { by: person, filename: file.name, content_base64: await toBase64(file) } });
    setNote({ ok: true, text: `${k}: ${r.articles} articles loaded from ${file.name}.` });
  });
  const view = (k: string) => api(`/legal/sources/${k}`).then(setOpen).catch((e) => setErr(e.message));
  const search = async () => { try { setHits(await api(`/legal/search?q=${encodeURIComponent(q)}${jur ? `&jurisdiction=${jur}` : ""}`)); setErr(""); } catch (e: any) { setErr(e.message); setHits(null); } };

  if (!d) return <p>{err || "Loading..."}</p>;
  const order = Object.keys(d.jurisdictions);
  const rows = d.sources.filter((s: any) => !jur || s.jurisdiction === jur)
    .sort((a: any, b: any) => order.indexOf(a.jurisdiction) - order.indexOf(b.jurisdiction) || a.short.localeCompare(b.short));
  return (
    <>
      {err && <div className="err">{err}</div>}
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
      <section><h2>{d.loaded} of {d.total} acts loaded · {d.articles} articles</h2>
        {d.loaded === 0 && <div className="warn-note">The base is empty. Contract remarks still work, but their law references show “act not loaded yet” until the texts are loaded.
          Press “Load” on an act (the server needs access to eur-lex.europa.eu), or save the act from the official site and use “Upload”. To load everything at once, run <code>python -m app.legal.loader --all</code> on the server.</div>}
        <p className="muted">Texts come from the official sites (EUR-Lex for EU acts, UNCITRAL and UNIDROIT for the international ones). National laws of Serbia, China and the UAE are uploaded from the official gazette or a trusted translation; check the act name before you upload.
          The base holds EU acts, not each member state’s own law.</p>
        <div className="row">
          <label>Show<br /><select value={jur} onChange={(e) => setJur(e.target.value)}><option value="">All</option>
            {Object.entries(d.jurisdictions).map(([k, v]) => <option key={k} value={k}>{String(v)}</option>)}</select></label>
          <label>Search the loaded texts<br /><input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder="e.g. late payment interest" /></label>
          <button onClick={search} disabled={q.trim().length < 3}>Search</button>
        </div>
        {hits && (hits.length === 0 ? <p className="muted">Nothing found in the loaded texts.</p> : hits.map((h, i) => <div className="prov" key={i}>
          <b>{h.short}</b> <span className="n">art. {h.number}</span> {h.heading}<div className="muted">…{h.excerpt}…</div></div>))}
      </section>
      <section>
        <table><thead><tr><th>Act</th><th>Where</th><th>Topics</th><th>Status</th><th /></tr></thead><tbody>
          {rows.map((s: any) => <tr key={s.key}>
            <td><b>{s.short}</b><div className="muted">{s.title}{s.check_name && " (check the name on import)"}</div>{s.note && <div className="muted">{s.note}</div>}</td>
            <td>{s.jurisdiction_name}<div className="muted">{s.ref}</div></td>
            <td>{(s.topics ?? []).map((t: string) => <span className="tag" key={t} style={{ marginRight: ".2rem" }}>{t}</span>)}</td>
            <td>{s.status === "loaded" ? <span className="tag ok">{s.provision_count} articles</span> : <span className="tag">not loaded</span>}
              {s.loaded_by && <div className="muted">{s.loaded_by}</div>}</td>
            <td><div className="row">
              {s.fetch !== "manual" && <button disabled={!named || busy === s.key} onClick={() => fetchOne(s.key)}>{busy === s.key ? "..." : s.status === "loaded" ? "Reload" : "Load"}</button>}
              <label className="tag" style={{ cursor: named ? "pointer" : "default" }}>Upload
                <input type="file" hidden disabled={!named} accept=".html,.htm,.txt,.pdf,.docx" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(s.key, f); e.target.value = ""; }} /></label>
              {s.status === "loaded" && <button onClick={() => view(s.key)}>Read</button>}
            </div></td></tr>)}
        </tbody></table>
      </section>
      {open && <section><h2>{open.short} · {open.title}</h2>
        <button onClick={() => setOpen(null)}>Close</button>
        {open.provisions.map((p: any) => <div className="prov" key={p.number}><span className="n">art. {p.number}</span> <b>{p.heading}</b>
          <div className="body-text muted">{p.text.slice(0, 1200)}{p.text.length > 1200 ? " …" : ""}</div></div>)}
      </section>}
    </>
  );
}

/* ---------------------------------------------------------------- incoterms */

function Incoterms() {
  const [d, setD] = useState<any>(null);
  const [code, setCode] = useState("FCA");
  const [err, setErr] = useState("");
  useEffect(() => { api("/legal/incoterms").then(setD).catch((e) => setErr(e.message)); }, []);
  if (!d) return <p>{err || "Loading..."}</p>;
  const r = d.rules.find((x: any) => x.code === code) ?? d.rules[0];
  return (
    <section><h2>Incoterms® {d.version}: who does what</h2>
      <p className="muted">Our own plain-language summary of the 11 rules, built from the ICC rules’ structure. It is not the ICC text; compare with the official ICC publication before relying on a detail. Contract checks use this table to spot a rule that does not fit the place or the way the goods travel.</p>
      <div className="codes">{d.rules.map((x: any) => <button key={x.code} className={x.code === r.code ? "on" : ""} onClick={() => setCode(x.code)}>{x.code}</button>)}</div>
      <h2>{r.code} · {r.name} <span className="tag">{r.group_label}</span> <span className="tag">{r.modes}</span></h2>
      <p>{r.summary}</p>
      <p className="muted">Named place: {r.place}</p>
      <table className="incot"><thead><tr><th /><th>Seller</th><th>Buyer</th></tr></thead><tbody>
        {r.topics.map((t: any) => <tr key={t.key}><td>{t.label}</td><td>{t.seller}</td><td>{t.buyer}</td></tr>)}</tbody></table>
      <div className="grid2" style={{ marginTop: ".8rem" }}>
        <div className="letter"><b>If we buy</b><div>{r.watch.buy}</div></div>
        <div className="letter"><b>If we sell</b><div>{r.watch.sell}</div></div>
      </div>
      <h2 style={{ marginTop: "1rem" }}>Not covered by Incoterms (write it into the contract)</h2>
      <ul>{d.not_covered.map((x: string) => <li key={x}>{x}</li>)}</ul>
    </section>
  );
}

/* ---------------------------------------------------------------- playbook */

function Playbook() {
  const { person } = usePerson();
  const named = person.trim().length > 1;
  const [rules, setRules] = useState<any[] | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState("");
  const [draft, setDraft] = useState<any>(null);
  const load = useCallback(() => api("/legal/rules").then(setRules).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const patch = async (key: string, values: any) => {
    try { await api(`/legal/rules/${key}`, { method: "PATCH", json: { changed_by: person, values } }); setErr(""); await load(); } catch (e: any) { setErr(e.message); }
  };
  if (!rules) return <p>{err || "Loading..."}</p>;
  return (
    <section><h2>Playbook · {rules.length} checks</h2>
      <div className="warn-note">These thresholds are a <b>starter draft</b>. Have your lawyer or manager review them and set your company’s own limits before relying on the verdicts.</div>
      {err && <div className="err">{err}</div>}
      <table><thead><tr><th>Check</th><th>Side</th><th>Level</th><th>On</th><th /></tr></thead><tbody>
        {rules.map((r) => <Fragment key={r.key}>
          <tr>
            <td><b>{r.title}</b> {r.draft && <span className="tag warn">draft</span>}<div className="muted">{r.key}</div></td>
            <td>{ROLE_LABEL[r.role]}</td>
            <td><select disabled={!named} value={r.severity} onChange={(e) => patch(r.key, { severity: e.target.value })}><option value="red">Risk</option><option value="yellow">Check</option><option value="info">Note</option></select></td>
            <td><input type="checkbox" disabled={!named} checked={r.enabled} onChange={(e) => patch(r.key, { enabled: e.target.checked })} /></td>
            <td><button onClick={() => { setOpen(open === r.key ? "" : r.key); setDraft({ risk: r.risk, suggest: r.suggest, params: r.params }); }}>{open === r.key ? "Close" : "Details"}</button></td>
          </tr>
          {open === r.key && draft && <tr><td colSpan={5}>
            <label>Why it matters<br /><textarea value={draft.risk} onChange={(e) => setDraft({ ...draft, risk: e.target.value })} /></label>
            <label>What to ask for<br /><textarea value={draft.suggest} onChange={(e) => setDraft({ ...draft, suggest: e.target.value })} /></label>
            {Object.keys(draft.params).length > 0 && <div className="row">{Object.entries(draft.params).map(([k, v]) => Array.isArray(v)
              ? <label key={k}>{k.replace(/_/g, " ")}<br /><input value={(draft.params[k] as string[]).join(", ")} onChange={(e) => setDraft({ ...draft, params: { ...draft.params, [k]: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) } })} /></label>
              : <label key={k}>{k.replace(/_/g, " ")}<br /><input type="number" style={{ width: "6rem" }} value={v as number} onChange={(e) => setDraft({ ...draft, params: { ...draft.params, [k]: Number(e.target.value) } })} /></label>)}</div>}
            <div>{r.citations_checked.map((c: any, i: number) => <Cite key={i} c={c} />)}</div>
            <div className="row"><button className="primary" disabled={!named} onClick={() => patch(r.key, { risk: draft.risk, suggest: draft.suggest, params: draft.params, draft: false })}>Save (marks it as reviewed)</button></div>
          </td></tr>}
        </Fragment>)}
      </tbody></table>
    </section>
  );
}

/* ---------------------------------------------------------------- settings */

function LegalSettings() {
  const { person } = usePerson();
  const named = person.trim().length > 1;
  const [s, setS] = useState<any>(null);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => { api("/legal/settings").then(setS).catch((e) => setErr(e.message)); }, []);
  if (!s) return <p>{err || "Loading..."}</p>;
  const list = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);
  const save = async () => {
    try { setS(await api("/legal/settings", { method: "PUT", json: { changed_by: person, values: s } })); setOk("Saved."); setErr(""); } catch (e: any) { setErr(e.message); setOk(""); }
  };
  return (
    <section><h2>Company rules for contracts</h2>
      {err && <div className="err">{err}</div>}{ok && <div className="ok-note">{ok}</div>}
      <label>Governing laws we accept (comma separated)<br /><textarea value={s.approved_laws.join(", ")} onChange={(e) => setS({ ...s, approved_laws: list(e.target.value) })} /></label>
      <label>Courts or arbitration places we accept (comma separated; empty: any is flagged for a look)<br /><textarea style={{ minHeight: "3.5rem" }} value={s.approved_forums.join(", ")} onChange={(e) => setS({ ...s, approved_forums: list(e.target.value) })} /></label>
      <h2 style={{ marginTop: "1rem" }}>Score weights</h2>
      <p className="muted">The contract score is the sum of these weights over its open remarks. Lower is better.</p>
      <div className="row">{["red", "yellow", "info"].map((k) => <label key={k}><Sev s={k} /><br /><input type="number" style={{ width: "6rem" }} value={s.weights[k]} onChange={(e) => setS({ ...s, weights: { ...s.weights, [k]: Number(e.target.value) } })} /></label>)}</div>
      <label className="row"><input type="checkbox" checked={s.require_signoff} onChange={(e) => setS({ ...s, require_signoff: e.target.checked })} />
        Do not allow a purchase order while a linked contract still has an open risk (accept, dismiss or hand it to the lawyer first)</label>
      <div className="row"><button className="primary" disabled={!named} onClick={save}>Save settings</button>{!named && <span className="muted">Enter your name at the top.</span>}</div>
    </section>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

const blank = { category: "supplier portal", name: "", site_url: "", login: "", password: "", comments: "" };
const TAG: Record<string, string> = { pending: "warn", approved: "ok", rejected: "bad", used: "" };

export default function Vault() {
  const { person } = usePerson();
  const who = person.trim();
  const [tab, setTab] = useState<"entries" | "requests" | "log">("entries");
  const [cats, setCats] = useState<string[]>([]);
  const [entries, setEntries] = useState<any[]>([]);
  const [reqs, setReqs] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [form, setForm] = useState<any>(null);  // null = closed; {id?} = add/edit
  const [asking, setAsking] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState<Record<number, string>>({});
  const [secret, setSecret] = useState<{ name: string; login: string; password: string } | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [e, r, l] = await Promise.all([api<any>("/vault"), api<any[]>("/vault/requests"), api<any[]>("/vault/log")]);
      setCats(e.categories); setEntries(e.entries); setReqs(r); setLog(l); setErr("");
    } catch (x: any) { setErr(x.message); }
  }, []);
  useEffect(() => {
    if (who) api("/vault/open", { method: "POST", json: { person: who } }).catch(() => {});
    load();
  }, [who, load]);

  const run = async (fn: () => Promise<unknown>) => { setErr(""); try { await fn(); await load(); } catch (x: any) { setErr(x.message); } };
  const shown = entries.filter((e) => (!cat || e.category === cat) && (!q || `${e.name} ${e.site_url ?? ""} ${e.comments ?? ""}`.toLowerCase().includes(q.toLowerCase())));
  const nameOf = (id: number) => entries.find((e) => e.id === id)?.name ?? `#${id}`;

  const save = () => run(async () => {
    const { id, ...rest } = form;
    if (id) {
      const patch: any = { changed_by: who, category: rest.category, name: rest.name, site_url: rest.site_url || null, comments: rest.comments || null };
      if (rest.login) patch.login = rest.login;
      if (rest.password) patch.password = rest.password;
      await api(`/vault/${id}`, { method: "PATCH", json: patch });
    } else await api("/vault", { method: "POST", json: { ...rest, site_url: rest.site_url || null, comments: rest.comments || null, changed_by: who } });
    setForm(null);
  });

  const mine = reqs.filter((r) => r.requested_by.toLowerCase() === who.toLowerCase());
  const pending = reqs.filter((r) => r.status === "pending");

  return (
    <>
      <div className="err" style={{ background: "transparent", border: "1px solid var(--warn, #c90)", color: "inherit" }}>
        Names here are not sign-ins. The two-person approval is a process aid, not a lock: run the app on a trusted machine only.
        Logins and passwords are stored encrypted and are shown only after a second person approves, once, within 15 minutes.
      </div>
      {err && <div className="err">{err}</div>}
      {!who && <div className="err">Enter your name at the top to use the vault.</div>}
      <div className="tabs">
        <div className={`tab ${tab === "entries" ? "active" : ""}`} onClick={() => setTab("entries")}>Accesses ({entries.length})</div>
        <div className={`tab ${tab === "requests" ? "active" : ""}`} onClick={() => setTab("requests")}>Requests ({pending.length} waiting)</div>
        <div className={`tab ${tab === "log" ? "active" : ""}`} onClick={() => setTab("log")}>Log</div>
      </div>

      {secret && (
        <div className="pane" style={{ marginBottom: "1rem" }}>
          <div className="pane-h"><b>{secret.name}</b> <span className="muted">shown once; close it when done</span></div>
          <div className="pane-b">
            <div className="row">Login <code>{secret.login}</code></div>
            <div className="row">Password <code>{secret.password}</code></div>
            <button onClick={() => setSecret(null)}>Hide</button>
          </div>
        </div>)}

      {tab === "entries" && (
        <div className="pane">
          <div className="pane-h">
            <div className="row" style={{ margin: 0 }}>
              <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
              <select value={cat} onChange={(e) => setCat(e.target.value)}><option value="">all categories</option>{cats.map((c) => <option key={c}>{c}</option>)}</select>
              <button className="primary" disabled={!who} onClick={() => setForm({ ...blank, category: cats[0] ?? blank.category })}>+ Access</button>
            </div>
          </div>
          {form && (
            <div className="pane-b">
              <div className="row">
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{cats.map((c) => <option key={c}>{c}</option>)}</select>
                <input placeholder="name" style={{ flex: 1 }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <input placeholder="site URL" style={{ flex: 1 }} value={form.site_url ?? ""} onChange={(e) => setForm({ ...form, site_url: e.target.value })} />
              </div>
              <div className="row">
                <input placeholder={form.id ? "new login (empty = keep)" : "login"} autoComplete="off" style={{ flex: 1 }} value={form.login} onChange={(e) => setForm({ ...form, login: e.target.value })} />
                <input placeholder={form.id ? "new password (empty = keep)" : "password"} type="password" autoComplete="new-password" style={{ flex: 1 }} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              </div>
              <div className="row"><input placeholder="comments" style={{ flex: 1 }} value={form.comments ?? ""} onChange={(e) => setForm({ ...form, comments: e.target.value })} /></div>
              <div className="row"><button className="primary" disabled={!who || !form.name.trim() || (!form.id && (!form.login || !form.password))} onClick={save}>Save</button><button onClick={() => setForm(null)}>Cancel</button></div>
            </div>)}
          <table>
            <thead><tr><th>Name</th><th>Category</th><th>Site</th><th>Comments</th><th>Updated</th><th></th></tr></thead>
            <tbody>{shown.map((e) => (
              <tr key={e.id}>
                <td>{e.name}</td><td>{e.category}</td><td>{e.site_url}</td><td className="muted">{e.comments}</td>
                <td className="muted">{e.updated_by} {fmtDate(e.updated_at)}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button disabled={!who} onClick={() => { setAsking(e.id); setReason(""); setTab("entries"); }}>Request view</button>{" "}
                  <button disabled={!who} onClick={() => setForm({ ...blank, ...e, login: "", password: "" })}>Edit</button>{" "}
                  <button disabled={!who} onClick={() => { if (confirm(`Delete “${e.name}”?`)) run(() => api(`/vault/${e.id}?changed_by=${encodeURIComponent(who)}`, { method: "DELETE" })); }}>Delete</button>
                </td>
              </tr>))}</tbody>
          </table>
          {shown.length === 0 && <div className="pane-b muted">No accesses stored yet.</div>}
          {asking !== null && (
            <div className="pane-b">
              <b>Request to view “{nameOf(asking)}”</b>
              <div className="row">
                <input placeholder="why do you need it?" style={{ flex: 1 }} value={reason} onChange={(e) => setReason(e.target.value)} />
                <button className="primary" disabled={!reason.trim()} onClick={() => run(async () => { await api(`/vault/${asking}/requests`, { method: "POST", json: { requested_by: who, reason } }); setAsking(null); setTab("requests"); })}>Send request</button>
                <button onClick={() => setAsking(null)}>Cancel</button>
              </div>
            </div>)}
        </div>)}

      {tab === "requests" && (
        <div className="pane">
          <table>
            <thead><tr><th>Access</th><th>Requested by</th><th>Reason</th><th>Status</th><th></th></tr></thead>
            <tbody>{reqs.map((r) => {
              const own = r.requested_by.toLowerCase() === who.toLowerCase();
              return (
                <tr key={r.id}>
                  <td>{r.entry_name ?? nameOf(r.entry_id)}</td>
                  <td>{r.requested_by}<div className="muted">{fmtDate(r.created_at)}</div></td>
                  <td>{r.reason}</td>
                  <td><span className={`tag ${TAG[r.status]}`}>{r.status}</span>{r.decided_by && <div className="muted">by {r.decided_by}{r.decision_comment ? `: ${r.decision_comment}` : ""}</div>}
                    {r.status === "approved" && r.approved_until && <div className="muted">valid until {fmtDate(r.approved_until)}</div>}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {r.status === "pending" && !own && (<>
                      <input placeholder="comment" style={{ width: "9rem" }} value={comment[r.id] ?? ""} onChange={(e) => setComment({ ...comment, [r.id]: e.target.value })} />{" "}
                      <button className="primary" disabled={!who} onClick={() => run(() => api(`/vault/requests/${r.id}/decide`, { method: "POST", json: { decided_by: who, approve: true, comment: comment[r.id] ?? "" } }))}>Approve</button>{" "}
                      <button disabled={!who} onClick={() => run(() => api(`/vault/requests/${r.id}/decide`, { method: "POST", json: { decided_by: who, approve: false, comment: comment[r.id] ?? "" } }))}>Reject</button></>)}
                    {r.status === "pending" && own && <span className="muted">another person must decide</span>}
                    {r.status === "approved" && own && (
                      <button className="primary" onClick={() => run(async () => { const x = await api<any>(`/vault/requests/${r.id}/reveal`, { method: "POST", json: { person: who } }); setSecret({ name: x.entry.name, login: x.login, password: x.password }); })}>Show once</button>)}
                  </td>
                </tr>);
            })}</tbody>
          </table>
          {reqs.length === 0 && <div className="pane-b muted">No requests.</div>}
          {mine.length > 0 && <div className="pane-b muted">You have {mine.length} request(s).</div>}
        </div>)}

      {tab === "log" && (
        <div className="pane">
          <table>
            <thead><tr><th>When</th><th>Person</th><th>Event</th><th>Access</th><th>Detail</th></tr></thead>
            <tbody>{log.map((l) => (
              <tr key={l.id}><td className="muted">{fmtDate(l.at)}</td><td>{l.person}</td><td>{l.event}</td><td>{l.entry_id ? nameOf(l.entry_id) : ""}</td><td className="muted">{l.detail}</td></tr>))}</tbody>
          </table>
        </div>)}
    </>
  );
}

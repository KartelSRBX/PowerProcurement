"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

/** Sign-in: the first administrator, users and their roles, and the switch. Administrators only; everyone signed in can change their own password. */
export function UsersPanel() {
  const { auth, refreshAuth } = usePerson();
  const [list, setList] = useState<any>(null);
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [f, setF] = useState({ name: "", password: "", roles: ["buyer"] as string[] });
  const [login, setLogin] = useState({ name: "", password: "" });
  const [pw, setPw] = useState({ old: "", next: "" });
  const [reset, setReset] = useState<Record<number, string>>({});
  const isAdmin = !!auth?.user?.roles.includes("admin");

  const load = useCallback(async () => {
    if (!isAdmin) { setList(null); return; }
    try { setList(await api<any>("/users")); setErr(""); } catch (e: any) { setErr(e.message); }
  }, [isAdmin]);
  useEffect(() => { load(); }, [load]);
  async function run(fn: () => Promise<any>, msg = "") {
    setErr(""); setNote("");
    try { await fn(); setNote(msg); await refreshAuth(); await load(); } catch (e: any) { setErr(e.message); }
  }
  if (!auth) return null;
  const roles = Object.keys(auth.roles);
  const toggle = (rs: string[], r: string) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]);

  return (
    <section data-testid="users">
      <h2>Sign-in and users <span className={`tag ${auth.enabled ? "ok" : "warn"}`}>{auth.enabled ? "on" : "off"}</span></h2>
      <p className="muted">{auth.enabled
        ? "Everyone signs in. Every action is recorded under the signed-in user's name and cannot be recorded under another."
        : "Sign-in is off: a name typed at the top is only a label in the log, and anyone who can open the app can use any name. Create an administrator, sign in, add the other users, then turn sign-in on."}</p>
      {auth.forced_off && <div className="err">Sign-in is switched off by the server environment (AUTH_FORCE_OFF).</div>}
      {err && <div className="err">{err}</div>}
      {note && <div className="ok-note">{note}</div>}

      {!auth.users_exist && <div className="letter">
        <b>Create the first administrator</b>
        <div className="row">
          <input placeholder="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <input type="password" placeholder="password (10+ characters)" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <button className="primary" disabled={!f.name.trim() || !f.password} onClick={() => run(() => api("/auth/bootstrap", { method: "POST", json: { name: f.name, password: f.password, roles: ["admin"] } }), "Administrator created and signed in.")}>Create</button>
        </div>
      </div>}

      {auth.users_exist && !auth.user && <div className="letter">
        <b>Sign in as an administrator to manage users</b>
        <div className="row">
          <input placeholder="name" value={login.name} onChange={(e) => setLogin({ ...login, name: e.target.value })} />
          <input type="password" placeholder="password" value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} />
          <button className="primary" disabled={!login.name.trim() || !login.password} onClick={() => run(() => api("/auth/login", { method: "POST", json: login }), "Signed in.")}>Sign in</button>
        </div>
      </div>}

      {auth.user && <div className="row">
        <b>Your password</b>
        <input type="password" placeholder="current" value={pw.old} onChange={(e) => setPw({ ...pw, old: e.target.value })} />
        <input type="password" placeholder="new (10+ characters)" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
        <button disabled={!pw.old || !pw.next} onClick={() => run(() => api("/auth/password", { method: "POST", json: { old: pw.old, new: pw.next } }), "Password changed; your other sessions were signed out.").then(() => setPw({ old: "", next: "" }))}>Change</button>
      </div>}

      {isAdmin && list && <>
        <table><thead><tr><th>Name</th><th>Roles</th><th>Active</th><th>Last sign-in</th><th>New password</th></tr></thead><tbody>
          {list.users.map((u: any) => (
            <tr key={u.id}>
              <td>{u.name} {u.locked && <span className="tag bad">locked</span>}</td>
              <td>{roles.map((r) => <label key={r} title={list.roles[r]} style={{ marginRight: ".6rem" }}>
                <input type="checkbox" checked={u.roles.includes(r)} onChange={() => run(() => api(`/users/${u.id}`, { method: "PATCH", json: { roles: toggle(u.roles, r) } }))} /> {r}</label>)}</td>
              <td><input type="checkbox" checked={u.active} onChange={(e) => run(() => api(`/users/${u.id}`, { method: "PATCH", json: { active: e.target.checked } }))} /></td>
              <td className="muted">{u.last_login_at ? fmtDate(u.last_login_at) : "never"}</td>
              <td><input type="password" placeholder="set" style={{ width: "9rem" }} value={reset[u.id] ?? ""} onChange={(e) => setReset({ ...reset, [u.id]: e.target.value })} />
                <button disabled={!reset[u.id]} onClick={() => run(() => api(`/users/${u.id}/password`, { method: "POST", json: { new: reset[u.id] } }), `Password of ${u.name} set; their sessions were ended.`).then(() => setReset({ ...reset, [u.id]: "" }))}>Set</button></td>
            </tr>))}
        </tbody></table>
        <div className="row">
          <input placeholder="new user's name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <input type="password" placeholder="password (10+ characters)" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          {roles.map((r) => <label key={r} title={list.roles[r]}><input type="checkbox" checked={f.roles.includes(r)} onChange={() => setF({ ...f, roles: toggle(f.roles, r) })} /> {r}</label>)}
          <button className="primary" disabled={!f.name.trim() || !f.password || f.roles.length === 0} onClick={() => run(() => api("/users", { method: "POST", json: f }), "User added.").then(() => setF({ name: "", password: "", roles: ["buyer"] }))}>Add user</button>
        </div>
        <ul className="muted" data-testid="role-legend">
          {roles.map((r) => <li key={r}><b>{r}</b>: {list.roles[r]}</li>)}
          <li>A user may do whatever any of their roles allows. Whoever edited a letter, RFQ or quote, or entered an invoice, cannot be the one to approve it.</li>
        </ul>
        <div className="row">
          {!auth.enabled
            ? <button className="primary" onClick={() => confirm("Turn sign-in on? Everyone will have to sign in; make sure you know your password.") && run(() => api("/auth/enabled", { method: "PUT", json: { enabled: true } }), "Sign-in is on.")}>Turn sign-in on</button>
            : <button className="danger" onClick={() => confirm("Turn sign-in off? Anyone who can open the app will be able to use any name.") && run(() => api("/auth/enabled", { method: "PUT", json: { enabled: false } }), "Sign-in is off.")}>Turn sign-in off</button>}
          <span className="muted">If nobody can sign in, start the server with AUTH_FORCE_OFF=true.</span>
        </div>
        <h3>Recent sign-in events</h3>
        <table><tbody>{list.events.slice(0, 15).map((e: any) => (
          <tr key={e.id}><td className="muted">{fmtDate(e.at)}</td><td>{e.who}</td><td>{e.action.replace("auth.", "")}</td><td className="muted">{Object.entries(e.detail ?? {}).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ")}</td></tr>))}</tbody></table>
      </>}
    </section>
  );
}

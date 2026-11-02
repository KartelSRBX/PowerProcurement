"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { usePerson } from "../lib/person";

/** Shown instead of the app when sign-in is on and nobody is signed in. */
export function Login() {
  const { refreshAuth } = usePerson();
  const [f, setF] = useState({ name: "", password: "" });
  const [err, setErr] = useState("");
  async function go() {
    setErr("");
    try { await api("/auth/login", { method: "POST", json: f }); setF({ name: "", password: "" }); await refreshAuth(); window.dispatchEvent(new Event("pp-signed-in")); }
    catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="letter" style={{ maxWidth: "26rem", margin: "4rem auto" }} data-testid="login">
      <h1>Sign in</h1>
      <p className="muted">PowerProcurement. Every action is recorded under the name you sign in with.</p>
      <div className="row"><input placeholder="name" autoComplete="username" style={{ flex: 1 }} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
      <div className="row"><input type="password" placeholder="password" autoComplete="current-password" style={{ flex: 1 }} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} onKeyDown={(e) => e.key === "Enter" && go()} /></div>
      {err && <div className="err">{err}</div>}
      <div className="row"><button className="primary" disabled={!f.name.trim() || !f.password} onClick={go}>Sign in</button></div>
    </div>
  );
}

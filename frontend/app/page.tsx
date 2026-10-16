"use client";

import { useEffect, useState } from "react";
import { api } from "./lib/api";

type Req = { id: number; status: string; sender: string; subject: string };

const DEMO_ITEMS = "500 x STM32F407VGT6 microcontroller\n2000 x 100nF 0603 capacitors";

export default function Home() {
  const [reqs, setReqs] = useState<Req[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [err, setErr] = useState("");
  const [name, setName] = useState("");
  const [f, setF] = useState({ sender: "buyer@customer.example", subject: "RFQ", items: DEMO_ITEMS, category: "electronics", language: "en", needed_by: "" });

  const load = () => api<Req[]>("/requests").then(setReqs).catch((e) => setErr(e.message));
  useEffect(() => {
    setName(localStorage.getItem("pp_name") ?? "");
    load();
    api("/health/ready").then(setHealth).catch(() => setHealth(null));
  }, []);

  async function create() {
    setErr("");
    try {
      const items = f.items.split("\n").filter(Boolean).map((line) => {
        const m = line.match(/^\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(.+)$/i);
        return m ? { description: m[2].trim(), quantity: Number(m[1].replace(",", ".")) } : { description: line.trim(), quantity: null };
      });
      localStorage.setItem("pp_name", name);
      const r = await api("/requests/manual", { method: "POST", json: {
        sender: f.sender, subject: f.subject, body: f.items, confirmed_by: name,
        parsed: { is_request: true, language: f.language, category: f.category, items, needed_by: f.needed_by || null, confidence: 1 },
      } });
      location.href = `/requests/${r.id}`;
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <>
      <h1>Requests</h1>
      <p className="muted">Backend: {health ? `up · AI: ${health.ai_provider} · mail: ${health.mail_mode}` : "unreachable"}</p>
      {err && <div className="err">{err}</div>}
      <section>
        <h2>New request (entered by a person; email parsing needs an AI key)</h2>
        <div className="row"><input placeholder="Your name (required)" value={name} onChange={(e) => setName(e.target.value)} />
          <input value={f.sender} onChange={(e) => setF({ ...f, sender: e.target.value })} />
          <input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></div>
        <textarea value={f.items} onChange={(e) => setF({ ...f, items: e.target.value })} />
        <div className="row">
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option>electronics</option><option>it_hardware</option><option>other</option></select>
          <select value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}><option value="en">Customer language: en</option><option value="sr">Customer language: sr</option></select>
          <label>Needed by <input type="date" value={f.needed_by} onChange={(e) => setF({ ...f, needed_by: e.target.value })} /></label>
          <button className="primary" disabled={!name.trim()} onClick={create}>Create request</button>
        </div>
      </section>
      <section>
        <table>
          <thead><tr><th>#</th><th>Customer</th><th>Subject</th><th>Status</th></tr></thead>
          <tbody>{reqs.map((r) => (
            <tr key={r.id}><td><a href={`/requests/${r.id}`}>{r.id}</a></td><td>{r.sender}</td><td>{r.subject}</td><td><span className="tag">{r.status}</span></td></tr>
          ))}</tbody>
        </table>
        {reqs.length === 0 && <p className="muted">No requests yet.</p>}
      </section>
    </>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

const STATUS: Record<string, [string, string]> = {
  unparsed: ["unparsed", "warn"], needs_review: ["needs review", "warn"], parsed: ["parsed by AI", "acc"],
  confirmed: ["request confirmed", "ok"], not_request: ["not a request", ""], draft: ["draft", "warn"],
  sent: ["sent", "ok"], rejected: ["rejected", "bad"],
};
const KIND: Record<string, string> = { rfq: "supplier RFQ", quote: "customer quote", po: "purchase order", email: "customer email" };

const tag = (s: string) => { const [t, c] = STATUS[s] ?? [s, ""]; return <span className={`tag ${c}`}>{t}</span>; };

// Draft only: pulls "500 pcs X" or "X - 500 pcs" lines out of the text so a person starts from
// something. Not AI; the person checks and edits every line.
const UNIT = "(?:pcs|pc|pieces|kom|ком|комада|шт|x|×)";
function guessItems(body: string): string {
  const out: string[] = [];
  const qty = (n: string) => n.replace(/[.,](?=\d{3}\b)/g, "").replace(",", ".");
  for (const raw of body.split("\n")) {
    const line = raw.replace(/^\s*[-*•]\s*/, "").trim();
    const a = line.match(new RegExp(`^(\\d[\\d.,]*)\\s*${UNIT}\\.?\\s+(.+)$`, "i"));
    const b = line.match(new RegExp(`^(.+?)\\s*(?:[-–:]|\\s${UNIT})\\s*(\\d[\\d.,]*)\\s*${UNIT}\\.?$`, "i"));
    if (a) out.push(`${qty(a[1])} x ${a[2].trim()}`);
    else if (b) out.push(`${qty(b[2])} x ${b[1].trim()}`);
  }
  return out.join("\n");
}

function RequestFromMail({ mail, onDone }: { mail: any; onDone: () => void }) {
  const { person } = usePerson();
  const [items, setItems] = useState(() => guessItems(mail.body));
  const [category, setCategory] = useState("electronics");
  const [language, setLanguage] = useState("en");
  const [neededBy, setNeededBy] = useState("");
  const [err, setErr] = useState("");
  const [ai, setAi] = useState<string>("mock");
  const [parsed, setParsed] = useState<any>(null);
  useEffect(() => { api<any>("/config").then((c) => setAi(c.ai_provider)).catch(() => {}); }, []);
  async function parseWithAi() {
    setErr("");
    try {
      const r = await api<any>("/requests/intake", { method: "POST", json: {
        message_id: mail.message_id, sender: mail.counterparty, subject: mail.subject, body: mail.body, received_at: mail.at,
      } });
      setParsed(r); onDone();
    } catch (e: any) { setErr(e.message); }
  }
  async function create() {
    setErr("");
    try {
      const parsedItems = items.split("\n").filter(Boolean).map((line) => {
        const m = line.match(/^\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*(.+)$/i);
        return m ? { description: m[2].trim(), quantity: Number(m[1].replace(",", ".")) } : { description: line.trim(), quantity: null };
      });
      await api("/requests/manual", { method: "POST", json: {
        sender: mail.counterparty, subject: mail.subject, body: mail.body, message_id: mail.message_id, confirmed_by: person,
        parsed: { is_request: true, language, category, items: parsedItems, needed_by: neededBy || null, confidence: 1 },
      } });
      onDone();
    } catch (e: any) { setErr(e.message); }
  }
  return (
    <div className="letter">
      <b>Create a request from this email</b>
      {ai === "anthropic" ? (
        <div className="row">
          <button className="primary" onClick={parseWithAi} disabled={!!parsed}>Parse with AI</button>
          <span className="muted">Sends this email’s text to the Claude API (billed to your key). A person still confirms the result.</span>
        </div>
      ) : (
        <p className="muted">AI parsing is off. <Link href="/settings">Add your API key in Settings</Link> to turn it on. Until then the item list is drafted by a simple text rule (not AI): check and fix it, one item per line, like “500 x name”.</p>
      )}
      {parsed && (
        <p>AI read this as {parsed.parsed?.is_request === false ? "not a request" : `${parsed.parsed?.items?.length ?? 0} item(s)`}, confidence {Math.round((parsed.confidence ?? 0) * 100)}%.{" "}
          <Link href={`/requests/${parsed.id}`}>Open request #{parsed.id} to review and confirm</Link></p>
      )}
      <textarea value={items} onChange={(e) => setItems(e.target.value)} placeholder="500 x STM32F407VGT6" />
      <div className="row">
        <select value={category} onChange={(e) => setCategory(e.target.value)}><option value="electronics">electronics</option><option value="it_hardware">IT-hardware</option><option value="other">other</option></select>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">customer language: en</option><option value="sr">customer language: sr</option></select>
        <label>needed by <input type="date" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} /></label>
        <button className="primary" disabled={!person.trim() || !items.trim()} onClick={create}>Confirm as request</button>
      </div>
      {!person.trim() && <div className="muted">Enter your name at the top: a person confirms the request.</div>}
      {err && <div className="err">{err}</div>}
    </div>
  );
}

export default function MailPage() {
  const [folder, setFolder] = useState<"all" | "in" | "out">("all");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [all, setAll] = useState<any[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [list, everything] = await Promise.all([api<any[]>(`/mail?folder=${folder}&q=${encodeURIComponent(q)}`), api<any[]>("/mail")]);
      setRows(list); setAll(everything); setErr("");
    } catch (e: any) { setErr(e.message); }
  }, [folder, q]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);

  const counts = useMemo(() => ({ all: all.length, in: all.filter((m) => m.direction === "in").length, out: all.filter((m) => m.direction === "out").length }), [all]);
  const cur = rows.find((m) => m.key === sel) ?? null;

  async function demo() { await api("/mail/demo-load", { method: "POST", json: {} }); load(); }

  return (
    <>
      {err && <div className="err">{err}</div>}
      <div className="split mail">
        <div className="pane"><div className="pane-b">
          {([["all", "All"], ["in", "Inbox"], ["out", "Sent"]] as const).map(([k, l]) => (
            <div key={k} className={`folder ${folder === k ? "active" : ""}`} onClick={() => setFolder(k)}><span>{l}</span><span className="muted">{counts[k]}</span></div>
          ))}
          <div className="muted" style={{ marginTop: "1rem" }}>Outgoing emails are created only after a person approves; in the demo they arrive in Mailpit.</div>
          <button style={{ marginTop: ".8rem", width: "100%" }} onClick={demo}>Load 16 demo emails</button>
        </div></div>

        <div className="pane">
          <div className="pane-h"><input style={{ width: "100%" }} placeholder="Search sender, subject, text" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {rows.map((m) => (
            <div key={m.key} className={`msg ${m.key === sel ? "sel" : ""}`} onClick={() => setSel(m.key)}>
              <div className="s">{m.direction === "out" ? "→ " : ""}{m.subject}</div>
              <div className="f">{m.counterparty}</div>
              <div className="row" style={{ margin: ".2rem 0 0" }}>{tag(m.status)}<span className="muted">{fmtDate(m.at)}</span></div>
            </div>
          ))}
          {rows.length === 0 && <div className="pane-b muted">No emails. Click “Load 16 demo emails” or create a request on the “Requests” tab.</div>}
        </div>

        <div className="pane">
          {!cur && <div className="pane-b muted">Pick an email on the left.</div>}
          {cur && (
            <>
              <div className="pane-h">
                <div style={{ fontWeight: 700 }}>{cur.subject}</div>
                <div className="muted">{cur.direction === "in" ? "From" : "To"}: {cur.counterparty} · {fmtDate(cur.at)}</div>
                <div className="row" style={{ marginBottom: 0 }}><span className="tag acc">{KIND[cur.kind]}</span>{tag(cur.status)}{cur.approved_by && <span className="tag">approved by: {cur.approved_by}</span>}{cur.source && <span className="tag">source: {cur.source}</span>}</div>
              </div>
              <div className="pane-b">
                <pre className="body-text">{cur.body}</pre>
                {cur.direction === "in" && cur.request && (
                  <div className="letter">
                    <b>Request #{cur.request.request_id}</b> · {cur.request.items} items · {cur.request.category} · language {cur.request.language} · confidence {Math.round((cur.request.confidence ?? 0) * 100)}% · {cur.request.model}
                    <div className="row"><Link href={`/requests/${cur.request.request_id}`}><button>Open pipeline</button></Link><Link href={`/articles?request=${cur.request.request_id}`}><button>Match articles</button></Link><Link href={`/quote?request=${cur.request.request_id}`}><button>To the offer</button></Link></div>
                  </div>
                )}
                {cur.direction === "in" && !cur.request && <RequestFromMail key={cur.key} mail={cur} onDone={load} />}
                {cur.direction === "out" && cur.request && <div className="row"><Link href={`/requests/${cur.request.request_id}`}><button>Request #{cur.request.request_id}</button></Link></div>}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

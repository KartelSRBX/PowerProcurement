"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, eur, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

const KIND: Record<string, string> = { rfq: "supplier RFQ", quote: "customer quote", followup: "supplier follow-up", reminder: "customer reminder", confirmation: "order confirmation", delivery: "delivery question" };

export default function Approvals() {
  const { person } = usePerson();
  const who = person.trim();
  const [mode, setMode] = useState<"pending" | "decided">("pending");
  const [kind, setKind] = useState<string>("all");
  const [rows, setRows] = useState<any[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setRows(await api<any[]>(`/approvals?status=${mode}`)); setErr(""); } catch (e: any) { setErr(e.message); }
  }, [mode]);
  useEffect(() => { load(); }, [load]);

  const shown = rows.filter((r) => kind === "all" || r.kind === kind);
  const cur = shown.find((r) => r.key === sel) ?? null;
  useEffect(() => { setText(cur?.body ?? ""); }, [cur?.key]);  // eslint-disable-line react-hooks/exhaustive-deps

  const base = (r: any) => (r.kind === "rfq" ? `/rfqs/${r.id}` : r.kind === "quote" ? `/quotes/${r.id}` : `/letters/${r.id}`);
  async function decide(approve: boolean) {
    if (!cur) return;
    setErr("");
    try {
      if (text !== cur.body) await api(base(cur), { method: "PATCH", json: { body: text } });
      await api(`${base(cur)}/decision`, { method: "POST", json: { approve, decided_by: who } });
      setSel(null);
      await load();
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <>
      <div className="tabs">
        <div className={`tab ${mode === "pending" ? "active" : ""}`} onClick={() => { setMode("pending"); setSel(null); }}>Waiting for approval</div>
        <div className={`tab ${mode === "decided" ? "active" : ""}`} onClick={() => { setMode("decided"); setSel(null); }}>Decided</div>
      </div>
      {err && <div className="err">{err}</div>}
      <div className="split two">
        <div className="pane">
          <div className="pane-h row" style={{ margin: 0 }}>
            {(["all", "rfq", "quote", "followup", "reminder", "confirmation", "delivery"] as const).map((k) => (
              <button key={k} className={kind === k ? "primary" : ""} onClick={() => setKind(k)}>{k === "all" ? "All" : KIND[k]}</button>
            ))}
            <span className="muted">{shown.length} letter(s)</span>
          </div>
          {shown.map((r) => (
            <div key={r.key} className={`msg ${r.key === sel ? "sel" : ""}`} onClick={() => setSel(r.key)}>
              <div className="s">{r.subject}</div>
              <div className="f">{r.counterparty}</div>
              <div className="row" style={{ margin: ".2rem 0 0" }}>
                <span className="tag acc">{KIND[r.kind]}</span>{r.drafted_by?.startsWith("AI") && <span className="tag">{r.drafted_by}</span>}
                {r.warnings.map((w: string) => <span key={w} className="tag bad">{w}</span>)}
                {mode === "decided" && <span className={`tag ${r.status === "sent" ? "ok" : "bad"}`}>{r.status} by {r.decided_by}</span>}
                <span className="muted">{fmtDate(r.at)}</span>
              </div>
            </div>
          ))}
          {shown.length === 0 && <div className="pane-b muted">{mode === "pending" ? "Nothing waits for approval. Letters appear here when a request reaches the drafting steps." : "No decisions yet."}</div>}
        </div>

        <div className="pane">
          {!cur && <div className="pane-b muted">Pick a letter on the left. Nothing leaves the system until you approve it; in the demo approved letters go to Mailpit.</div>}
          {cur && (
            <>
              <div className="pane-h">
                <div style={{ fontWeight: 700 }}>{cur.subject}</div>
                <div className="muted">To: {cur.counterparty} · language {cur.language} · <Link href={`/requests/${cur.request_id}`}>request #{cur.request_id}</Link></div>
                {cur.quote && <div className="row" style={{ marginBottom: 0 }}><span className="tag">price {eur(cur.quote.price)} {cur.quote.currency}</span><span className="tag">cost {eur(cur.quote.cost_eur)} EUR</span><span className="tag">markup {(cur.quote.markup * 100).toFixed(1)}%</span></div>}
                {cur.warnings.map((w: string) => <div key={w} className="err">{w}</div>)}
              </div>
              <div className="pane-b">
                {mode === "pending" ? (
                  <>
                    <textarea style={{ minHeight: "18rem" }} value={text} onChange={(e) => setText(e.target.value)} />
                    <div className="row">
                      <button className="primary" disabled={!who} onClick={() => decide(true)}>Approve and send (to Mailpit)</button>
                      <button disabled={!who} onClick={() => decide(false)}>Reject</button>
                      {text !== cur.body && <span className="muted">your edits are saved with the decision</span>}
                    </div>
                    {!who && <div className="muted">Enter your name at the top: a person approves every letter.</div>}
                  </>
                ) : <pre className="body-text">{cur.body}</pre>}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

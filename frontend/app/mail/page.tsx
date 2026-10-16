"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { usePerson } from "../lib/person";

const STATUS: Record<string, [string, string]> = {
  unparsed: ["не разобрано", "warn"], needs_review: ["нужна проверка", "warn"], parsed: ["разобрано ИИ", "acc"],
  confirmed: ["заявка подтверждена", "ok"], not_request: ["не заявка", ""], draft: ["черновик", "warn"],
  sent: ["отправлено", "ok"], rejected: ["отклонено", "bad"],
};
const KIND: Record<string, string> = { rfq: "запрос поставщику", quote: "КП клиенту", po: "заказ поставщику", email: "письмо клиента" };

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
      <b>Создать заявку из письма</b>
      <p className="muted">Автоматический разбор писем включится с ключом ИИ. Пока список позиций набросан простым правилом (не ИИ): проверьте и поправьте, по одной позиции в строке «500 x название».</p>
      <textarea value={items} onChange={(e) => setItems(e.target.value)} placeholder="500 x STM32F407VGT6" />
      <div className="row">
        <select value={category} onChange={(e) => setCategory(e.target.value)}><option value="electronics">электроника</option><option value="it_hardware">IT-оборудование</option><option value="other">другое</option></select>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">язык клиента: en</option><option value="sr">язык клиента: sr</option></select>
        <label>нужно к <input type="date" value={neededBy} onChange={(e) => setNeededBy(e.target.value)} /></label>
        <button className="primary" disabled={!person.trim() || !items.trim()} onClick={create}>Подтвердить как заявку</button>
      </div>
      {!person.trim() && <div className="muted">Введите своё имя вверху: заявку подтверждает человек.</div>}
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
          {([["all", "Все"], ["in", "Входящие"], ["out", "Исходящие"]] as const).map(([k, l]) => (
            <div key={k} className={`folder ${folder === k ? "active" : ""}`} onClick={() => setFolder(k)}><span>{l}</span><span className="muted">{counts[k]}</span></div>
          ))}
          <div className="muted" style={{ marginTop: "1rem" }}>Исходящие письма создаются только после одобрения человека; в демо они приходят в Mailpit.</div>
          <button style={{ marginTop: ".8rem", width: "100%" }} onClick={demo}>Загрузить 16 демо-писем</button>
        </div></div>

        <div className="pane">
          <div className="pane-h"><input style={{ width: "100%" }} placeholder="Поиск по отправителю, теме, тексту" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {rows.map((m) => (
            <div key={m.key} className={`msg ${m.key === sel ? "sel" : ""}`} onClick={() => setSel(m.key)}>
              <div className="s">{m.direction === "out" ? "→ " : ""}{m.subject}</div>
              <div className="f">{m.counterparty}</div>
              <div className="row" style={{ margin: ".2rem 0 0" }}>{tag(m.status)}<span className="muted">{fmtDate(m.at)}</span></div>
            </div>
          ))}
          {rows.length === 0 && <div className="pane-b muted">Писем нет. Нажмите «Загрузить 16 демо-писем» или создайте заявку на вкладке «Заявки».</div>}
        </div>

        <div className="pane">
          {!cur && <div className="pane-b muted">Выберите письмо слева.</div>}
          {cur && (
            <>
              <div className="pane-h">
                <div style={{ fontWeight: 700 }}>{cur.subject}</div>
                <div className="muted">{cur.direction === "in" ? "От" : "Кому"}: {cur.counterparty} · {fmtDate(cur.at)}</div>
                <div className="row" style={{ marginBottom: 0 }}><span className="tag acc">{KIND[cur.kind]}</span>{tag(cur.status)}{cur.approved_by && <span className="tag">одобрил: {cur.approved_by}</span>}{cur.source && <span className="tag">источник: {cur.source}</span>}</div>
              </div>
              <div className="pane-b">
                <pre className="body-text">{cur.body}</pre>
                {cur.direction === "in" && cur.request && (
                  <div className="letter">
                    <b>Заявка #{cur.request.request_id}</b> · {cur.request.items} поз. · {cur.request.category} · язык {cur.request.language} · уверенность {Math.round((cur.request.confidence ?? 0) * 100)}% · {cur.request.model}
                    <div className="row"><Link href={`/requests/${cur.request.request_id}`}><button>Открыть конвейер</button></Link><Link href={`/articles?request=${cur.request.request_id}`}><button>Подобрать артикулы</button></Link><Link href={`/quote?request=${cur.request.request_id}`}><button>К предложению</button></Link></div>
                  </div>
                )}
                {cur.direction === "in" && !cur.request && <RequestFromMail key={cur.key} mail={cur} onDone={load} />}
                {cur.direction === "out" && cur.request && <div className="row"><Link href={`/requests/${cur.request.request_id}`}><button>Заявка #{cur.request.request_id}</button></Link></div>}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

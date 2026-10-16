"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, eur } from "../lib/api";

function Lines({ g, qty }: { g: any; qty?: number | null }) {
  const best = g.lines.find((l: any) => !l.sanctioned && !l.expired);
  return (
    <table>
      <thead><tr><th>Поставщик</th><th>Цена</th><th>≈ EUR / шт</th><th>MOQ</th><th>Срок, дн.</th>{qty != null && <th>Сумма, EUR</th>}<th></th></tr></thead>
      <tbody>{g.lines.map((l: any) => (
        <tr key={l.supplier_id} style={l.sanctioned || l.expired ? { opacity: 0.55 } : undefined}>
          <td>{l.supplier} ({l.country})</td><td className="num">{l.unit_price} {l.currency}</td>
          <td className={`num ${best && l.supplier_id === best.supplier_id ? "best" : ""}`}>{eur(l.price_eur)}</td>
          <td className="num">{l.moq}</td><td className="num">{l.lead_time_days}</td>
          {qty != null && <td className="num">{eur(l.line_total_eur)}</td>}
          <td>{l.sanctioned && <span className="tag bad">санкции</span>} {l.expired && <span className="tag bad">прайс просрочен</span>} {qty != null && !l.moq_ok && <span className="tag warn">заказ меньше MOQ</span>} {best && l.supplier_id === best.supplier_id && <span className="tag ok">лучшая цена</span>}</td>
        </tr>))}</tbody>
    </table>
  );
}

function Group({ g, qty }: { g: any; qty?: number | null }) {
  return (
    <section>
      <h2>{g.description} <span className="tag">{g.keyword}</span></h2>
      <div className="row"><span className="tag acc">поставщиков: {g.suppliers}</span>
        {g.min_eur != null && <span className="tag">мин {eur(g.min_eur)}</span>}{g.median_eur != null && <span className="tag">медиана {eur(g.median_eur)}</span>}{g.max_eur != null && <span className="tag">макс {eur(g.max_eur)}</span>}
        <span className="muted">EUR за штуку по демо-курсу, прайсы синтетические и не подтверждены</span></div>
      <Lines g={g} qty={qty} />
    </section>
  );
}

function Inner() {
  const params = useSearchParams();
  const [mode, setMode] = useState<"catalog" | "request">(params.get("request") ? "request" : "catalog");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  const [reqs, setReqs] = useState<any[]>([]);
  const [rid, setRid] = useState(params.get("request") ?? "");
  const [matches, setMatches] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => { const t = setTimeout(() => api(`/articles/search?q=${encodeURIComponent(q)}`).then(setHits).catch((e) => setErr(e.message)), 200); return () => clearTimeout(t); }, [q]);
  useEffect(() => { api<any[]>("/requests").then(setReqs).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { if (rid) api(`/requests/${rid}/articles`).then((m) => { setMatches(m); setErr(""); }).catch((e) => setErr(e.message)); else setMatches([]); }, [rid]);

  return (
    <>
      <div className="tabs">
        <div className={`tab ${mode === "catalog" ? "active" : ""}`} onClick={() => setMode("catalog")}>Поиск по каталогу</div>
        <div className={`tab ${mode === "request" ? "active" : ""}`} onClick={() => setMode("request")}>Позиции заявки</div>
      </div>
      {err && <div className="err">{err}</div>}
      {mode === "catalog" && (
        <>
          <div className="row"><input autoFocus style={{ width: "24rem", maxWidth: "100%" }} placeholder="Артикул, название или поставщик: stm32, 0603, ..." value={q} onChange={(e) => setQ(e.target.value)} /><span className="muted">найдено артикулов: {hits.length}</span></div>
          {hits.map((g) => <Group key={g.keyword} g={g} />)}
          {hits.length === 0 && <p className="muted">Ничего не найдено. Добавьте строку прайса на вкладке «Поставщики».</p>}
        </>
      )}
      {mode === "request" && (
        <>
          <div className="row"><select value={rid} onChange={(e) => setRid(e.target.value)}><option value="">выберите заявку</option>
            {reqs.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.sender} · {r.subject}</option>)}</select>
            {rid && <Link href={`/requests/${rid}`}>конвейер заявки</Link>}</div>
          <p className="muted">Подбор идёт по правилу: ключ из прайса должен встретиться в описании или номере детали позиции. Это не ИИ, поэтому пустой результат значит «в прайсах нет ключа», а не «такого товара не существует».</p>
          {matches.map((it) => (
            <div key={it.item_id}>
              <h2 style={{ margin: "1rem 0 .2rem" }}>{it.quantity ?? "?"} × {it.description} {it.part_number && <span className="tag">{it.part_number}</span>}</h2>
              {it.matches.length === 0 && <section><span className="tag bad">артикул не найден</span> <span className="muted">Добавьте его в прайс поставщика (вкладка «Поставщики») или запросите предложение вручную.</span></section>}
              {it.matches.map((g: any) => <Group key={g.keyword} g={g} qty={it.quantity} />)}
            </div>))}
        </>
      )}
    </>
  );
}

export default function Articles() {
  return <Suspense fallback={<p>Загрузка...</p>}><Inner /></Suspense>;
}

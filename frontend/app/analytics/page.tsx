"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

const LABELS: Record<string, string> = {
  confirmed: "подтверждена человеком", needs_review: "нужна проверка", parsed: "разобрана ИИ", not_request: "не заявка",
  electronics: "электроника", it_hardware: "IT-оборудование", other: "другое", sr: "сербский", en: "английский",
  accepted: "согласие", rejected: "отказ", counter: "встречное предложение", silence: "молчание",
};

function Bars({ data, max }: { data: [string, number][]; max?: number }) {
  const m = max ?? Math.max(1, ...data.map(([, v]) => v));
  if (data.length === 0) return <div className="muted">Пока нет данных.</div>;
  return <>{data.map(([k, v]) => (
    <div className="bar" key={k}><span>{LABELS[k] ?? k}</span><div className="track"><div className="fill" style={{ width: `${(100 * v) / m}%` }} /></div><span className="num">{v}</span></div>
  ))}</>;
}

function Volume({ data }: { data: { day: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const w = 600, h = 110, bw = w / data.length;
  return (
    <svg viewBox={`0 0 ${w} ${h + 24}`} width="100%" role="img" aria-label="Входящие письма по дням">
      {data.map((d, i) => {
        const bh = (d.count / max) * h;
        return <g key={d.day}><rect x={i * bw + 1} y={h - bh} width={bw - 2} height={bh} rx={2} fill="var(--accent)" opacity={d.count ? 0.9 : 0.15}><title>{d.day}: {d.count}</title></rect></g>;
      })}
      <text x="0" y={h + 20} fontSize="16" fill="var(--muted)">{data[0]?.day}</text>
      <text x={w} y={h + 20} fontSize="16" fill="var(--muted)" textAnchor="end">{data.at(-1)?.day}</text>
    </svg>
  );
}

export default function Analytics() {
  const [a, setA] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  useEffect(() => { api(`/analytics/messages?days=${days}`).then(setA).catch((e) => setErr(e.message)); }, [days]);
  if (!a) return <p>{err || "Загрузка..."}</p>;
  const t = a.totals;
  const kpis: [string, string | number][] = [
    ["входящих писем", t.inbound], ["не разобрано", t.unparsed], ["заявок", t.requests],
    ["отправлено исходящих", t.outbound_sent], ["черновиков ждут одобрения", t.outbound_drafts],
    ["средняя уверенность ИИ", a.avg_confidence == null ? "—" : `${Math.round(a.avg_confidence * 100)}%`],
  ];
  const top = a.funnel[0].count || 1;
  return (
    <>
      <div className="kpis">{kpis.map(([l, v]) => <div className="kpi" key={l}><div className="v">{v}</div><div className="l">{l}</div></div>)}</div>
      <div className="grid2">
        <section>
          <h2>Входящие письма по дням <select style={{ float: "right" }} value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={14}>14 дней</option><option value={30}>30 дней</option><option value={90}>90 дней</option></select></h2>
          <Volume data={a.volume} />
        </section>
        <section>
          <h2>Воронка: от письма до заказа</h2>
          {a.funnel.map((f: any) => (
            <div className="bar" key={f.stage}><span>{f.stage}</span><div className="track"><div className="fill" style={{ width: `${(100 * f.count) / top}%` }} /></div><span className="num">{f.count}</span></div>
          ))}
          <p className="muted">Считается по записям в базе; шаг «подтверждено человеком» обязателен перед любым исходящим письмом.</p>
        </section>
        <section><h2>Статусы заявок</h2><Bars data={Object.entries(a.by_status)} /></section>
        <section><h2>Языки писем</h2><Bars data={Object.entries(a.by_language)} /><h2 style={{ marginTop: "1rem" }}>Категории</h2><Bars data={Object.entries(a.by_category)} /></section>
        <section><h2>Кто пишет чаще всего</h2><Bars data={a.top_senders.map((s: any) => [s.sender, s.count])} /></section>
        <section>
          <h2>Запросы поставщикам</h2>
          <table><tbody>
            <tr><td>Отправлено запросов</td><td className="num">{a.rfq.sent}</td></tr>
            <tr><td>Получено ответов (предложений)</td><td className="num">{a.rfq.answered}</td></tr>
            <tr><td>из них сымитировано демо-симулятором</td><td className="num">{a.rfq.demo_simulated}</td></tr>
          </tbody></table>
          <h2 style={{ marginTop: "1rem" }}>Ответы клиентов на КП</h2>
          <Bars data={Object.entries(a.outcomes)} />
        </section>
        <section><h2>Позиций в заявке</h2><Bars data={Object.entries(a.items_per_request).map(([k, v]) => [`${k} поз.`, v as number])} /></section>
      </div>
    </>
  );
}

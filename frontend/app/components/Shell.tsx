"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { PersonProvider, usePerson } from "../lib/person";

const NAV = [
  { href: "/", ico: "☰", label: "Заявки" },
  { href: "/mail", ico: "✉", label: "Почта" },
  { href: "/analytics", ico: "▥", label: "Аналитика писем" },
  { href: "/suppliers", ico: "⌂", label: "Поставщики" },
  { href: "/articles", ico: "⌕", label: "Подбор артикулов" },
  { href: "/quote", ico: "€", label: "Предложение" },
];

function Top({ title }: { title: string }) {
  const { person, setPerson } = usePerson();
  const [health, setHealth] = useState<any>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    api("/health/ready").then((h) => { setHealth(h); setDown(false); }).catch(() => setDown(true));
  }, []);
  return (
    <header className="hud-top">
      <span className="title">{title}</span>
      <span className={`chip ${down ? "bad" : "ok"}`}>{down ? "сервер недоступен" : "сервер на связи"}</span>
      {health && <span className={`chip ${health.ai_provider === "mock" ? "warn" : "ok"}`}>ИИ: {health.ai_provider === "mock" ? "выключен (mock)" : health.ai_provider}</span>}
      {health && <span className="chip warn">почта: {health.mail_mode}</span>}
      <a className="chip" href="http://localhost:8025" target="_blank" rel="noreferrer">Mailpit ↗</a>
      <label className="person">Работает:
        <input placeholder="ваше имя (нужно для одобрений)" value={person} onChange={(e) => setPerson(e.target.value)} />
      </label>
    </header>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/requests") : path.startsWith(href));
  const current = NAV.find((n) => active(n.href));
  const narrow = path === "/" || path.startsWith("/requests");
  return (
    <PersonProvider>
      <div className="hud">
        <nav className="hud-side">
          <div className="brand">POWER<b>PROCUREMENT</b></div>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`nav-item ${active(n.href) ? "active" : ""}`}>
              <span className="nav-ico">{n.ico}</span>{n.label}
            </Link>
          ))}
          <div className="side-foot">Демо: синтетические данные, письма уходят только в Mailpit. Любое исходящее письмо отправляется после одобрения человека.</div>
        </nav>
        <Top title={current?.label ?? "PowerProcurement"} />
        <main className={`hud-main ${narrow ? "narrow" : ""}`}>{children}</main>
      </div>
    </PersonProvider>
  );
}

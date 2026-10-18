"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { PersonProvider, usePerson } from "../lib/person";

const NAV = [
  { href: "/", ico: "☰", label: "Requests" },
  { href: "/mail", ico: "✉", label: "Mail" },
  { href: "/approvals", ico: "✓", label: "Approvals" },
  { href: "/analytics", ico: "▥", label: "Message analytics" },
  { href: "/pricing", ico: "%", label: "Pricing analytics" },
  { href: "/suppliers", ico: "⌂", label: "Suppliers" },
  { href: "/articles", ico: "⌕", label: "Article matching" },
  { href: "/quote", ico: "€", label: "Offer" },
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
      <span className={`chip ${down ? "bad" : "ok"}`}>{down ? "server unreachable" : "server online"}</span>
      {health && <span className={`chip ${health.ai_provider === "mock" ? "warn" : "ok"}`}>AI: {health.ai_provider === "mock" ? "off (mock)" : health.ai_provider}</span>}
      {health && <span className="chip warn">mail: {health.mail_mode}</span>}
      <a className="chip" href="http://localhost:8025" target="_blank" rel="noreferrer">Mailpit ↗</a>
      <label className="person">Working as:
        <input placeholder="your name (needed for approvals)" value={person} onChange={(e) => setPerson(e.target.value)} />
      </label>
    </header>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [waiting, setWaiting] = useState(0);
  useEffect(() => {
    api<any[]>("/approvals").then((a) => setWaiting(a.length)).catch(() => setWaiting(0));
  }, [path]);
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
              {n.href === "/approvals" && waiting > 0 && <span className="chip warn" style={{ marginLeft: "auto" }}>{waiting}</span>}
            </Link>
          ))}
          <div className="side-foot">Demo: synthetic data, email goes only to Mailpit. Every outgoing email is sent only after a person approves it.</div>
        </nav>
        <Top title={current?.label ?? "PowerProcurement"} />
        <main className={`hud-main ${narrow ? "narrow" : ""}`}>{children}</main>
      </div>
    </PersonProvider>
  );
}

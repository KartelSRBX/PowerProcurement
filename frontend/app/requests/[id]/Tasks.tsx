"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../../lib/api";

const TAG: Record<string, string> = { todo: "", doing: "acc", review: "warn", done: "ok", paused: "bad" };
const PROVIDER: Record<string, string> = { off: "off", bitrix: "Bitrix24 API", demo: "demo (no portal)", excel: "Excel file" };
const STATES = ["todo", "doing", "review", "done", "paused"];

type Props = { id: string; who: string; stage: string; act: (fn: () => Promise<unknown>) => Promise<void>; post: (p: string, j?: unknown) => Promise<any> };

/** The request's work plan as tasks in Bitrix24 (or the demo / Excel mode), with progress read back from there. */
export function TasksPanel({ id, who, stage, act, post }: Props) {
  const [tree, setTree] = useState<any>(null);
  const [plan, setPlan] = useState<any[]>([]);
  const [cfg, setCfg] = useState<any>(null);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [t, p, c] = await Promise.all([api<any>(`/requests/${id}/tasks`), api<any[]>(`/requests/${id}/tasks/plan`), api<any>("/tasks/config")]);
    setTree(t); setPlan(p); setCfg(c.config);
  }, [id]);
  useEffect(() => { load().catch(() => {}); }, [load, stage]);

  const run = (fn: () => Promise<unknown>) => act(async () => { setMsg(""); await fn(); await load(); });
  if (!tree || !cfg) return null;
  const provider = cfg.provider;
  const roleLabel = (key?: string) => (key && cfg.roles[key]?.label) || key || "";
  const missing = plan.filter((p) => !p.exists).length;

  const row = (t: any, depth: number): any => (
    <div key={t.id}>
      <div className="row" style={{ marginLeft: depth * 22, borderLeft: depth ? "2px solid var(--line)" : "none", paddingLeft: depth ? 8 : 0 }}>
        <b>{t.url ? <a href={t.url} target="_blank" rel="noreferrer">{t.title}</a> : t.title}</b>
        <span className={`tag ${TAG[t.state]}`}>{t.state}</span>
        {t.external_id && <span className="tag">#{t.external_id}</span>}
        {t.late && <span className="tag bad">late</span>}
        {t.missing && <span className="tag bad">gone from the portal</span>}
        {t.drift === "behind" && <span className="tag warn" title="The request is past this step but the task is still open">task is behind</span>}
        {t.drift === "ahead" && <span className="tag warn" title="The task is closed but the app does not show this step done yet">task is ahead</span>}
        <select value={t.state} disabled={!who} onChange={(e) => run(() => post(`/tasks/${t.id}/state`, { state: e.target.value, by: who }))}>
          {STATES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </div>
      <div className="bar" style={{ marginLeft: depth * 22 + 8, gridTemplateColumns: "minmax(12rem, 26rem) 1fr 2.5rem" }}>
        <span className="muted">{roleLabel(t.role)}{t.responsible_id ? ` · user ${t.responsible_id}` : ""}{t.deadline ? ` · due ${fmtDate(t.deadline)}` : ""}</span>
        <div className="track"><div className="fill" style={{ width: `${t.progress}%` }} /></div><span>{t.progress}%</span>
      </div>
      {t.events.length > 0 && <details style={{ marginLeft: depth * 22 + 8 }}><summary className="muted">history ({t.events.length})</summary>
        {t.events.map((e: any, i: number) => <div key={i} className="muted">{fmtDate(e.at)} · {e.kind}: {e.old ?? "–"} → {e.new ?? "–"} ({e.source}{e.actor ? `, ${e.actor}` : ""})</div>)}
      </details>}
      {t.children.map((c: any) => row(c, depth + 1))}
    </div>
  );

  return (
    <section><h2>Tasks in {PROVIDER[provider]}</h2>
      {provider === "off" && <p className="muted">Tasks are switched off. Choose Bitrix24, Excel or the demo on the <Link href="/tasks">Tasks page</Link>.</p>}
      {provider !== "off" && <>
        {provider === "demo" && <p className="muted">Demo mode: the “portal” is simulated inside this app. Nothing is sent to Bitrix24.</p>}
        <div className="row">
          {tree.count === 0
            ? <button className="primary" disabled={!who || !plan.length} onClick={() => run(async () => { const r = await post(`/requests/${id}/tasks`, { by: who }); setMsg(`${r.created.length} tasks created.${r.warnings.length ? " " + r.warnings.join("; ") : ""}`); })}>Create {plan.length} tasks</button>
            : missing > 0 && <button disabled={!who} onClick={() => run(async () => { const r = await post(`/requests/${id}/tasks`, { by: who }); setMsg(`${r.created.length} tasks created.`); })}>Create the {missing} missing</button>}
          {tree.count > 0 && provider !== "excel" && <button onClick={() => run(async () => { const r = await post(`/requests/${id}/tasks/sync`); setMsg(`Checked ${r.checked}, changed ${r.changed}.${r.unmapped_statuses.length ? ` Unknown statuses: ${r.unmapped_statuses.join(", ")} (add them under Statuses).` : ""}${r.missing.length ? ` Missing in the portal: ${r.missing.join(", ")}.` : ""}`); })}>Read statuses now</button>}
          {tree.count > 0 && provider === "demo" && <button onClick={() => run(async () => { await post(`/requests/${id}/tasks/demo-advance`); await post(`/requests/${id}/tasks/sync`); })}>Demo: a colleague moves work forward</button>}
          {tree.count > 0 && <a href={`/api/requests/${id}/tasks/export.xlsx`}><button>Export to Excel</button></a>}
          <Link href="/tasks" className="muted">settings</Link>
          {!who && <span className="muted">Enter your name at the top to create or change tasks.</span>}
        </div>
        {msg && <div className="ok-note">{msg}</div>}
        {tree.count === 0 && plan.length > 0 && <>
          <p className="muted">These tasks will be created, parents first. Nothing is created until you press the button.</p>
          <table><thead><tr><th>Task</th><th>Parent</th><th>Who</th><th>Due</th></tr></thead><tbody>
            {plan.map((p) => <tr key={p.key}><td>{p.title}</td><td>{p.parent ?? "–"}</td><td>{roleLabel(p.role)}{p.responsible_id ? ` (user ${p.responsible_id})` : provider === "bitrix" ? " – nobody set" : ""}</td><td>{p.deadline ? fmtDate(p.deadline) : "–"}</td></tr>)}
          </tbody></table></>}
        {tree.count > 0 && <>
          <div className="bar"><span><b>Overall progress</b></span><div className="track"><div className="fill" style={{ width: `${tree.progress}%` }} /></div><span>{tree.progress}%</span></div>
          {tree.tasks.map((t: any) => row(t, 0))}
        </>}
      </>}
    </section>
  );
}

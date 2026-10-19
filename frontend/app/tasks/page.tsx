"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { usePerson } from "../lib/person";

const PROVIDERS: [string, string][] = [["off", "Off"], ["bitrix", "Bitrix24 (API)"], ["excel", "Excel file only"], ["demo", "Demo (simulated portal)"]];

function toBase64(f: File) {
  return new Promise<string>((ok, no) => {
    const fr = new FileReader();
    fr.onload = () => ok(String(fr.result).split(",")[1] ?? "");
    fr.onerror = () => no(new Error("the file could not be read in the browser"));
    fr.readAsDataURL(f);
  });
}

/** A pair list ("remote code" -> our state) edited as rows. */
function MapEditor({ value, onChange, options, left, right }: { value: Record<string, string>; onChange: (v: Record<string, string>) => void; options?: string[]; left: string; right: string }) {
  const rows = Object.entries(value);
  return (
    <table><thead><tr><th>{left}</th><th>{right}</th><th /></tr></thead><tbody>
      {rows.map(([k, v], i) => <tr key={i}>
        <td><input value={k} onChange={(e) => onChange(Object.fromEntries(rows.map(([a, b], j) => (j === i ? [e.target.value, b] : [a, b]))))} /></td>
        <td>{options
          ? <select value={v} onChange={(e) => onChange({ ...value, [k]: e.target.value })}>{options.map((o) => <option key={o}>{o}</option>)}</select>
          : <input value={v} onChange={(e) => onChange({ ...value, [k]: e.target.value })} />}</td>
        <td><button onClick={() => { const n = { ...value }; delete n[k]; onChange(n); }}>remove</button></td>
      </tr>)}
      <tr><td colSpan={3}><button onClick={() => onChange({ ...value, "": options?.[0] ?? "" })}>add row</button></td></tr>
    </tbody></table>
  );
}

export default function TasksPage() {
  const { person } = usePerson();
  const [d, setD] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [over, setOver] = useState<any>(null);
  const [dir, setDir] = useState<any>(null);
  const [hook, setHook] = useState("");
  const [json, setJson] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const named = person.trim().length > 0;

  const load = useCallback(async () => {
    try {
      const s = await api<any>("/tasks/config");
      setD(s); setCfg(s.config); setJson(JSON.stringify(s.config, null, 2));
      setOver(await api<any>("/tasks"));
      setErr("");
    } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function run(fn: () => Promise<void>) {
    setErr(""); setNote(null);
    try { await fn(); } catch (e: any) { setErr(e.message); }
  }
  const upd = (fn: (c: any) => void) => setCfg((c: any) => { const n = structuredClone(c); fn(n); return n; });
  const save = (doc = cfg) => run(async () => {
    for (const m of ["status_map", "stage_map", "custom_fields"]) if (doc[m]) doc = { ...doc, [m]: Object.fromEntries(Object.entries<string>(doc[m]).filter(([k, v]) => k.trim() && v.trim())) };
    const s = await api<any>("/tasks/config", { method: "PUT", json: { changed_by: person, config: doc } });
    setD(s); setCfg(s.config); setJson(JSON.stringify(s.config, null, 2));
    setOver(await api<any>("/tasks")); setNote({ ok: true, text: "Saved." });
  });
  const saveHook = (clear = false) => run(async () => {
    const s = await api<any>("/tasks/webhook", { method: "PUT", json: { changed_by: person, url: clear ? null : hook } });
    setD(s); setHook(""); setNote({ ok: true, text: clear ? "Webhook address removed." : "Webhook address saved (stored encrypted)." });
  });
  const test = () => run(async () => { const r = await api<any>("/tasks/test", { method: "POST", json: {} }); setNote({ ok: r.ok, text: r.detail }); });
  const loadDir = () => run(async () => { const r = await api<any>("/tasks/directory"); setDir(r); setNote({ ok: true, text: `Loaded ${r.users.length} people, ${r.groups.length} groups, ${r.stages.length} kanban stages.` }); });
  const syncAll = () => run(async () => {
    const r = await api<any>("/tasks/sync", { method: "POST", json: {} });
    setNote({ ok: true, text: `Checked ${r.checked}, changed ${r.changed}.${r.unmapped_statuses.length ? ` Unknown statuses: ${r.unmapped_statuses.join(", ")}.` : ""}` });
    setOver(await api<any>("/tasks"));
  });
  const importFile = (f: File) => run(async () => {
    const r = await api<any>("/tasks/import", { method: "POST", json: { filename: f.name, content_base64: await toBase64(f), by: person } });
    setNote({ ok: true, text: `Updated ${r.updated}, unchanged ${r.unchanged}, not found ${r.not_found}.${r.unknown_statuses.length ? ` Status words not understood: ${r.unknown_statuses.join(", ")}.` : ""}` });
    setOver(await api<any>("/tasks"));
  });

  if (!d || !cfg) return <p>{err || "Loading..."}</p>;
  const users: any[] = dir?.users ?? [];
  const unsaved = cfg.provider !== d.config.provider;
  const userPick = (value: string | null, onChange: (v: string) => void) => users.length
    ? <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}><option value="">(none)</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name} · {u.id}</option>)}</select>
    : <input style={{ width: "7rem" }} placeholder="user id" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;

  return (
    <>
      <h1>Tasks <span className="tag">{PROVIDERS.find((p) => p[0] === cfg.provider)?.[1]}</span></h1>
      <p className="muted">Turns each request into a task with subtasks in Bitrix24, reads their statuses back and shows progress. Everything that differs between companies is set here, not in code.</p>
      {err && <div className="err">{err}</div>}
      {note && <div className={note.ok ? "ok-note" : "err"}>{note.text}</div>}
      {!named && <div className="muted">Enter your name at the top: every change here is recorded with it.</div>}

      <section><h2>Progress</h2>
        <div className="row">
          <button onClick={syncAll} disabled={cfg.provider === "off" || cfg.provider === "excel"}>Read statuses of all tasks now</button>
          <a href="/api/tasks/export.xlsx"><button>Export all tasks to Excel</button></a>
          <label className="row muted">Import statuses from Excel
            <input type="file" accept=".xlsx,.xlsm" disabled={!named} onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); e.target.value = ""; }} /></label>
        </div>
        <p className="muted">Import reads our own export, a file you edited, or Bitrix24’s “Export to Excel”. Rows are matched by the task number, or by request and key.</p>
        {over && (over.requests.length === 0 ? <p className="muted">No tasks yet. Open a confirmed request and create its tasks.</p>
          : over.requests.map((r: any) => <div className="bar" key={r.request_id}>
            <span><Link href={`/requests/${r.request_id}`}>{r.ref}</Link> {r.subject}</span>
            <div className="track"><div className="fill" style={{ width: `${r.progress}%` }} /></div><span>{r.progress}%</span></div>))}
      </section>

      <section><h2>1 · Connection</h2>
        <div className="row">
          {PROVIDERS.map(([k, label]) => <label key={k} className="row"><input type="radio" checked={cfg.provider === k} onChange={() => upd((c) => { c.provider = k; })} />{label}</label>)}
        </div>
        {cfg.provider === "bitrix" && <div className="letter">
          <div className="row"><b>Incoming webhook</b>{d.webhook.set ? <span className="tag ok">set {d.webhook.hint}</span> : <span className="tag warn">not set</span>}</div>
          <p className="muted">In Bitrix24: Developer resources → Other → Incoming webhook. Give it the “Tasks” and “Users” permissions (and “Workgroups” if you use groups), then paste the address here. It is stored encrypted and never shown again.</p>
          <div className="row">
            <input style={{ flex: 1, minWidth: "20rem" }} placeholder="https://your-company.bitrix24.com/rest/1/xxxxxxxx/" value={hook} onChange={(e) => setHook(e.target.value)} />
            <button className="primary" disabled={!named || !hook.trim()} onClick={() => saveHook()}>Save address</button>
            {d.webhook.set && <button className="danger" disabled={!named} onClick={() => saveHook(true)}>Remove</button>}
          </div>
        </div>}
        <div className="row">
          <button onClick={test} disabled={unsaved || cfg.provider === "off"}>Test the connection</button>
          <button onClick={loadDir} disabled={unsaved || cfg.provider === "off"}>Load people, groups and stages from the portal</button>
          {unsaved && cfg.provider !== "off" && <span className="muted">Save the settings first: these buttons use the saved connection.</span>}
        </div>
        <div className="grid2">
          <label>Workgroup / project id<br /><input value={cfg.group_id ?? ""} onChange={(e) => upd((c) => { c.group_id = e.target.value || null; })} list="groups" />
            <datalist id="groups">{(dir?.groups ?? []).map((g: any) => <option key={g.id} value={g.id}>{g.name}</option>)}</datalist></label>
          <label>Flow id (optional)<br /><input value={cfg.flow_id ?? ""} onChange={(e) => upd((c) => { c.flow_id = e.target.value || null; })} /></label>
          <label>Task author (empty: the webhook’s owner)<br />{userPick(cfg.creator_user_id, (v) => upd((c) => { c.creator_user_id = v || null; }))}</label>
          <label>Responsible when a step has no role<br />{userPick(cfg.default_responsible, (v) => upd((c) => { c.default_responsible = v || null; }))}</label>
        </div>
      </section>

      <section><h2>2 · People and roles</h2>
        <p className="muted">A step names a role; the role names a person in your portal. Change the person here and every later task follows.</p>
        <table><thead><tr><th>Role key</th><th>Label</th><th>Person</th><th /></tr></thead><tbody>
          {Object.entries<any>(cfg.roles).map(([k, r]) => <tr key={k}>
            <td><code>{k}</code></td>
            <td><input value={r.label} onChange={(e) => upd((c) => { c.roles[k].label = e.target.value; })} /></td>
            <td>{userPick(r.user_id, (v) => upd((c) => { c.roles[k].user_id = v || null; }))}</td>
            <td><button onClick={() => upd((c) => { delete c.roles[k]; })}>remove</button></td></tr>)}
          <tr><td colSpan={4}><button onClick={() => { const k = prompt("Role key (letters, digits, _)"); if (k && /^[a-z0-9_]+$/.test(k)) upd((c) => { c.roles[k] = { label: k, user_id: null }; }); }}>add role</button></td></tr>
        </tbody></table>
      </section>

      <section><h2>3 · What the statuses mean in your portal</h2>
        <p className="muted">Bitrix24 status codes: 1 new, 2 pending, 3 in progress, 4 waiting for review, 5 completed, 6 deferred. Companies often add kanban stages: map those too, a stage wins over the code. Unknown codes are shown after a sync so you can add them here.</p>
        <div className="grid2">
          <div><b>Status code → our state</b><MapEditor value={cfg.status_map} onChange={(v) => upd((c) => { c.status_map = v; })} options={d.states} left="code" right="state" /></div>
          <div><b>Kanban stage id → our state</b><MapEditor value={cfg.stage_map} onChange={(v) => upd((c) => { c.stage_map = v; })} options={d.states} left="stage id" right="state" />
            {(dir?.stages ?? []).length > 0 && <p className="muted">Stages in the portal: {dir.stages.map((s: any) => `${s.name} = ${s.id}`).join(", ")}</p>}</div>
          <div><b>Our state → Bitrix24 action</b>
            {d.states.map((st: string) => <div className="row" key={st}><span style={{ width: "5rem" }}>{st}</span>
              <select value={cfg.status_actions[st] ?? ""} onChange={(e) => upd((c) => { if (e.target.value) c.status_actions[st] = e.target.value; else delete c.status_actions[st]; })}>
                <option value="">(not possible)</option>{["tasks.task.renew", "tasks.task.start", "tasks.task.complete", "tasks.task.pause", "tasks.task.defer"].map((m) => <option key={m}>{m}</option>)}</select></div>)}</div>
          <div><b>Progress per state, %</b>
            {d.states.map((s: string) => <div className="row" key={s}><span style={{ width: "5rem" }}>{s}</span><input type="number" min={0} max={100} style={{ width: "5rem" }} value={cfg.state_weights[s] ?? 0} onChange={(e) => upd((c) => { c.state_weights[s] = Number(e.target.value); })} /></div>)}</div>
        </div>
      </section>

      <section><h2>4 · Steps that become tasks</h2>
        <p className="muted">Title and description can use <code>$ref</code> <code>$subject</code> <code>$customer</code> <code>$items</code> <code>$needed_by</code>. A step with a parent becomes a subtask. “Done after” is the request stage at which the step should be finished: the app warns when a task disagrees.</p>
        {cfg.templates.map((t: any, i: number) => <div className="letter" key={i}>
          <div className="row">
            <label className="row"><input type="checkbox" checked={t.enabled} onChange={(e) => upd((c) => { c.templates[i].enabled = e.target.checked; })} />on</label>
            <input style={{ width: "9rem" }} value={t.key} title="key" onChange={(e) => upd((c) => { c.templates[i].key = e.target.value; })} />
            <input style={{ flex: 1, minWidth: "16rem" }} value={t.title} onChange={(e) => upd((c) => { c.templates[i].title = e.target.value; })} />
            <button onClick={() => upd((c) => { c.templates.splice(i, 1); })}>remove</button>
          </div>
          <div className="row">
            <label className="muted">subtask of <select value={t.parent ?? ""} onChange={(e) => upd((c) => { c.templates[i].parent = e.target.value || null; })}><option value="">(top level)</option>{cfg.templates.filter((x: any, j: number) => j !== i).map((x: any) => <option key={x.key}>{x.key}</option>)}</select></label>
            <label className="muted">role <select value={t.role ?? ""} onChange={(e) => upd((c) => { c.templates[i].role = e.target.value || null; })}><option value="">(default)</option>{Object.keys(cfg.roles).map((r) => <option key={r}>{r}</option>)}</select></label>
            <label className="muted">due in days <input type="number" min={0} style={{ width: "4.5rem" }} value={t.deadline_days ?? ""} onChange={(e) => upd((c) => { c.templates[i].deadline_days = e.target.value === "" ? null : Number(e.target.value); })} /></label>
            <label className="muted">done after <select value={t.done_stage ?? ""} onChange={(e) => upd((c) => { c.templates[i].done_stage = e.target.value || null; })}><option value="">(not checked)</option>{d.stages.map((s: string) => <option key={s}>{s}</option>)}</select></label>
          </div>
          <textarea style={{ minHeight: "3.5rem" }} placeholder="Description" value={t.description} onChange={(e) => upd((c) => { c.templates[i].description = e.target.value; })} />
          <textarea style={{ minHeight: "3rem" }} placeholder="Checklist, one item per line" value={t.checklist.join("\n")} onChange={(e) => upd((c) => { c.templates[i].checklist = e.target.value.split("\n").filter((x: string) => x.trim()); })} />
        </div>)}
        <div className="row">
          <button onClick={() => upd((c) => { c.templates.push({ key: `step_${c.templates.length + 1}`, title: "$ref · New step", description: "", parent: c.templates[0]?.key ?? null, role: null, deadline_days: null, done_stage: null, checklist: [], enabled: true }); })}>add step</button>
          <button onClick={() => upd((c) => { c.templates = structuredClone(d.defaults.templates); c.roles = { ...d.defaults.roles, ...c.roles }; })}>reset steps to the starting set</button>
        </div>
      </section>

      <section><h2>5 · Custom fields and Excel columns</h2>
        <div className="grid2">
          <div><b>Our value → custom field code in Bitrix24</b>
            <p className="muted">Values: ref, subject, customer, items, needed_by. Example: ref → UF_CRM_REQUEST.</p>
            <MapEditor value={cfg.custom_fields} onChange={(v) => upd((c) => { c.custom_fields = v; })} left="value" right="field" /></div>
          <div><b>Fixed extra fields for every task</b>
            <p className="muted">JSON in Bitrix24’s own names, for example {`{"PRIORITY": "2", "TAGS": ["PowerProcurement"]}`}.</p>
            <textarea style={{ minHeight: "5rem" }} defaultValue={JSON.stringify(cfg.extra_fields, null, 1)} key={JSON.stringify(cfg.extra_fields)}
              onBlur={(e) => { try { const v = JSON.parse(e.target.value || "{}"); upd((c) => { c.extra_fields = v; }); } catch { setErr("Extra fields must be valid JSON."); } }} /></div>
        </div>
        <p className="muted">Excel import understands these status words (any language, add your own): {Object.keys(cfg.excel.status_words).length} known. Edit them under “Everything as JSON”.</p>
      </section>

      <section><h2>Save</h2>
        <div className="row">
          <button className="primary" disabled={!named} onClick={() => save()}>Save all settings</button>
          <button onClick={() => { setCfg(d.config); setNote({ ok: true, text: "Changes discarded." }); }}>Discard changes</button>
        </div>
        <details><summary className="muted">Everything as JSON (export, import, copy to another installation)</summary>
          <textarea style={{ minHeight: "18rem", fontFamily: "var(--mono)" }} value={json} onChange={(e) => setJson(e.target.value)} />
          <div className="row"><button disabled={!named} onClick={() => { try { save(JSON.parse(json)); } catch { setErr("That is not valid JSON."); } }}>Save this JSON</button>
            <button onClick={() => setJson(JSON.stringify(cfg, null, 2))}>Fill from the form above</button></div>
        </details>
      </section>
    </>
  );
}

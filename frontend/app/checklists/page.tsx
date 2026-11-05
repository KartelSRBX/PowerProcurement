"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { usePerson } from "../lib/person";

const BASIS: Record<string, string> = {
  primary: "date from a primary source",
  secondary: "date only in a secondary source: check it",
  inferred: "date worked out from a rule, not stated: check it",
};

export default function Checklists() {
  const { person } = usePerson();
  const who = person.trim();
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try { setD(await api("/checklists")); setErr(""); } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function set(key: string, state: string) {
    try { await api(`/checklists/${key}`, { method: "PUT", json: { state, note: notes[key] ?? "", set_by: who } }); await load(); } catch (e: any) { setErr(e.message); }
  }
  if (!d) return <p>{err || "Loading..."}</p>;

  return (
    <>
      <div className="err" data-testid="checklist-draft"><b>Draft.</b> {d.note} Pages read on {d.checked_on}. Lines say "not found" where the pages read did not answer; nothing is filled in from memory.</div>
      {err && <div className="err">{err}</div>}
      {d.areas.map((a: any) => (
        <section key={a.key} data-testid={`area-${a.key}`}>
          <h2>{a.title} <span className="muted" style={{ fontWeight: 400 }}>· {a.answered} of {a.total} answered</span></h2>
          {a.items.map((i: any) => (
            <div className="letter" key={i.key} data-testid={`item-${i.key}`}>
              <div className="row" style={{ marginBottom: ".2rem" }}>
                <b>{i.title}</b>
                <span className="tag">draft</span>
                {i.date && <span className={`tag ${i.date_marked ? "bad" : "ok"}`} title={BASIS[i.date_basis]}>{i.date}{i.date_marked ? " · check" : ""}</span>}
                <span className={`tag ${i.source_kind === "primary" ? "ok" : ""}`}>{i.source_kind} source</span>
              </div>
              <p style={{ margin: ".2rem 0" }}>{i.detail}</p>
              {i.ask && <p className="muted" style={{ margin: ".2rem 0" }}>To check: {i.ask}</p>}
              <p className="muted" style={{ margin: ".2rem 0" }}>Source: <a href={i.source_url} target="_blank" rel="noreferrer">{i.source_url}</a> · read {i.checked_on} · “{i.quote}”{i.date_marked ? ` · ${BASIS[i.date_basis]}` : ""}</p>
              <div className="row">
                <input placeholder="note (needed for “does not apply”)" style={{ minWidth: "16rem" }} value={notes[i.key] ?? i.progress?.note ?? ""} onChange={(e) => setNotes({ ...notes, [i.key]: e.target.value })} />
                <button disabled={!who} onClick={() => set(i.key, "done")}>Checked</button>
                <button disabled={!who} onClick={() => set(i.key, "not_applicable")}>Does not apply</button>
                {i.progress && <><span className={`tag ${i.progress.state === "done" ? "ok" : ""}`}>{i.progress.state.replace("_", " ")} by {i.progress.set_by}</span><button disabled={!who} onClick={() => set(i.key, "todo")}>Reopen</button></>}
              </div>
            </div>
          ))}
        </section>
      ))}
    </>
  );
}

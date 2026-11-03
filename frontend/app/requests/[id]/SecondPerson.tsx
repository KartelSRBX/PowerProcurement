"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";

/** Orders that meet a risk rule set in Settings need a second, different person. Shows the rules this order meets and the ask that waits. */
export function SecondPerson({ id, who, act, post, data }: { id: string; who: string; act: (fn: () => Promise<unknown>) => Promise<void>; post: (path: string, json?: unknown) => Promise<unknown>; data: unknown }) {
  const [r, setR] = useState<{ risks: { kind: string; text: string }[]; pending: any } | null>(null);
  const [comment, setComment] = useState("");

  useEffect(() => { api<any>(`/requests/${id}/order-risks`).then(setR).catch(() => setR(null)); }, [id, data]);
  if (!r || (r.risks.length === 0 && !r.pending)) return null;

  const p = r.pending;
  const same = !!p && p.requested_by.trim().toLowerCase() === who.trim().toLowerCase();
  const decide = (approve: boolean) => act(() => post(`/requests/${id}/second-approval`, { decided_by: who, approve, comment }).then(() => setComment("")));

  return (
    <div className="letter" data-testid="second-person">
      <div className="row"><b>Second person</b>{p ? <span className="tag bad">waiting for a different person</span> : <span className="tag">will be needed</span>}</div>
      <ul className="muted">{(p ? p.risks : r.risks).map((x: any) => <li key={x.kind}>{x.text}</li>)}</ul>
      {!p && <p className="muted">When the order is approved below, it is not created until a different person confirms it.</p>}
      {p && <>
        <p className="muted">Approved by {p.requested_by}. The order is created, and sent to the supplier, only when someone else confirms it.</p>
        <div className="row">
          <input placeholder="comment (needed to reject)" value={comment} onChange={(e) => setComment(e.target.value)} style={{ minWidth: "16rem" }} />
          <button className="primary" disabled={!who || same} title={same ? "the first approver cannot confirm" : ""} onClick={() => decide(true)}>Confirm the order</button>
          <button disabled={!who || same || comment.trim().length < 3} onClick={() => decide(false)}>Reject</button>
        </div>
      </>}
    </div>
  );
}

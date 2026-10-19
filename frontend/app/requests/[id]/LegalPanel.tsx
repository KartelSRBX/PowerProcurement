"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

/** Contracts linked to this request, and whether open risks would stop the purchase order. */
export function LegalPanel({ id }: { id: string }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api(`/requests/${id}/legal`).then(setD).catch(() => setD(null)); }, [id]);
  if (!d) return null;
  return (
    <section><h2>Contracts <Link href="/legal" className="muted">Legal</Link></h2>
      {d.contracts.length === 0 ? <p className="muted">No contract is linked to this request. Add one on the Legal page and enter this request number.</p>
        : <table><tbody>{d.contracts.map((c: any) => <tr key={c.id}>
          <td><Link href={`/legal/contracts/${c.id}`}>{c.title}</Link> <span className="muted">{c.counterparty}</span></td>
          <td>{c.counts.red > 0 && <span className="sev red">{c.counts.red} risk{c.counts.red === 1 ? "" : "s"}</span>} {c.counts.yellow > 0 && <span className="sev yellow">{c.counts.yellow} to check</span>}</td>
          <td className="num">score {c.score}</td></tr>)}</tbody></table>}
      {d.require_signoff && <p className={d.open_red ? "err" : "muted"}>Sign-off rule is on: {d.open_red ? `${d.open_red} open risk(s) block the purchase order until someone decides on them.` : "no open risks, the purchase order is not blocked."}</p>}
    </section>
  );
}

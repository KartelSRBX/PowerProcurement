"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

/** What a person recorded about the articles on this request: end of life, and the replacements and equivalents linked to them. */
export function ItemNotes({ id, refresh }: { id: string | number; refresh: unknown }) {
  const [notes, setNotes] = useState<any[]>([]);
  useEffect(() => { api<any>(`/requests/${id}/signals`).then((s) => setNotes(s.item_notes ?? [])).catch(() => setNotes([])); }, [id, refresh]);
  if (notes.length === 0) return null;
  return (
    <div data-testid="item-notes">
      {notes.map((n) => <div className="letter" key={n.item_id}>
        <div className="row"><b>{n.description}</b>
          {n.record?.brand && <span className="tag">{n.record.brand}</span>}
          {n.record?.eol && <span className="tag bad">end of life{n.record.eol_since ? ` since ${n.record.eol_since}` : ""}</span>}
          {n.record?.eol_note && <span className="muted">{n.record.eol_note}</span>}</div>
        {n.links.map((l: any) => <div key={l.id} className="muted">{l.relation === "equivalent" ? "equivalent to" : l.relation} <b>{l.label}</b>{l.other_eol && <span className="tag bad" style={{ marginLeft: 4 }}>also end of life</span>}{l.note && ` · ${l.note}`} · entered by {l.set_by}</div>)}
      </div>)}
      <div className="muted">Entered by a person on the <Link href="/articles">Article matching</Link> tab (Notes). The app only repeats it.</div>
    </div>
  );
}

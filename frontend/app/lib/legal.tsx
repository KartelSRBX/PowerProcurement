"use client";

export const SEV_LABEL: Record<string, string> = { red: "Risk", yellow: "Check", info: "Note" };
export const STATE_LABEL: Record<string, string> = { open: "Open", accepted: "Accepted", dismissed: "Dismissed", to_lawyer: "With the lawyer" };
export const ROLE_LABEL: Record<string, string> = { buy: "We buy", sell: "We sell", both: "Both sides" };
export const CITE_LABEL: Record<string, string> = {
  verified: "found in the loaded text",
  article_missing: "act loaded, article not found",
  not_loaded: "act not loaded yet",
};

export function toBase64(f: File) {
  return new Promise<string>((ok, no) => {
    const fr = new FileReader();
    fr.onload = () => ok(String(fr.result).split(",")[1] ?? "");
    fr.onerror = () => no(new Error("the file could not be read in the browser"));
    fr.readAsDataURL(f);
  });
}

export function Sev({ s }: { s: string }) {
  return <span className={`sev ${s}`}>{SEV_LABEL[s] ?? s}</span>;
}

export function Cite({ c }: { c: any }) {
  return (
    <span className={`cite ${c.status}`} title={`${c.title || c.source}${c.heading ? " · " + c.heading : ""} — ${CITE_LABEL[c.status] ?? c.status}`}>
      {c.short}{c.article ? ` art. ${c.article}` : ""} · {CITE_LABEL[c.status] ?? c.status}
    </span>
  );
}

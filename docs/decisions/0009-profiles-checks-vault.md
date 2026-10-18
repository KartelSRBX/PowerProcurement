# 0009. Supplier profiles, supplier checks, access vault, supplier sorting

Status: requested by the user (2026-10-18); details below are the AI's proposals. Adapted from the user's first
procurement tool; nothing else from it was ported.

## Decisions

- **Profiles live on the supplier row** (brands, product types, role per brand: vendor / distributor / sub-distributor /
  reseller, stock delivery days, payment type, contract note, credit line, rebates, partner status, website). Discounts by
  brand are a small separate table. Values are validated; every edit goes into the audit log with the person's name.
- **Checks are an append-only history** (working / not working / under review, who, contact, note). The newest one counts.
  A supplier whose newest check says "not working" is left out of new shortlists; "under review" stays in with a note on the reason.
  Suppliers with no check are shown as "not checked" and stay in.
- **Sorting and filters run on the server** so the order is the same for every client: country, then category, then brand
  narrow each other (counts per option), plus role, status and check result. Empty values sort last in both directions; ties break by name.
- **The vault stores logins and passwords encrypted** with the same key as the Settings secrets (ADR 0008). Lists never carry
  them. To see one, a person files a request with a reason; a **different** person approves; the requester then reveals it
  **once**, within 15 minutes. Opening the vault, requests, decisions, reveals, edits and deletes are logged without secrets.
  If the encryption key was replaced the entry says it cannot be decrypted instead of failing silently.
- **Honest limit:** the app has no sign-in, a name is typed in the top bar. The two-person rule is a process aid and an audit
  trail, not a lock: anyone who can open the app can type a second name. Real accounts would be a separate decision.
- **Calculator** is a placeholder tab ("Unique to the project") reserved for the project's own landed-cost calculator.

## Not done / follow-ups

- Roles and sign-in; notifications for waiting vault requests; importing real supplier profiles from the old tool.

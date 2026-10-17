# 0006. Mini-CRM panel: tabs, raw mail storage, no AI in the windows

Status: accepted by the user's request (2026-10-16); details below are the AI's proposals.

## Context

The user asked for the panel to look like a small CRM with tabs: an email window, message analytics,
supplier storage, article matching and an offer builder.

## Decisions

- **One shell, six tabs** (Requests, Mail, Message analytics, Suppliers, Article matching, Offer).
  A single "who is working" field in the top bar names the person for every approval and edit.
  The pipeline page of one request stays as the full step-by-step view; the tabs are working windows
  over the same data and the same API rules.
- **Raw inbound mail is stored on its own** (`inbox_emails`). Before this, an email existed only
  after the AI parsed it, so without an API key the Mail window would be empty. Now polling stores the
  message first; a request links to it by `Message-ID`. A person can turn an unparsed email into a
  request by hand (item list drafted by a simple text rule, not AI, then checked by the person).
- **Outbound mail is shown from the records that created it** (supplier letters, customer quotes,
  purchase orders), including who approved it. `rfqs` and `customer_quotes` gained `created_at`.
- **Article matching reuses the shortlist rule** (catalog keyword found in the item text). It does not
  guess. An empty result says the price lists have no such key and points to the Suppliers tab.
- **Supplier edits require a named person and are written to the audit log.** The sanctions flag can be
  set from the UI; both directions ask for confirmation.
- **The offer window shows a server-side preview** (same landed-cost and markup code as the real quote),
  so the number on screen equals the number in the draft. A test asserts this.
- **Analytics are counts from the database**, no model. Demo-simulated supplier answers are labelled.

## Not done / follow-ups

- The UI is English only (project rule: README, code and interface in English). A first version was written in Russian by mistake and translated the next day.
- The demo inbox is the 16 synthetic gold emails, loaded by a button.
- No authentication: the "who is working" name is a label, not a login.

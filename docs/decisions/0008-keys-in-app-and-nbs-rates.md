# 0008. Keys entered in the app, National Bank of Serbia rates, install from git

Status: accepted by the user's answers (2026-10-18); details below are the AI's proposals.

## Context

The user decided: no public demo (a recorded video instead), but anyone must be able to clone the repository and run
it; people put their own keys into the application; the exchange-rate source is the National Bank of Serbia.

## Decisions

- **A Settings tab holds the Anthropic key, model and provider.** Saved values live in the database table
  `app_settings` and apply on top of the environment (`.env` still works; a saved value wins). A named person is
  required for every change and the audit log records the change without the secret.
- **The key is encrypted before it reaches the database** (Fernet). The encryption key is `APP_SECRET_KEY` or, if empty,
  generated once into the `appdata` volume. This protects a copy of the database, not a machine where both are readable.
  The API never returns the key, only whether one is set and its last four characters.
- **"Test key" makes one 8-token call** and reports a plain result (rejected, no access, model not found, rate limit, no
  network). The app does not spend anything else until a person clicks **Parse with AI** on one email.
- **Saved settings are held in memory by the one backend process** and rebuilt from the database on start and after each save. Running
  several backend processes would need a shared cache; the compose setup runs one.
- **Exchange rates: National Bank of Serbia middle rate (srednji kurs), or manual.** The bank's own list is an HTML page and
  its web service needs a registered licence, so the app reads the public JSON mirror kurs.resenje.org
  (`/api/v1/currencies/{eur|usd}/rates/today`, field `exchange_middle` divided by `parity`) and converts to units per 1 EUR.
  The URL is a setting. Every fetched rate is stored with its date; a failed fetch keeps the last good rate. A background
  thread refreshes about every six hours while NBS is selected.
- **Real mail sending stays environment-only.** SMTP and the allow-list are safety settings (ADR 0003) and are not editable in the UI.
- **Install = `git clone` + `docker compose up --build`.** No `.env` and no accounts are needed; AI is optional.

## Not done / follow-ups

- The mirror is a community service with no stated guarantee; if it disappears, set another URL or use manual rates.
  Fetching from nbs.rs directly would need parsing its HTML or a licence.
- IMAP credentials can be saved the same way once the mailbox path is tested on a real server.
- Rates apply at the moment a price is read, so an old quote keeps its stored EUR amounts but a catalog price in RSD
  follows today's rate.

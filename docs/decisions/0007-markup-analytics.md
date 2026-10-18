# 0007. Markup analytics: counts and a fitted curve, no model

Status: proposed by the AI (2026-10-18); the human asked to continue along the roadmap, details are open to change.

## Context

Phase 7 asks for analytics that recover patterns planted in the synthetic data. There are no real quote
outcomes yet, so the analysis has to be honest about what it can and cannot say.

## Decisions

- **Two sources, one table of rows.** `quote_history` holds synthetic or imported quotes; quotes made in the app
  (sent, with a recorded outcome) are read live from `customer_quotes` and `outcomes`. A quote counts as won only when accepted.
- **Synthetic data has planted profiles.** Seven customers with their own price sensitivity (the 50% point and
  steepness of the win curve). The generator is seeded, and the test checks that the suggestion lands near the planted optimum
  and that a sensitive customer gets a clearly lower markup than an insensitive one.
- **Suggestion = markup that maximizes markup × win probability.** Win probability comes from a logistic curve fitted by
  maximum likelihood (grid search), not from raw bucket rates, because bucket rates of a few dozen quotes are too noisy to take an argmax from.
  The suggestion never leaves the range of markups actually seen, and the page warns when the best point sits at the edge.
- **Minimum evidence.** Buckets under 8 quotes are drawn faded and not used; a customer needs 30 quotes, otherwise the rule
  falls back to the category, then to all quotes, and says which basis it used. Under 3 usable buckets there is no suggestion.
- **Only a hint.** The Offer tab shows the suggestion with a "Use" button; the markup stays a person's decision and still goes through approval.

## Not done / follow-ups

- Import of real quote history (CSV), margin by item category inside one quote, time trends, confidence intervals.
- The curve assumes one smooth drop; real data with a price anchor (round numbers, competitor quotes) will not fit it.

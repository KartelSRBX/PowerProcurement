# 0005. Walking skeleton before depth

Status: accepted

The plan says to build the end-to-end path on simple data first and add depth later. With no API key
available yet, the path runs without any AI:

- **Letters** (supplier RFQ, customer quote, purchase order, invoice request) come from templates in
  Serbian (Latin) and English. Each template function can be replaced by an AI drafting step with the same signature.
- **Requests** are entered by a person (the email parsing step is built and has a gold set, but is unmeasured).
- **Supplier answers** are entered as structured data. A clearly labelled demo simulator can generate them from
  the synthetic price lists; nothing pretends to be a real supplier.
- **Prices** come from synthetic price lists behind one lookup function; every observation keeps its source,
  time, currency, MOQ and validity, and is shown as unconfirmed.

Proposals that still need your approval (they are not in the plan):
- Scoring formulas per criterion (`app/scoring/scoring.py`) and the demo freight/duty and country-risk tables.
- Shortlist: category match, catalog coverage, then number of past deals; top five pre-selected.
- Target price = median of catalog prices converted to EUR.
- Purchase order checks: cost within `PO_BUDGET_LIMIT_EUR`, and agreed price not below cost.
- Default markup 15% until analytics exists; fixed demo exchange rates.

Open question from the plan, still open: the real source of RSD/EUR/USD rates.

# 0014. Landed cost: arithmetic in code, figures from people, Incoterms decide who has paid what

Status: part of the 30-day improvement plan (feature F5: landed cost instead of the flat demo markup per country). Built in three
steps: the engine (this decision), the Calculator screen, then use in scoring and quotes.

## Decisions

- **Pure code, no AI.** `app/pricing/landed.py` takes the quoted price and the figures a person supplies (freight, insurance or a
  rate, inland transport, customs agent, duty rate, VAT rate) and returns the lines, the customs value, duty, VAT, the landed cost
  and the cash out. No database, no network.
- **The Incoterms rule decides which figures the buyer still adds.** For each of the 11 rules there are five parts: origin charges,
  main carriage, insurance, delivery after the named place, import duty and taxes. The seller's price already contains the ones
  the rule makes the seller pay; the buyer adds the rest. EXW covers none of them, DDP all of them. The table is `COVERED` and a
  test checks that it lists every rule of `app/legal/incoterms.py`.
- **Nothing is guessed.** A figure that is needed and missing is a warning, counts as zero, and marks the result `complete: false`
  so a caller can show it as a lower bound or refuse to rank on it. No default for freight, insurance, duty or VAT exists in the
  code. A missing Incoterms rule is treated as ex works with a warning, because that is the case where nothing is hidden in the
  price.
- **Rule set.** Customs value = price + origin charges + carriage + insurance the buyer adds, minus the part of the price that pays
  for transport after the border (D rules; the caller enters it). Duty = customs value x rate. VAT base = customs value + duty +
  the buyer's own costs inside the country (agent, inland transport). VAT is not part of the landed cost when it can be reclaimed
  (`vat_recoverable`, the caller's statement) and is shown separately as part of the cash out. This is a simplified rule set for
  imports into Serbia and is marked as such; a tax adviser should check it before it decides a purchase.
- **Rates come from the registry, not from the code.** The duty rate for a code and origin comes from the duty registry (day 5);
  a preferential rate needs proof of origin, so choosing it stays a person's decision. The VAT rate is a setting.
- **The old flat model stays as the fallback** until offers carry enough figures; scoring will say which of the two it used.

## Used in scoring, quotes and orders (day 8)

- **A saved calculation per offer.** A person saves the Calculator's result for one offer (`offer_costs`: inputs, result,
  who, when). Scoring, the quote preview, the customer quote and the purchase order all ask one function
  (`app/pricing/offer_cost.py`) which cost an offer is judged by.
- **Only a complete, matching calculation counts.** An incomplete one is a lower bound and would make an offer look cheaper
  than it is, so it is saved but not used. A calculation whose goods value no longer matches the offer's price (the offer
  changed after saving) is not used either. Saving is refused when the items add up to a different price than the offer.
- **The flat estimate stays as the fallback**, so every offer still has a cost to rank by. Every result carries `cost_source`
  (`calculation` or `flat estimate`) and, for the flat estimate, the reason. A quote stores the basis and the breakdown it used,
  so the cost in an old quote can be explained after the calculation or the rates have changed.
- **Mixed ranking is possible**: one offer judged by a calculation and another by the flat estimate. The table says which is
  which instead of hiding it. Calculating every offer before ranking is the person's call.

## Warnings (day 9)

- **"You pay" comes from one table.** Which parts the buyer pays is decided by `COVERED` in `landed.py`, the same table
  the arithmetic uses, so the words and the numbers cannot disagree. The text for each part is the buyer's or the seller's
  duty from the Legal module's Incoterms data (`app/legal/incoterms.py`), quoted and not rewritten. The Legal data is our own
  summary of the ICC rules, not the ICC text, and the interface says so.
- **Only carriage is a flag.** An offer under EXW, FCA, FAS or FOB gets "you pay the main carriage" in its term flags,
  because that is a cost missing from the price. The full list of what the buyer pays is shown in the Calculator, not as a
  flag on every offer.
- **Old rates warn, they do not block.** The registry keeps the tariff's rate date. When it is older than a limit
  (`duty_rate_max_age_days`, 365 to start with, a setting changed by a named person), when it is missing ("unknown": nobody
  can say how old the rates are), when the code is not in the registry or not a full 10-digit line, or when no tariff is
  loaded, the calculation adds a warning. The rate typed by the person is still used and the result stays complete: a
  doubtful rate is not a missing figure. The check runs when the calculation is made or saved; it is not repeated when the
  saved calculation is later used for scoring.

## Not decided here

- Excise duties, anti-dumping duties, quotas, customs fees by band and currency conversion of figures given in other currencies
  (the caller converts to EUR first) are outside this step.

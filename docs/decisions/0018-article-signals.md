# 0018. Article signals from the company's own history

Status: accepted (plan day 17)

## Context

A buyer sees each offer on its own. What they miss is the drift: the same article quoted 15% higher than last time, or a lead time
that has crept up. The app already holds what is needed to see it: orders, accepted invoices with lines, delivery dates.

## Decisions

- **Own history only.** No market data and no AI. The reference is a price this company actually paid or ordered, and a lead time its
  own orders actually took. Market prices (day 3 of the target-price work) are estimates and stay out of this signal.
- **Paid beats ordered.** The last price is the unit price on an accepted invoice with lines; if there is none, the unit price of the
  offer behind an order, labelled "ordered" so nobody reads it as a paid price. An invoice nobody accepted does not count.
- **Price and lead history are kept apart.** A newer order without a price for the article must not hide an older one that has one.
- **An article is its part number, else its description.** Part numbers are compared as letters and digits without case; descriptions
  without case and spacing. There is no article master table, so two different wordings of the same part without a part number are
  two articles; the signal then stays quiet rather than guessing.
- **Lead time is per order, not per item.** An offer has one lead time, so it is set against the longest last lead among its items.
  It needs both a number of days and a percentage (defaults 3 days and 25%) so that 2 days becoming 3 is not an alert.
- **Thresholds are Settings values** (price rise 10%, lead rise 25% and 3 days), changed by a named person and logged.
- **A signal is a warning, never a score input and never a block.** The text says what it compared with: which order, which supplier,
  paid or ordered.

## Not decided here

- Signals on the customer side (a customer's repeated price pushback), and trends over more than the last order.
- An article master table that links alternative part numbers (plan day 18 starts that for alternates).

# 0019. Article notes: end of life, replacements and authorized channel

Status: accepted (plan day 18)

## Context

Three things a buyer knows and the app does not: a part is going end of life (and what replaces it), who makes it, and whether the
supplier quoting it is an authorized channel for that maker (a counterfeit-risk question in electronics). Getting any of them from
outside data would mean inventing it; the buyer already holds them.

## Decisions

- **A person enters it; code only warns.** No lookup, no AI, no market data. Every record, link and removal goes to the audit log
  with the person's name and, for a changed record, the previous value.
- **An article is its part number, else its description**, with the same key as the article signals (0018). There is still no article
  master table: two wordings of one part without a part number are two articles, and the notes then stay quiet rather than guess.
- **End of life is a mark with an optional date and note**, not a computed state. A date in the future is refused; leave it empty
  when it is not known. A note without the mark is refused.
- **A link is a replacement or an equivalent.** A replacement points one way (the second takes over from the first) and reads
  "replaced by" or "replaces" depending on the side it is seen from; an equivalent reads the same from both. Two articles carry one
  link at most, in either direction, so the record cannot contradict itself. A replacement that is itself end of life is marked.
- **Authorized channel is per brand, not a yes/no on the supplier.** A supplier is authorized for some brands and not others, so the
  supplier keeps `authorized_brands`, which must be among its `brands`. The warning needs both facts: the article has a manufacturer
  and the supplier is not marked for it. An article with no manufacturer entered never triggers it; the app does not guess a brand
  from the description. The text says "not marked", because it reports a missing entry, not a finding that the supplier is
  unauthorized.
- **Not a score input and not a block.** The warnings sit beside the ranking like the article signals.

## Not decided here

- Proof of authorization (a certificate, its date and expiry) attached to the supplier: today it is a tick a person sets after
  seeing one.
- Suggesting an alternate that has a price from another supplier, or searching the price lists for an equivalent.

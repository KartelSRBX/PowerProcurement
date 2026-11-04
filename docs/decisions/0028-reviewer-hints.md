# 0028. Hints for the person who approves a letter

Status: accepted (plan day 27)

## Context

Every outgoing letter is approved by a person. When the letter was written by an AI, or edited by a colleague, the approver has to read all of it to find
what is not the standard wording. And nobody could say how long approvals take or how often the drafts are changed.

## Decisions

- **Every letter keeps the plain template text for the same facts** (`template_body` on RFQs, customer quotes and the other letters), written when the
  draft is made. The draft functions now return a value that unpacks as before (subject, body, who drafted it) and also carries the template, so no
  caller had to change. The template is built every time, even when an AI text is used instead; it costs nothing.
- **The approval page shows what differs, line by line**: lines added and lines removed compared with the template, in red and green, or "same as the
  template". Whitespace and line endings are ignored. The comparison is of the saved text, so edits typed in the box and not yet saved appear after the decision.
  A letter drafted before this day has no template and says so. It is a hint: it blocks nothing, scores nothing and does not decide.
- **Decisions get a time** (`decided_at` on the same three tables). Review time is the time from the draft appearing to the decision, so it includes
  waiting; the page says so. Decisions made before this day have no time; they are counted apart and left out of the averages, not guessed.
- **Statistics** (`GET /approvals/stats`, shown on the Analytics page): per kind of letter, how many were decided, approved and rejected, the median
  and the longest time, how many differ from the template, and the same split between AI drafts and template drafts.

## Not decided here

- What a good review time is. No target is set and nobody is ranked by it; the numbers describe the process.
- Comparing the subject line, or comparing against the previous letter to the same supplier.
- Showing which words changed inside a line. A line is the unit.

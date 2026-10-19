"""Reading a contract without a model: split it into clauses, give each a type, and pull out the facts the
rules need (days, percentages, governing law, Incoterms). Every fact keeps the exact sentence it came from,
so a remark can quote the contract word for word. English text only for now."""

# ruff: noqa: E501

import re
from dataclasses import dataclass, field
from typing import Any

CLAUSE_TYPES = [
    "payment",
    "delivery",
    "title",
    "warranty",
    "inspection",
    "liability",
    "indemnity",
    "penalty",
    "termination",
    "term",
    "price_change",
    "governing_law",
    "jurisdiction",
    "confidentiality",
    "ip",
    "data",
    "sanctions",
    "force_majeure",
    "assignment",
    "subscription",
]

_KEYWORDS: dict[str, list[str]] = {
    "payment": [
        "payment",
        "invoice",
        "pay ",
        "paid",
        "remuneration",
        "due date",
        "advance",
        "prepayment",
        "pro-forma",
        "pro forma",
    ],
    "delivery": [
        "deliver",
        "incoterms",
        "shipment",
        "shipping",
        "freight",
        "carriage",
        "dispatch",
        "lead time",
    ],
    "title": [
        "retention of title",
        "title to the goods",
        "title shall",
        "ownership of the goods",
        "risk of loss",
        "risk shall pass",
        "property in the goods",
    ],
    "warranty": ["warrant", "defect", "non-conform", "guarantee", "conformity", "defective"],
    "inspection": [
        "inspection",
        "acceptance",
        "accept the goods",
        "examin",
        "deemed accepted",
        "deemed to be accepted",
    ],
    "liability": ["liab", "consequential", "indirect damages", "loss of profit", "aggregate"],
    "indemnity": ["indemn", "hold harmless"],
    "penalty": ["penalt", "liquidated damages", "late fee", "contractual fine", "delay damages"],
    "termination": ["terminat", "rescind", "cancel", "withdraw from"],
    "term": ["renew", "initial term", "duration", "expire", "expiry", "effective date", "term of this"],
    "price_change": [
        "price adjust",
        "adjust the price",
        "price increase",
        "price revision",
        "change the price",
        "modify the price",
        "escalation",
    ],
    "governing_law": ["governing law", "governed by", "applicable law", "construed in accordance"],
    "jurisdiction": ["jurisdiction", "courts of", "arbitrat", "dispute", "venue", "seat of"],
    "confidentiality": ["confidential", "non-disclosure", "trade secret"],
    "ip": ["intellectual property", "licen", "copyright", "patent", "trademark", "source code"],
    "data": ["personal data", "data protection", "gdpr", "processor", "data processing", "privacy"],
    "sanctions": [
        "sanction",
        "export control",
        "embargo",
        "re-export",
        "anti-corruption",
        "bribery",
        "dual-use",
    ],
    "force_majeure": [
        "force majeure",
        "act of god",
        "beyond the reasonable control",
        "beyond its reasonable control",
    ],
    "assignment": ["assign", "subcontract", "novat"],
    "subscription": [
        "subscription",
        "saas",
        "software as a service",
        "cloud",
        "service level",
        "uptime",
        "hosting",
    ],
}

_NUM_WORDS = {
    "seven": 7,
    "ten": 10,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty-five": 45,
    "forty five": 45,
    "sixty": 60,
    "ninety": 90,
    "one hundred and twenty": 120,
    "one hundred twenty": 120,
}
_NUM = r"(?:\d{1,3}|" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")"
_PAREN = r"(?:\s*\(\s*\d{1,3}\s*\))?"
_DAYS = rf"(?P<n>{_NUM}){_PAREN}\s*(?:calendar |working |business |banking )?(?P<u>days?|hours?)"
_DAYS2 = _DAYS.replace("(?P<n>", "(?P<n2>").replace("(?P<u>", "(?P<u2>")

SEA_TERMS = {"FAS", "FOB", "CFR", "CIF"}
_PLACE = r"[A-Z][A-Za-z'’]+(?:(?:\s+|\s+(?:of|and|the)\s+)[A-Z][A-Za-z'’]+){0,4}"
_CODES = "EXW|FCA|FAS|FOB|CPT|CIP|CFR|CIF|DAP|DPU|DDP|DAT|DAF|DES|DEQ|DDU|CNF|C&F"
_HEADING_NUM = re.compile(
    r"^\s*(?:(?:article|section|clause)\s+)?(\d{1,2}(?:\.\d{1,2})?)[.)]?\s+(?=[A-Z(\"'])", re.I
)
_HEADING_WORD = re.compile(r"^\s*(?:article|section|clause)\s+(\d{1,2})\b[.:\-–]?\s*(.*)$", re.I)


@dataclass
class Clause:
    position: int
    heading: str
    text: str
    start: int
    types: list[str] = field(default_factory=list)
    facts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def clause_type(self) -> str:
        return self.types[0] if self.types else "other"


def number(token: str) -> int | None:
    token = token.lower().strip()
    if token.isdigit():
        return int(token)
    return _NUM_WORDS.get(token)


def sentence(text: str, start: int, end: int, limit: int = 320) -> str:
    """The sentence (or line) that holds text[start:end], as written, trimmed to a readable length."""
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start), text.rfind("; ", 0, start))
    left = 0 if left < 0 else left + 1
    rights = [i for i in (text.find(". ", end), text.find("\n", end), text.find("; ", end)) if i >= 0]
    right = min(rights) + 1 if rights else len(text)
    out = text[left:right].strip()
    if len(out) > limit:
        a = max(0, start - left - limit // 2)
        out = text[left + a : left + a + limit].strip()
    return out


def split(text: str) -> list[Clause]:
    """Clauses by numbered or `Article N` headings; paragraphs when the text has none."""
    lines = [(m.start(), m.group(0)) for m in re.finditer(r"[^\n]*", text) if m.group(0).strip()]
    marks: list[tuple[int, str, int]] = []  # (offset, heading line, depth)
    for off, line in lines:
        m = _HEADING_WORD.match(line) or _HEADING_NUM.match(line)
        if m and len(line) < 4000:
            depth = m.group(1).count(".") + 1
            marks.append((off, line.strip()[:200], depth))
        elif line.strip().isupper() and 3 <= len(line.strip()) <= 70 and not line.strip().isdigit():
            marks.append((off, line.strip(), 1))
    spans: list[tuple[int, str, int]] = marks
    if len(marks) < 2:
        spans = []
        for m in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text):
            if m.group(0).strip():
                spans.append((m.start(), m.group(0).strip().split("\n", 1)[0][:200], 1))
    clauses: list[Clause] = []
    if spans and spans[0][0] > 0 and text[: spans[0][0]].strip():
        spans = [(0, "Preamble", 1), *spans]
    for i, (off, heading, _depth) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(text)
        body = text[off:end].strip()
        if body:
            clauses.append(Clause(position=len(clauses) + 1, heading=heading, text=body, start=off))
    return clauses


def classify(clauses: list[Clause]) -> None:
    """Give each clause its types. A heading hit weighs more than a hit in the body; sub-clauses such as 5.1
    take the type of the heading above them when their own words say nothing."""
    parent_types: list[str] = []
    for c in clauses:
        score: dict[str, int] = {}
        head, body = c.heading.lower(), c.text.lower()
        for kind, words in _KEYWORDS.items():
            n = sum(3 for w in words if w in head) + min(sum(body.count(w) for w in words), 4)
            if n >= 2:
                score[kind] = n
        top_level = bool(
            re.match(r"^\s*(?:(?:article|section|clause)\s+)?\d{1,2}[.)]?\s", c.heading, re.I)
        ) and not re.match(r"^\s*\d{1,2}\.\d", c.heading)
        if score:
            c.types = sorted(score, key=lambda k: -score[k])
        elif not top_level and parent_types:
            c.types = list(parent_types[:1])
        if top_level or c.position == 1:
            parent_types = c.types


def _facts(c: Clause) -> None:
    t = c.text

    def add(kind: str, value: Any, m: re.Match) -> None:
        c.facts.setdefault(kind, []).append({"value": value, "quote": sentence(t, m.start(), m.end())})

    if "payment" in c.types or re.search(r"\binvoice", t, re.I):
        for m in re.finditer(rf"(?:within|in|after|not later than|no later than|net)\s*{_DAYS}", t, re.I):
            n = number(m.group("n"))
            if n is not None and m.group("u").lower().startswith("day"):
                add("payment_days", n, m)
        for m in re.finditer(r"\bnet\s*(\d{1,3})\b", t, re.I):
            add("payment_days", int(m.group(1)), m)
    for m in re.finditer(
        r"(\d{1,3})\s*%[^.]{0,40}?(?:in advance|advance payment|prepayment|upfront|up-front|pro[- ]?forma)"
        r"|(?:advance payment|prepayment|pro[- ]?forma)[^.]{0,60}?(\d{1,3})\s*%",
        t,
        re.I,
    ):
        add("advance_pct", int(m.group(1) or m.group(2)), m)
    for m in re.finditer(
        r"\b(?:advance payment|prepayment|payment in advance|pro[- ]?forma invoice)\b", t, re.I
    ):
        if not c.facts.get("advance_pct"):
            add("advance_pct", None, m)
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:per|a|each|/)\s*(day|week|month|year|annum)", t, re.I):
        unit = m.group(2).lower()
        add(
            "rate",
            {"pct": float(m.group(1).replace(",", ".")), "unit": "year" if unit == "annum" else unit},
            m,
        )
    for m in re.finditer(
        r"shall not exceed|not exceed|limited to|maximum (?:aggregate )?liability|aggregate liability|capped at|cap of|up to a maximum",
        t,
        re.I,
    ):
        add("cap", True, m)
    for m in re.finditer(
        r"unlimited liability|without (?:any )?limit|no limit(?:ation)? (?:of|on) liability|liability (?:is|shall be) unlimited",
        t,
        re.I,
    ):
        add("unlimited", True, m)
    for m in re.finditer(
        r"(\d{1,3})\s*%\s*of\s+(?:the\s+)?(?:total\s+|annual\s+|net\s+)?(?:contract|order|purchase|fees|price|value|amount)",
        t,
        re.I,
    ):
        add("cap_pct", int(m.group(1)), m)
    if "warranty" in c.types:
        for m in re.finditer(r"(\d{1,3})\s*(?:\(\d+\)\s*)?(month|year)s?", t, re.I):
            n = int(m.group(1)) * (12 if m.group(2).lower() == "year" else 1)
            add("warranty_months", n, m)
        for m in re.finditer(
            r"\bas[- ]is\b|disclaims? (?:all|any)(?: implied)? warrant|without any warranty|no warranty",
            t,
            re.I,
        ):
            add("warranty_disclaimed", True, m)
    if {"warranty", "inspection", "termination", "term"} & set(c.types):
        for m in re.finditer(rf"(?:within|no later than|not later than)\s*{_DAYS}", t, re.I):
            n = number(m.group("n"))
            if n is not None:
                days = n if m.group("u").lower().startswith("day") else n / 24
                add("notice_days", {"days": days, "types": list(c.types)}, m)
    for m in re.finditer(
        r"automatic(?:ally)?\s+(?:renew|extend)|auto-?renew|tacit(?:ly)?\s+renew|renew(?:s|ed)?\s+automatically|renew(?:s|ed)?\s+for\s+successive|extended\s+for\s+(?:successive|further)",
        t,
        re.I,
    ):
        add("renewal", True, m)
    for m in re.finditer(
        rf"{_DAYS}'?\s*(?:prior |advance |written )*notice|notice[^.]{{0,40}}?{_DAYS2}", t, re.I
    ):
        n = number(m.group("n") or m.group("n2"))
        if n is not None:
            add("renewal_notice_days", n, m)
    for m in re.finditer(r"deemed\s+(?:to\s+be\s+)?accepted[^.]{0,80}", t, re.I):
        add("deemed_acceptance", True, m)
        d = re.search(_DAYS, m.group(0), re.I) or re.search(
            _DAYS, t[max(0, m.start() - 120) : m.end() + 120], re.I
        )
        if d and number(d.group("n")) is not None:
            c.facts["deemed_acceptance"][-1]["value"] = number(d.group("n"))
    for m in re.finditer(rf"governed by[^.]*?\blaws? of\s+(?:the\s+)?(?P<v>{_PLACE})", t):
        add("law", m.group("v").strip(), m)
    cisg = r"(?:CISG|United Nations Convention on Contracts for the International Sale of Goods|Vienna Convention)"
    for m in re.finditer(
        rf"(?:exclud\w+|disappl\w+|not apply|shall not apply)[^.]{{0,160}}{cisg}|{cisg}[^.]{{0,160}}(?:exclud\w+|not apply|disappl\w+)",
        t,
        re.I,
    ):
        add("cisg_excluded", True, m)
    for m in re.finditer(cisg, t):
        add("cisg_mentioned", True, m)
    for m in re.finditer(
        rf"(?:courts?\s+of|jurisdiction\s+of\s+the\s+courts?\s+(?:of|in)|competent\s+court\s+(?:of|in))\s+(?:the\s+)?(?P<v>{_PLACE})",
        t,
    ):
        add("forum", {"kind": "courts", "place": m.group("v").strip()}, m)
    for m in re.finditer(r"arbitrat\w*", t, re.I):
        seat = re.search(rf"(?:seat|place|venue)[^.]{{0,60}}?(?:in|of|at|shall be)\s+(?P<v>{_PLACE})", t)
        rules = re.search(r"rules\s+of\s+(?:the\s+)?(?P<v>[A-Z][A-Za-z.' -]{2,60}?)(?=\s*[,.;(]|$)", t)
        add(
            "forum",
            {
                "kind": "arbitration",
                "place": seat.group("v").strip() if seat else "",
                "rules": rules.group("v").strip() if rules else "",
            },
            m,
        )
        break
    for m in re.finditer(rf"\b({_CODES})\b", t):
        rest = t[m.end() : m.end() + 90]
        version = re.search(
            r"Incoterms[®]?\s*(?:\()?\s*(20\d\d|2000|1990)", t[max(0, m.start() - 40) : m.end() + 60], re.I
        )
        rest_clean = re.sub(r"\(?\s*Incoterms[^)\n,]*\)?", " ", rest, flags=re.I)
        p = re.match(
            r"[\s,:\-–]*(?:at |in )?(?P<v>[A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+){0,3})", rest_clean
        )
        place = p.group("v") if p and p.group("v").upper() not in _CODES.split("|") else ""
        add(
            "incoterm",
            {"code": m.group(1), "place": place, "version": version.group(1) if version else ""},
            m,
        )
    for m in re.finditer(
        r"retention of title|title (?:to the goods )?(?:shall )?(?:remain|pass)[^.]{0,80}(?:until|upon)[^.]{0,60}(?:payment|paid)|reservation of (?:title|ownership)",
        t,
        re.I,
    ):
        add("retention_of_title", True, m)


def analyse(text: str) -> list[Clause]:
    clauses = split(text)
    classify(clauses)
    for c in clauses:
        _facts(c)
    return clauses


def incoterms_version(text: str) -> str:
    m = re.search(r"Incoterms[®]?\s*(?:\()?\s*(20\d\d|2000|1990)", text, re.I)
    return m.group(1) if m else ""

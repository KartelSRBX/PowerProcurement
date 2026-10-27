"""What an Incoterms rule leaves to the buyer, in the words of the Legal module's Incoterms data. Code decides
who pays what (the table in landed.py, one source for the arithmetic and for these notes); the text for each
part is the buyer's or the seller's duty from the Legal data. That data is a summary of the ICC rule in our
own words, not the ICC text: the Legal page says to check the official publication."""

from app.legal import incoterms
from app.pricing.landed import COVERED, LABELS, PARTS

# the Legal topic that describes each part, and the label shown for it
TOPIC = {
    "origin": "clearance",
    "carriage": "carriage",
    "insurance": "insurance",
    "delivery": "costs",
    "import_taxes": "clearance",
}
SHORT = {
    "origin": "export formalities and loading",
    "carriage": "main carriage",
    "insurance": "insurance",
    "delivery": "delivery after the named place",
    "import_taxes": "import clearance, duty and taxes",
}


def you_pay(code: str | None) -> dict | None:
    """For one rule: each of the five parts with who pays it and the Legal text for that side."""
    code = (code or "").strip().upper()
    if code not in COVERED:
        return None
    rule = incoterms.build(code)
    topics = {t["key"]: t for t in rule["topics"]}
    lines = []
    for part, covered in zip(PARTS, COVERED[code], strict=True):
        topic = topics[TOPIC[part]]
        lines.append(
            {
                "key": part,
                "label": LABELS[part],
                "short": SHORT[part],
                "pays": "seller" if covered else "you",
                "text": topic["seller"] if covered else topic["buyer"],
            }
        )
    mine = [ln["short"] for ln in lines if ln["pays"] == "you"]
    return {
        "code": code,
        "name": rule["name"],
        "lines": lines,
        "summary": f"{code}: on top of the price you pay {', '.join(mine)}."
        if mine
        else f"{code}: the seller pays everything up to your door, duty and taxes included.",
        "watch": rule["watch"]["buy"],
        "source": rule["source"],
    }


def carriage_flag(code: str | None) -> str | None:
    """The warning for an offer whose Incoterms rule leaves the main carriage to the buyer."""
    code = (code or "").strip().upper()
    if code in COVERED and not COVERED[code][PARTS.index("carriage")]:
        return f"{code}: you pay the main carriage, it is not in this price"
    return None

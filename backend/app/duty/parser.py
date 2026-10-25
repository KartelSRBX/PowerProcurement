"""Reads the text of the Serbian Customs Tariff (the official PDF, Cyrillic) into one record per tariff line.

The layout this was written against, one row per tariff line:

    8527 12 00 00  - - Радио касетофони џепних димензија KD 15 ССП: 0
    CEFTA (AL, BA, MK, MD, ME, UN1244): 0
    EAEU: АМ: 0, BY: 0, KG: 0, KZ: 0, RU: 0
    TR: 0
    EFTA: IS: 0, NO: 0, CH: 0, LI: 0
    GB: 0
    CN: 9
    AE: 0
    EG: 7,5

that is: the 10-digit code, the description with leading dashes for its depth (it can wrap onto more lines),
the unit, the general (MFN) duty in percent, then "ССП:" and the rate under the Stabilisation and Association
Agreement with the EU, followed by one line per other trade agreement. The comma is the decimal mark. Codes
of 4, 6 or 8 digits are headings with no rate. A line starting with "ех"/"ex" is a sub-case of the line above
with rates of its own: it is noted, and its rates are never mixed into the line's rates. A cell that is not a
plain number (for example "таб. 3", a reference to a table) is kept as text and marked, never converted.

Text goes in, records come out; nothing here touches the database or the network."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

CODE_ROW = re.compile(r"^ (\d{4}(?: \d{2}){0,3})(?:\s+(.*))?$")
PAGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")
HEADER = re.compile(
    r"^\s*Тарифна\s*$|Тарифна\s+ознака|^\s*ознака\s+Наименовање"
)  # printed on one or two lines
EX_ROW = re.compile(r"^\s*[eе][xх]\s")  # Latin and Cyrillic look-alikes both occur
NUMBER = re.compile(r"\d+(?:,\d+)?")
RATE_ONLY = re.compile(r"(?:(\S+)\s+)?(\d+(?:,\d+)?)\s*$")  # no "ССП:" when its cell is split into sub-cases
INLINE_CEFTA = re.compile(r"\s(CEFTA\s*\([^)]*\)\s*:\s*\S+)\s*$")
RATE_CELL = re.compile(r"(?:(\S+)\s+)?(\S+)\s+ССП:\s*(.*)$", re.S)
DEPTH = re.compile(r"^((?:-\s*)*)(.*)$", re.S)
PAGE_MARK = re.compile(r"^=====PAGE \d+=====$")

UNIT = re.compile(r"[A-ZА-Я\-]{1,5}")
SINGLE = ("TR", "GB", "CN", "AE", "EG")  # agreement lines with one rate for one partner


@dataclass
class DutyLine:
    code: str  # 10 digits, no spaces
    description: str
    heading: str  # description of the 4-digit heading the line sits under
    level: int  # how many dashes the description started with
    unit: str
    mfn_rate: float | None  # general duty in percent when the cell is a plain number
    mfn_text: str  # the cell as printed
    agreements: dict[str, float | str] = field(default_factory=dict)
    has_exceptions: bool = False
    notes: str = ""

    @property
    def needs_check(self) -> bool:
        """True when something here is not a plain percentage and a person should read the tariff."""
        return (
            self.mfn_rate is None
            or self.has_exceptions
            or any(isinstance(v, str) for v in self.agreements.values())
        )


def _number(cell: str) -> float | None:
    cell = cell.strip()
    return float(cell.replace(",", ".")) if NUMBER.fullmatch(cell) else None


def _value(cell: str) -> float | str:
    cell = " ".join(cell.split()).strip(" ;,")
    n = _number(cell)
    return n if n is not None else cell


def _agreement(line: str) -> dict[str, float | str] | None:
    """One agreement line as {key: rate}, or None when the line is not one."""
    s = line.strip()
    if s.startswith("CEFTA"):
        m = re.match(r"CEFTA\s*\([^)]*\)\s*:\s*(.+)$", s)
        return {"CEFTA": _value(m.group(1))} if m else None
    m = re.match(r"(EAEU|EFTA)\s*:\s*(.+)$", s)
    if m:
        out = {}
        for part in re.split(r"[,;]\s*(?=[A-ZА-Я]{2}\s*:)", m.group(2)):  # "AM: 0, BY: 10,8; NO: 27"
            c = re.match(r"([A-ZА-Я]{2})\s*:\s*(.+)$", part.strip(), re.S)
            if c:
                out[f"{m.group(1)}:{c.group(1).translate(CYR_TO_LAT)}"] = _value(c.group(2))
        return out or None
    m = re.match(r"([A-Z]{2})\s*:\s*(.+)$", s, re.S)
    if m and m.group(1) in SINGLE:
        return {m.group(1): _value(m.group(2))}
    return None


CYR_TO_LAT = str.maketrans("АВЕКМНОРСТХ", "ABEKMHOPCTX")  # "АМ" in the EAEU line is Cyrillic


def _add_text(cur: dict, line: str) -> None:
    """Add a description/rate line; a CEFTA agreement printed at its end is split off into the agreements."""
    inline = INLINE_CEFTA.search(line)
    if inline:
        cur["agreements"].update(_agreement(inline.group(1)) or {})
        line = line[: inline.start()]
    cur["text"].append(line)


def parse_lines(lines: Iterable[str]) -> list[DutyLine]:
    """Walk the extracted text line by line. Page numbers, table headers and page markers are skipped."""
    out: list[DutyLine] = []
    heading = ""
    cur: dict | None = None  # the tariff line being collected
    in_ex = False  # inside a sub-case: its rates are not the line's rates

    def finish() -> None:
        nonlocal cur
        if cur is None:
            return
        text = " ".join(" ".join(cur["text"]).split())
        full = text
        unit, rate_cell, ssp = "", "", None
        m = RATE_CELL.search(text)
        m = m or RATE_ONLY.search(text)
        if m:
            first, rate_cell = m.group(1) or "", m.group(2)
            ssp = m.group(3) if m.re is RATE_CELL else None
            if UNIT.fullmatch(first):
                unit, text = first, text[: m.start()]
            else:  # no unit printed: the word before the rate belongs to the description
                text = f"{text[: m.start()]} {first}"
        depth = DEPTH.match(text.strip())
        agreements = dict(cur["agreements"])
        if ssp is not None:
            agreements = {"SSP": _value(ssp)} | agreements
        out.append(
            DutyLine(
                code=cur["code"],
                description=" ".join(depth.group(2).split()) if depth else text,
                heading=cur["heading"],
                level=depth.group(1).count("-") if depth else 0,
                unit=unit,
                mfn_rate=_number(rate_cell),
                mfn_text=rate_cell if _number(rate_cell) is not None else " ".join(full.split())[-160:],
                agreements=agreements,
                has_exceptions=bool(cur["ex"]),
                notes="; ".join(cur["ex"]),
            )
        )
        cur = None

    for raw in lines:
        line = raw.rstrip("\n")
        if PAGE_MARK.match(line) or HEADER.search(line) or PAGE_NUMBER.match(line) or not line.strip():
            continue
        m = CODE_ROW.match(line)
        if m:
            finish()
            in_ex = False
            digits = m.group(1).replace(" ", "")
            rest = m.group(2) or ""
            if len(digits) == 10:
                cur = {"code": digits, "text": [], "agreements": {}, "ex": [], "heading": heading}
                _add_text(cur, rest)
            elif len(digits) == 4:
                heading = " ".join(rest.split()).rstrip(":")
            continue
        if cur is None:
            continue
        if EX_ROW.match(line):
            in_ex = True
            cur["ex"].append(" ".join(line.split()))
            continue
        agr = _agreement(line)
        if agr is not None:
            if not in_ex:
                cur["agreements"].update(agr)
            continue
        if in_ex:
            cur["ex"][-1] += " " + " ".join(line.split())
        elif line.lstrip().startswith("-") and cur["agreements"]:
            finish()  # an unnumbered "- ..." line after the rates opens a heading, not the line's own text
        else:
            _add_text(cur, line)
    finish()
    return out

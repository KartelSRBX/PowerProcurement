"""What goods really cost once they are in the buyer's warehouse. Pure arithmetic: no database, no network,
no AI. The caller supplies every figure (freight, insurance, duty rate, VAT rate, ...) in EUR or percent;
this module decides only which of them the buyer still has to add, given the Incoterms rule of the offer,
and adds them up. Nothing is guessed: a figure that is needed and missing is reported as a warning and the
result is marked incomplete.

The rules (a simplified rule set, written for imports into Serbia; a tax adviser should check them):

- The quoted price already contains whatever the Incoterms rule makes the seller pay. For each rule that is
  five things: origin charges (loading, export clearance), main carriage, insurance, delivery after the named
  place, and import duty and taxes (see COVERED). The buyer adds the figures for the rest.
- Customs value = the price + what the buyer adds for origin charges, carriage and insurance, minus any part of
  the price that pays for transport inside the importing country after the border (D rules).
- Duty = customs value x duty rate (unless the seller pays it, DDP).
- VAT base = customs value + duty + the buyer's own costs inside the country up to the first destination
  (clearance agent, inland transport). VAT = base x VAT rate (unless the seller pays it, DDP).
- Landed cost = everything the buyer pays except VAT that the buyer gets back as input VAT. Cash out also counts
  that VAT. Whether it comes back is the caller's statement (vat_recoverable).
"""

# ruff: noqa: E501

from dataclasses import dataclass, field

# which of the five parts the seller already included in the price, per Incoterms 2020 rule
# (origin charges, main carriage, insurance, delivery after the named place, import duty and taxes)
COVERED: dict[str, tuple[bool, bool, bool, bool, bool]] = {
    "EXW": (False, False, False, False, False),
    "FCA": (True, False, False, False, False),
    "FAS": (True, False, False, False, False),
    "FOB": (True, False, False, False, False),
    "CFR": (True, True, False, False, False),
    "CPT": (True, True, False, False, False),
    "CIF": (True, True, True, False, False),
    "CIP": (True, True, True, False, False),
    "DAP": (True, True, True, True, False),
    "DPU": (True, True, True, True, False),
    "DDP": (True, True, True, True, True),
}
PARTS = ("origin", "carriage", "insurance", "delivery", "import_taxes")


@dataclass(frozen=True)
class LandedInput:
    price_eur: float  # what the supplier quotes for the goods, under its Incoterms rule
    incoterm: str | None = None
    origin_eur: float | None = None  # loading and export clearance, when the buyer pays them
    freight_eur: float | None = None  # main carriage to the border, when the buyer pays it
    insurance_eur: float | None = None  # a quoted insurance premium, when the buyer pays it
    insurance_pct: float | None = None  # or a rate, in percent of price + origin + carriage
    inland_eur: float | None = None  # the buyer's transport inside the country, when the buyer pays it
    clearance_eur: float | None = None  # customs agent and fees, when the buyer pays them
    inland_in_price_eur: float = 0.0  # D rules: the part of the price that is transport after the border
    duty_pct: float | None = None
    vat_pct: float | None = None
    vat_recoverable: bool = True


@dataclass
class Line:
    key: str
    label: str
    amount_eur: float
    note: str = ""


@dataclass
class Landed:
    lines: list[Line] = field(default_factory=list)
    customs_value_eur: float = 0.0
    vat_base_eur: float = 0.0
    duty_eur: float = 0.0
    vat_eur: float = 0.0
    landed_cost_eur: float = 0.0  # the cost to compare offers by
    cash_out_eur: float = 0.0  # everything paid, VAT included
    complete: bool = True  # False when a needed figure was missing
    warnings: list[str] = field(default_factory=list)
    included_by_seller: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:

        def r(x: float) -> float:
            return round(x, 2)

        return {
            "lines": [
                {"key": ln.key, "label": ln.label, "amount_eur": r(ln.amount_eur), "note": ln.note}
                for ln in self.lines
            ],
            "customs_value_eur": r(self.customs_value_eur),
            "duty_eur": r(self.duty_eur),
            "vat_base_eur": r(self.vat_base_eur),
            "vat_eur": r(self.vat_eur),
            "landed_cost_eur": r(self.landed_cost_eur),
            "cash_out_eur": r(self.cash_out_eur),
            "complete": self.complete,
            "warnings": self.warnings,
            "included_by_seller": self.included_by_seller,
        }


LABELS = {
    "origin": "origin charges",
    "carriage": "main carriage",
    "insurance": "insurance",
    "delivery": "delivery after the named place",
    "import_taxes": "import duty and taxes",
}


def compute(inp: LandedInput) -> Landed:
    for name in ("price_eur", "origin_eur", "freight_eur", "insurance_eur", "insurance_pct", "inland_eur", "clearance_eur",
                 "inland_in_price_eur", "duty_pct", "vat_pct"):  # fmt: skip
        v = getattr(inp, name)
        if v is not None and v < 0:
            raise ValueError(f"{name} cannot be negative")
    if inp.price_eur <= 0:
        raise ValueError("price_eur must be above zero")
    out = Landed()
    code = (inp.incoterm or "").strip().upper() or None
    if code is not None and code not in COVERED:
        raise ValueError(f"unknown Incoterms rule {code}")
    if code is None:
        out.warnings.append(
            "no Incoterms rule: costs are added as if the price were ex works, which is probably too high"
        )
    covered = dict(zip(PARTS, COVERED[code or "EXW"], strict=True))
    out.included_by_seller = [LABELS[p] for p in PARTS if covered[p]]

    def need(value: float | None, why: str) -> float:
        if value is None:
            out.complete = False
            out.warnings.append(why)
            return 0.0
        return value

    out.lines.append(
        Line(
            "goods",
            "goods, as quoted",
            inp.price_eur,
            f"{code or 'no rule'}: includes {', '.join(out.included_by_seller) or 'nothing beyond the goods'}",
        )
    )
    origin = (
        0.0
        if covered["origin"]
        else need(
            inp.origin_eur,
            "origin charges (loading, export clearance) are not in the price and no figure was given",
        )
    )
    freight = (
        0.0
        if covered["carriage"]
        else need(inp.freight_eur, "main carriage is not in the price and no figure was given")
    )
    if origin:
        out.lines.append(Line("origin", "origin charges", origin))
    if freight:
        out.lines.append(Line("carriage", "main carriage", freight))

    insurance = 0.0
    if not covered["insurance"]:
        if inp.insurance_eur is not None:
            insurance = inp.insurance_eur
        elif inp.insurance_pct is not None:
            insurance = (inp.price_eur + origin + freight) * inp.insurance_pct / 100
        else:
            out.complete = False
            out.warnings.append(
                "insurance is not in the price and no figure or rate was given (cargo is then uninsured or insured elsewhere)"
            )
        if insurance:
            out.lines.append(Line("insurance", "insurance", insurance))

    deduction = inp.inland_in_price_eur if covered["delivery"] else 0.0
    if deduction > inp.price_eur:
        raise ValueError("inland_in_price_eur is more than the price")
    if covered["delivery"] and not deduction:
        out.warnings.append(
            "the price includes delivery inside the country: if part of it is transport after the border, enter it so the customs value is not overstated"
        )
    out.customs_value_eur = inp.price_eur + origin + freight + insurance - deduction

    if covered["import_taxes"]:
        out.warnings.append(
            "DDP: the seller pays duty and taxes; check who is the importer of record and whether the VAT is yours to claim"
        )
    else:
        out.duty_eur = (
            out.customs_value_eur
            * need(inp.duty_pct, "the duty rate is not known, so duty is counted as zero")
            / 100
        )
        if out.duty_eur:
            out.lines.append(
                Line(
                    "duty",
                    "import duty",
                    out.duty_eur,
                    f"{inp.duty_pct:g}% of the customs value {out.customs_value_eur:.2f}",
                )
            )
    clearance = (
        0.0
        if covered["import_taxes"]
        else need(inp.clearance_eur, "customs agent and fees: no figure was given, counted as zero")
    )
    inland = (
        0.0
        if covered["delivery"]
        else need(
            inp.inland_eur,
            "transport inside the country is not in the price and no figure was given, counted as zero",
        )
    )
    if clearance:
        out.lines.append(Line("clearance", "customs agent and fees", clearance))
    if inland:
        out.lines.append(Line("inland", "transport inside the country", inland))

    if not covered["import_taxes"]:
        out.vat_base_eur = out.customs_value_eur + out.duty_eur + clearance + inland
        out.vat_eur = (
            out.vat_base_eur * need(inp.vat_pct, "the VAT rate is not known, so VAT is counted as zero") / 100
        )
        if out.vat_eur:
            out.lines.append(
                Line(
                    "vat",
                    "import VAT",
                    out.vat_eur,
                    f"{inp.vat_pct:g}% of {out.vat_base_eur:.2f}; "
                    + (
                        "reclaimable, not part of the landed cost"
                        if inp.vat_recoverable
                        else "not reclaimable, part of the landed cost"
                    ),
                )
            )

    paid = sum(ln.amount_eur for ln in out.lines if ln.key != "vat")
    out.landed_cost_eur = paid + (0.0 if inp.vat_recoverable else out.vat_eur)
    out.cash_out_eur = paid + out.vat_eur
    return out

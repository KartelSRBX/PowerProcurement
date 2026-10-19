"""The starter playbook: the checks and their first thresholds. The thresholds are only a starting point,
written as drafts that a lawyer or manager should rewrite for the company; they live in the database and
are edited in the interface. Each check reads the facts found in analysis.py and returns hits; it never
calls a model. `role` is our side: buy (we buy from the other party) or sell (we sell to them)."""

# ruff: noqa: E501

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.legal import incoterms
from app.legal.analysis import Clause, sentence

SEVERITIES = ("red", "yellow", "info")
ROLES = ("buy", "sell", "both")

# Our side's counterparty, as the contract is likely to call it.
CP = {
    "buy": r"(?:supplier|seller|vendor|provider|licensor|manufacturer)",
    "sell": r"(?:buyer|customer|purchaser|client|licensee)",
}

APPROVED_LAWS = [
    "serbia",
    "england",
    "wales",
    "switzerland",
    "germany",
    "austria",
    "france",
    "italy",
    "spain",
    "netherlands",
    "belgium",
    "poland",
    "czech",
    "hungary",
    "romania",
    "bulgaria",
    "croatia",
    "slovenia",
    "slovakia",
    "greece",
    "portugal",
    "sweden",
    "denmark",
    "finland",
    "ireland",
    "luxembourg",
    "lithuania",
    "latvia",
    "estonia",
    "cyprus",
    "malta",
]
EMBARGO = ["russia", "belarus", "iran", "north korea", "syria", "crimea", "donetsk", "luhansk", "cuba"]
DEFAULT_SETTINGS: dict[str, Any] = {
    "approved_laws": APPROVED_LAWS,
    "approved_forums": [],
    "weights": {"red": 10, "yellow": 3, "info": 0},
    "require_signoff": False,
}


@dataclass
class Hit:
    clause: Clause | None
    quote: str = ""
    severity: str | None = None  # overrides the rule's own
    extra: str = ""  # appended to the title
    citations: list[dict[str, Any]] | None = None
    risk: str | None = None


@dataclass
class Ctx:
    role: str
    text: str
    clauses: list[Clause]
    params: dict[str, Any]
    settings: dict[str, Any]
    _cache: dict[str, Any] = field(default_factory=dict)

    def facts(self, kind: str) -> list[tuple[Clause, dict[str, Any]]]:
        return [(c, f) for c in self.clauses for f in c.facts.get(kind, [])]

    def of_type(self, kind: str) -> list[Clause]:
        return [c for c in self.clauses if kind in c.types]

    def has(self, kind: str) -> bool:
        return any(kind in c.types for c in self.clauses)

    def find(self, pattern: str, flags: int = re.I) -> list[tuple[Clause, re.Match]]:
        out = []
        for c in self.clauses:
            for m in re.finditer(pattern, c.text, flags):
                out.append((c, m))
        return out

    def goods(self) -> bool:
        return bool(
            re.search(r"\b(goods|products|components|equipment|hardware|devices)\b", self.text, re.I)
        ) or self.has("delivery")

    def law(self) -> str:
        found = self.facts("law")
        return found[0][1]["value"] if found else ""


def _quote(c: Clause, m: re.Match) -> str:
    return sentence(c.text, m.start(), m.end())


CHECKS: dict[str, Callable[[Ctx], list[Hit]]] = {}


def check(key: str):
    def deco(fn):
        CHECKS[key] = fn
        return fn

    return deco


# ---- payment ------------------------------------------------------------------------------------


@check("payment_long")
def payment_long(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("payment_days"):
        d = f["value"]
        if d > x.params["red_days"]:
            out.append(Hit(c, f["quote"], "red", f"{d} days"))
        elif d > x.params["warn_days"]:
            out.append(Hit(c, f["quote"], "yellow", f"{d} days"))
    return out


@check("payment_short")
def payment_short(x: Ctx) -> list[Hit]:
    return [
        Hit(c, f["quote"], extra=f"{f['value']} days")
        for c, f in x.facts("payment_days")
        if f["value"] < x.params["min_days"]
    ]


@check("advance_payment")
def advance_payment(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("advance_pct"):
        pct = f["value"]
        sev = "red" if pct is not None and pct >= x.params["red_pct"] else None
        out.append(Hit(c, f["quote"], sev, f"{pct}% in advance" if pct is not None else "payment in advance"))
    return out


@check("payment_missing")
def payment_missing(x: Ctx) -> list[Hit]:
    return [] if x.facts("payment_days") else [Hit(None, "", extra="no payment term in days found")]


@check("late_interest_missing")
def late_interest_missing(x: Ctx) -> list[Hit]:
    pays = x.of_type("payment")
    if not pays:
        return []
    if any(re.search(r"interest|late fee|late payment|overdue|default rate", c.text, re.I) for c in pays):
        return []
    return [Hit(pays[0], pays[0].heading)]


# ---- penalties ----------------------------------------------------------------------------------


@check("penalty_rate_high")
def penalty_rate_high(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("rate"):
        v = f["value"]
        if (
            v["unit"] == "day"
            and v["pct"] > x.params["max_per_day_pct"]
            and ({"penalty"} & set(c.types) or re.search(r"penalt|liquidated|delay", c.text, re.I))
        ):
            out.append(Hit(c, f["quote"], extra=f"{v['pct']:g}% per day"))
    return out


@check("penalty_uncapped")
def penalty_uncapped(x: Ctx) -> list[Hit]:
    out = []
    for c in x.of_type("penalty"):
        rates = c.facts.get("rate")
        if rates and not re.search(
            r"shall not exceed|not exceed|capped|maximum of|up to (?:a maximum of )?\d+\s*%|in total",
            c.text,
            re.I,
        ):
            out.append(Hit(c, rates[0]["quote"]))
    return out


@check("penalty_adjustable")
def penalty_adjustable(x: Ctx) -> list[Hit]:
    law = x.law().lower()
    out = []
    if not (x.of_type("penalty") or re.search(r"liquidated damages|penalt", x.text, re.I)):
        return out
    found = [(c, m) for c, m in x.find(r"liquidated damages|penalt") if len(_quote(c, m)) >= 30]
    c, q = (found[0][0], _quote(*found[0])) if found else ((x.of_type("penalty") or x.clauses)[0], "")
    if re.search(r"china|\bprc\b|people'?s republic", law):
        out.append(Hit(c, q, extra="Chinese law", citations=[{"source": "cn-civil-code", "article": "585"}]))
    if re.search(r"emirates|\buae\b|dubai|abu dhabi", law):
        out.append(Hit(c, q, extra="UAE law", citations=[{"source": "ae-civil", "article": "390"}]))
    return out


# ---- liability ----------------------------------------------------------------------------------


@check("liability_cap_missing")
def liability_cap_missing(x: Ctx) -> list[Hit]:
    libs = x.of_type("liability")
    if not libs:
        return [Hit(None, "", extra="no limitation of liability found")]
    out = []
    for c in libs:
        if c.facts.get("unlimited"):
            out.append(Hit(c, c.facts["unlimited"][0]["quote"], "red", "liability is unlimited"))
    if not out and not any(c.facts.get("cap") for c in libs):
        out.append(Hit(libs[0], libs[0].heading, extra="no cap stated"))
    return out


@check("liability_supplier_cap_low")
def liability_supplier_cap_low(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("cap_pct"):
        if f["value"] < x.params["min_cap_pct"] and "liability" in c.types:
            out.append(Hit(c, f["quote"], extra=f"cap {f['value']}%"))
    for c in x.of_type("liability"):
        m = re.search(
            r"in no event shall[^.]{0,120}liable|excludes? (?:all|any) liability|no liability whatsoever",
            c.text,
            re.I,
        )
        if m:
            out.append(Hit(c, _quote(c, m), extra="broad exclusion"))
    return out


@check("liability_consequential")
def liability_consequential(x: Ctx) -> list[Hit]:
    out = []
    for c, m in x.find(
        r"(?:indirect|consequential|special)[^.]{0,80}(?:damages|loss)|loss of (?:profit|revenue|business)"
    ):
        if re.search(r"liab|exclud|not be liable|no liability|disclaim", c.text, re.I):
            out.append(Hit(c, _quote(c, m)))
            break
    return out


@check("liability_gross_negligence")
def liability_gross_negligence(x: Ctx) -> list[Hit]:
    out = []
    for c, m in x.find(
        r"(?:exclud|limit|no liability|not be liable)[^.]{0,150}(?:gross negligence|wilful|willful|intentional|fraud)"
    ):
        s = _quote(c, m)
        if re.search(
            r"except|other than|save for|nothing in this|does not (?:apply|limit)|shall not (?:apply|limit)",
            s,
            re.I,
        ):
            continue
        out.append(Hit(c, s))
    return out


# ---- warranty and acceptance --------------------------------------------------------------------


@check("warranty_missing")
def warranty_missing(x: Ctx) -> list[Hit]:
    return [] if x.has("warranty") or not x.goods() else [Hit(None, "", extra="no warranty clause found")]


@check("warranty_short")
def warranty_short(x: Ctx) -> list[Hit]:
    out = [
        Hit(c, f["quote"], extra=f"{f['value']} months")
        for c, f in x.facts("warranty_months")
        if f["value"] < x.params["min_months"]
    ]
    out += [Hit(c, f["quote"], "red", "warranty disclaimed") for c, f in x.facts("warranty_disclaimed")]
    return out


@check("warranty_long")
def warranty_long(x: Ctx) -> list[Hit]:
    return [
        Hit(c, f["quote"], extra=f"{f['value']} months")
        for c, f in x.facts("warranty_months")
        if f["value"] > x.params["max_months"]
    ]


@check("claims_period_short")
def claims_period_short(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("notice_days"):
        v = f["value"]
        if {"warranty", "inspection"} & set(v["types"]) and v["days"] < x.params["min_days"]:
            out.append(Hit(c, f["quote"], extra=f"{v['days']:g} days"))
    return out


@check("deemed_acceptance_short")
def deemed_acceptance_short(x: Ctx) -> list[Hit]:
    return [
        Hit(c, f["quote"], extra=f"{f['value']} days")
        for c, f in x.facts("deemed_acceptance")
        if isinstance(f["value"], int) and f["value"] < x.params["min_days"]
    ]


# ---- term, change, termination, assignment ------------------------------------------------------


@check("auto_renewal")
def auto_renewal(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("renewal"):
        notice = [n["value"] for n in c.facts.get("renewal_notice_days", [])]
        if notice and max(notice) >= x.params["min_notice_days"]:
            out.append(Hit(c, f["quote"], "info", f"notice {max(notice)} days"))
        else:
            out.append(Hit(c, f["quote"], extra="notice period missing or short"))
    return out


def _one_sided(x: Ctx, verbs: str, qualifier: str) -> list[Hit]:
    cp = CP["buy" if x.role == "buy" else "sell"]
    out = []
    for c, m in x.find(rf"\b{cp}\b[^.]{{0,100}}?(?:{verbs})[^.]{{0,160}}"):
        s = _quote(c, m)
        if re.search(qualifier, s, re.I) and not re.search(
            r"either party|each party|both parties|the parties may", s, re.I
        ):
            out.append(Hit(c, s))
    return out


@check("unilateral_change")
def unilateral_change(x: Ctx) -> list[Hit]:
    hits = _one_sided(
        x,
        r"may|reserves? the right to|is entitled to|shall be entitled to",
        r"(?:change|modify|amend|adjust|revise|increase)[^.]{0,60}(?:price|fee|rate|terms|conditions|specification)",
    )
    for h in hits:
        if re.search(r"without (?:prior )?notice|sole discretion|at any time", h.quote, re.I):
            h.severity = "red" if re.search(r"without (?:prior )?notice", h.quote, re.I) else None
    return hits


@check("termination_one_sided")
def termination_one_sided(x: Ctx) -> list[Hit]:
    return _one_sided(
        x,
        r"may terminate|may cancel|may withdraw|right to terminate",
        r"for convenience|at any time|without (?:cause|reason|notice)|sole discretion",
    )


@check("assignment_one_sided")
def assignment_one_sided(x: Ctx) -> list[Hit]:
    return _one_sided(
        x,
        r"may assign|may subcontract|may transfer|shall be entitled to assign|may delegate",
        r"without (?:[\w'’]+ ){0,4}(?:consent|approval)",
    )


# ---- law, courts --------------------------------------------------------------------------------


@check("governing_law_missing")
def governing_law_missing(x: Ctx) -> list[Hit]:
    return [] if x.facts("law") else [Hit(None, "", extra="no governing law found")]


@check("governing_law_outside")
def governing_law_outside(x: Ctx) -> list[Hit]:
    approved = [a.lower() for a in x.settings.get("approved_laws", [])]
    out = []
    for c, f in x.facts("law"):
        v = f["value"].lower()
        if approved and not any(a in v for a in approved):
            out.append(Hit(c, f["quote"], extra=f["value"]))
    return out


@check("cisg_status")
def cisg_status(x: Ctx) -> list[Hit]:
    if not x.goods():
        return []
    ex = x.facts("cisg_excluded")
    if ex:
        return [Hit(ex[0][0], ex[0][1]["quote"], extra="CISG excluded")]
    if x.facts("law"):
        c, f = x.facts("law")[0]
        return [Hit(c, f["quote"], extra="CISG not mentioned")]
    return []


@check("jurisdiction_missing")
def jurisdiction_missing(x: Ctx) -> list[Hit]:
    return [] if x.facts("forum") else [Hit(None, "", extra="no court or arbitration clause found")]


@check("forum_outside")
def forum_outside(x: Ctx) -> list[Hit]:
    approved = [a.lower() for a in x.settings.get("approved_forums", [])]
    if not approved:
        return []
    out = []
    for c, f in x.facts("forum"):
        place = f["value"].get("place", "").lower()
        if place and not any(a in place for a in approved):
            out.append(Hit(c, f["quote"], extra=f["value"]["place"]))
    return out


# ---- Incoterms ----------------------------------------------------------------------------------


@check("incoterms_missing")
def incoterms_missing(x: Ctx) -> list[Hit]:
    return [] if x.facts("incoterm") or not x.goods() else [Hit(None, "", extra="no Incoterms rule found")]


@check("incoterms_place_missing")
def incoterms_place_missing(x: Ctx) -> list[Hit]:
    return [
        Hit(c, f["quote"], extra=f["value"]["code"])
        for c, f in x.facts("incoterm")
        if not f["value"]["place"] and f["value"]["code"] in incoterms.CODES
    ]


@check("incoterms_version")
def incoterms_version(x: Ctx) -> list[Hit]:
    out = []
    for c, f in x.facts("incoterm"):
        v = f["value"]
        if v["code"] in incoterms.OUTDATED:
            out.append(
                Hit(
                    c,
                    f["quote"],
                    "red" if v["code"] == "DAT" else None,
                    v["code"],
                    risk=incoterms.OUTDATED[v["code"]],
                )
            )
        elif v["version"] and v["version"] != incoterms.VERSION:
            out.append(Hit(c, f["quote"], extra=f"Incoterms {v['version']}"))
        elif not v["version"] and not re.search(r"incoterms", x.text, re.I):
            out.append(Hit(c, f["quote"], extra=f"{v['code']} without the Incoterms edition"))
    return out[:3]


@check("incoterms_mode")
def incoterms_mode(x: Ctx) -> list[Hit]:
    if not re.search(
        r"container|air ?freight|by air|truck|road|rail|courier|CMR|\bAWB\b|air waybill", x.text, re.I
    ):
        return []
    return [
        Hit(c, f["quote"], extra=f["value"]["code"])
        for c, f in x.facts("incoterm")
        if f["value"]["code"] in incoterms.CODES and incoterms.is_sea_only(f["value"]["code"])
    ]


@check("incoterms_conflict")
def incoterms_conflict(x: Ctx) -> list[Hit]:
    codes = {f["value"]["code"] for _, f in x.facts("incoterm")}
    if len(codes) < 2:
        return []
    c, f = x.facts("incoterm")[0]
    return [Hit(c, f["quote"], extra=", ".join(sorted(codes)))]


_WATCH_SEVERITY = {
    ("sell", "DDP"): "yellow",
    ("sell", "DPU"): "yellow",
    ("buy", "EXW"): "yellow",
    ("buy", "CIF"): "yellow",
    ("buy", "CFR"): "yellow",
    ("sell", "EXW"): "yellow",
    ("sell", "FOB"): "yellow",
}


@check("incoterms_role_watch")
def incoterms_role_watch(x: Ctx) -> list[Hit]:
    out, seen = [], set()
    for c, f in x.facts("incoterm"):
        code = f["value"]["code"]
        if code in seen or code not in incoterms.CODES:
            continue
        seen.add(code)
        info = incoterms.build(code)
        out.append(
            Hit(
                c,
                f["quote"],
                _WATCH_SEVERITY.get((x.role, code), "info"),
                f"{code}: {info['name']}",
                risk=info["watch"][x.role],
            )
        )
    return out


# ---- goods, data, compliance ---------------------------------------------------------------------


@check("retention_of_title_missing")
def retention_of_title_missing(x: Ctx) -> list[Hit]:
    return (
        []
        if x.facts("retention_of_title") or not x.goods()
        else [Hit(None, "", extra="no retention of title found")]
    )


@check("data_processing_missing")
def data_processing_missing(x: Ctx) -> list[Hit]:
    hit = re.search(r"personal data|data subject|\bGDPR\b", x.text, re.I)
    if not hit or re.search(
        r"data processing (?:agreement|addendum)|\bDPA\b|article 28|standard contractual clauses|\bSCCs?\b",
        x.text,
        re.I,
    ):
        return []
    found = x.find(r"personal data|data subject|GDPR")
    return [Hit(found[0][0], _quote(*found[0]))]


@check("data_transfer")
def data_transfer(x: Ctx) -> list[Hit]:
    for c, m in x.find(
        r"outside (?:of )?(?:the )?(?:EEA|European Economic Area|EU|European Union)|third countr(?:y|ies)"
    ):
        if not re.search(
            r"standard contractual clauses|\bSCCs?\b|adequacy|binding corporate rules", x.text, re.I
        ):
            return [Hit(c, _quote(c, m))]
    return []


@check("sanctions_clause_missing")
def sanctions_clause_missing(x: Ctx) -> list[Hit]:
    if x.has("sanctions") or re.search(r"sanction|export control|embargo", x.text, re.I):
        return []
    return [Hit(None, "", extra="no sanctions or export-control clause found")]


@check("embargo_mention")
def embargo_mention(x: Ctx) -> list[Hit]:
    out, seen = [], set()
    names = [n.lower() for n in x.params.get("countries", [])]
    for c in x.clauses:
        for name in names:
            m = re.search(rf"\b{re.escape(name)}\b", c.text, re.I)
            if m and name not in seen:
                seen.add(name)
                s = _quote(c, m)
                benign = bool(
                    re.search(
                        r"shall not|must not|prohibit|no re-?export|not (?:be )?(?:sold|exported|re-?exported|resold)|undertakes not",
                        s,
                        re.I,
                    )
                )
                out.append(Hit(c, s, "info" if benign else None, name.title()))
    return out


@check("force_majeure_missing")
def force_majeure_missing(x: Ctx) -> list[Hit]:
    return [] if x.has("force_majeure") else [Hit(None, "", extra="no force majeure clause found")]


@check("confidentiality_missing")
def confidentiality_missing(x: Ctx) -> list[Hit]:
    return [] if x.has("confidentiality") else [Hit(None, "", extra="no confidentiality clause found")]


# ---- software and subscriptions -----------------------------------------------------------------


def _saas(x: Ctx) -> bool:
    return bool(re.search(r"\bsaas\b|subscription|cloud|software as a service|hosted service", x.text, re.I))


@check("saas_data_exit")
def saas_data_exit(x: Ctx) -> list[Hit]:
    if not _saas(x) or re.search(
        r"(?:return|export|retriev|delet|migrat)\w*[^.]{0,80}(?:data|content)", x.text, re.I
    ):
        return []
    return [Hit(None, "", extra="no way to get your data out on termination")]


@check("saas_service_level")
def saas_service_level(x: Ctx) -> list[Hit]:
    if not _saas(x) or re.search(r"uptime|availability|service level|\bSLA\b", x.text, re.I):
        return []
    return [Hit(None, "", extra="no uptime or service level")]


@check("delivery_date_vague")
def delivery_date_vague(x: Ctx) -> list[Hit]:
    for c, m in x.find(
        r"(?:approximate|approximately|estimated|indicative|non-binding|about)\s+(?:delivery|dispatch|lead)|delivery (?:dates?|times?) (?:is|are|shall be) (?:approximate|estimated|indicative|non-binding)"
    ):
        return [Hit(c, _quote(c, m))]
    return []


# ---- the rule list ------------------------------------------------------------------------------


def _c(source: str, article: str | None = None) -> dict[str, Any]:
    return {"source": source, "article": article} if article else {"source": source}


@dataclass(frozen=True)
class RuleDef:
    key: str
    title: str
    clause_type: str
    role: str
    severity: str
    risk: str
    suggest: str
    params: dict[str, Any] = field(default_factory=dict)
    citations: tuple[dict[str, Any], ...] = ()


RULES: list[RuleDef] = [
    RuleDef(
        "payment_long",
        "Payment term is long",
        "payment",
        "sell",
        "yellow",
        "A long payment term ties up your cash and raises the chance of late payment. For EU business-to-business sales the Late Payment Directive limits the term to 60 days unless it is expressly agreed and not grossly unfair.",
        "Ask for 30 days from the invoice, 60 at most, and interest on late payment.",
        {"warn_days": 60, "red_days": 90},
        (_c("eu-2011-7", "3"), _c("rs-payment-terms")),
    ),
    RuleDef(
        "payment_short",
        "Payment term is short",
        "payment",
        "buy",
        "yellow",
        "A short term leaves little time to receive, check and pay, and a late payment may trigger interest or penalties.",
        "Ask for 30 to 60 days counted from receipt of the goods and a correct invoice.",
        {"min_days": 30},
        (_c("eu-2011-7", "3"),),
    ),
    RuleDef(
        "advance_payment",
        "Payment in advance",
        "payment",
        "buy",
        "yellow",
        "You pay before you hold the goods. If the supplier fails or ships late you are an unsecured creditor.",
        "Pay in stages tied to milestones, or ask for a bank guarantee or letter of credit; avoid paying all of it before shipment.",
        {"red_pct": 100},
        (),
    ),
    RuleDef(
        "payment_missing",
        "No payment term in days",
        "payment",
        "both",
        "yellow",
        "Without a clear due date it is unclear when payment is late, and when interest starts.",
        "State the payment term in days and what it is counted from (invoice date, receipt of goods).",
        {},
        (_c("eu-2011-7", "3"),),
    ),
    RuleDef(
        "late_interest_missing",
        "No interest on late payment",
        "payment",
        "sell",
        "yellow",
        "Late payment is left to the statutory rules, which are slower and harder to enforce across borders than a stated rate.",
        "Add interest on late payment at a stated rate and recovery costs. EU rules give at least a fixed compensation for recovery costs.",
        {},
        (_c("eu-2011-7", "6"), _c("eu-2011-7", "3")),
    ),
    RuleDef(
        "penalty_rate_high",
        "Penalty rate is high",
        "penalty",
        "buy",
        "red",
        "Daily penalties add up fast: 1% per day is 30% of the order value in a month unless a cap stops it.",
        "Ask for at most 0.1 to 0.5% per day, a grace period and a total cap of 5 to 10% of the order value.",
        {"max_per_day_pct": 0.5},
        (_c("cn-civil-code", "585"), _c("ae-civil", "390")),
    ),
    RuleDef(
        "penalty_uncapped",
        "Penalty has no cap",
        "penalty",
        "buy",
        "yellow",
        "Without a ceiling the penalty can exceed the value of the delay.",
        "Add a ceiling as a share of the order value and make the penalty the only remedy for the delay.",
        {},
        (),
    ),
    RuleDef(
        "penalty_adjustable",
        "A court may adjust the penalty",
        "penalty",
        "both",
        "info",
        "Under this law a court can reduce a penalty that is excessive or raise one that is too low, so the agreed figure is not certain.",
        "Set a figure that matches a realistic loss and note how it was estimated.",
        {},
        (),
    ),
    RuleDef(
        "liability_cap_missing",
        "Your liability is not limited",
        "liability",
        "sell",
        "yellow",
        "Without a cap you are liable for all damage the law allows, which can be far above the price.",
        "Cap your total liability at the price of the order (or the fees of one year), and exclude indirect loss.",
        {},
        (_c("cisg", "74"),),
    ),
    RuleDef(
        "liability_supplier_cap_low",
        "The supplier's liability is limited",
        "liability",
        "buy",
        "yellow",
        "A low cap or a broad exclusion leaves you carrying the loss if the goods or service fail.",
        "Ask for a cap of at least the full price, and no cap for intent, gross negligence, death or injury.",
        {"min_cap_pct": 100},
        (_c("cisg", "74"),),
    ),
    RuleDef(
        "liability_consequential",
        "Indirect loss and lost profit are excluded",
        "liability",
        "buy",
        "yellow",
        "If the supplier's fault stops your production or your own sale, those losses are not recoverable.",
        "Ask to carve out losses that were foreseeable from the purpose of the purchase, or accept it knowingly and insure.",
        {},
        (_c("cisg", "74"),),
    ),
    RuleDef(
        "liability_gross_negligence",
        "Liability for intent or gross negligence is excluded",
        "liability",
        "both",
        "yellow",
        "Many legal systems do not let a party exclude liability for intent or gross negligence, so the clause may be void, and a court may not uphold the rest of the limit either.",
        "Remove the exclusion for intent, gross negligence and fraud, and keep the cap for ordinary negligence.",
        {},
        (_c("cn-civil-code", "506"),),
    ),
    RuleDef(
        "warranty_missing",
        "No warranty clause",
        "warranty",
        "buy",
        "yellow",
        "Without an agreed warranty you rely on the default rules, which are shorter and less clear about remedies.",
        "Add a warranty period, repair or replacement within a set time, and who pays shipping of defective goods.",
        {},
        (_c("cisg", "35"),),
    ),
    RuleDef(
        "warranty_short",
        "Warranty is short or disclaimed",
        "warranty",
        "buy",
        "yellow",
        "A short warranty ends before many defects show up; a disclaimer such as 'as is' removes your remedies.",
        "Ask for at least 12 months from delivery or commissioning, and remove 'as is' wording.",
        {"min_months": 12},
        (_c("cisg", "35"),),
    ),
    RuleDef(
        "warranty_long",
        "Warranty is long",
        "warranty",
        "sell",
        "yellow",
        "A long warranty is a cost you carry after the sale and cannot easily insure.",
        "Limit it to the period you can support, and say what voids it (misuse, third-party repair).",
        {"max_months": 24},
        (_c("cisg", "35"),),
    ),
    RuleDef(
        "claims_period_short",
        "Time to report defects is short",
        "warranty",
        "buy",
        "yellow",
        "A short window to report defects may end before you can open and test the goods. Late notice can cost you the claim.",
        "Ask for at least 14 days from discovery for visible defects and a longer period for hidden ones.",
        {"min_days": 14},
        (_c("cisg", "38"), _c("cisg", "39")),
    ),
    RuleDef(
        "deemed_acceptance_short",
        "Goods are accepted by silence after a few days",
        "inspection",
        "buy",
        "yellow",
        "If you do not object within the short period the goods count as accepted and your remedies shrink.",
        "Ask for at least 7 days after delivery, counted from the day you can inspect.",
        {"min_days": 7},
        (_c("cisg", "38"),),
    ),
    RuleDef(
        "auto_renewal",
        "The contract renews automatically",
        "term",
        "both",
        "yellow",
        "If the notice date passes, the contract runs for another full term.",
        "Put the notice date in the calendar, ask for 30 to 60 days of notice, and a right to end after the first term.",
        {"min_notice_days": 30},
        (),
    ),
    RuleDef(
        "unilateral_change",
        "The other side can change price or terms",
        "price_change",
        "both",
        "yellow",
        "The price or terms can move after you have signed, and you may be bound to the new ones.",
        "Allow changes only by written agreement, or with long notice and a right for you to end the contract without penalty.",
        {},
        (),
    ),
    RuleDef(
        "termination_one_sided",
        "Only the other side can end the contract at will",
        "termination",
        "both",
        "yellow",
        "You are bound while the other side can leave at any time, which makes planning and investment risky.",
        "Make the right to terminate for convenience mutual, with notice long enough to find a replacement.",
        {},
        (),
    ),
    RuleDef(
        "assignment_one_sided",
        "The other side can hand the contract to someone else",
        "assignment",
        "both",
        "yellow",
        "A third party you did not choose, and have not checked, may end up performing or collecting.",
        "Require your written consent for assignment or subcontracting, and keep the original party responsible.",
        {},
        (),
    ),
    RuleDef(
        "governing_law_missing",
        "No governing law",
        "governing_law",
        "both",
        "yellow",
        "Without a chosen law the court decides which applies, which is slow and uncertain.",
        "Choose a law you know or a neutral one, and state it in the contract.",
        {},
        (_c("eu-593-2008", "3"), _c("eu-593-2008", "4")),
    ),
    RuleDef(
        "governing_law_outside",
        "Governing law is not on your approved list",
        "governing_law",
        "both",
        "yellow",
        "Disputes will be judged under a law your company has not approved or may not know well.",
        "Ask for an approved or neutral law. If you accept this one, get a local lawyer's view first.",
        {},
        (_c("eu-593-2008", "3"),),
    ),
    RuleDef(
        "cisg_status",
        "Is the Vienna sales convention (CISG) meant to apply?",
        "governing_law",
        "both",
        "info",
        "The CISG applies automatically between parties in contracting states unless the contract excludes it. Leaving it unmentioned can surprise one side.",
        "Decide on purpose: exclude it by name, or keep it and check that the contract is consistent with it.",
        {},
        (_c("cisg", "1"), _c("cisg", "6")),
    ),
    RuleDef(
        "jurisdiction_missing",
        "No court or arbitration clause",
        "jurisdiction",
        "both",
        "yellow",
        "Without it, each side may sue in its own country, and an award or judgment may be hard to enforce abroad.",
        "Choose courts or arbitration with a named seat and rules, and check that the result can be enforced where the other side has assets.",
        {},
        (_c("eu-1215-2012", "25"), _c("ny-1958")),
    ),
    RuleDef(
        "forum_outside",
        "Court or arbitration seat is not on your approved list",
        "jurisdiction",
        "both",
        "yellow",
        "Proceedings abroad cost more and need local lawyers.",
        "Ask for an approved or neutral forum.",
        {},
        (_c("eu-1215-2012", "25"),),
    ),
    RuleDef(
        "incoterms_missing",
        "No Incoterms rule",
        "delivery",
        "both",
        "yellow",
        "It is unclear who pays freight, who insures, who clears customs, and when the risk passes.",
        "Add one Incoterms 2020 rule with a named place, for example 'FCA Belgrade (Incoterms 2020)'.",
        {},
        (),
    ),
    RuleDef(
        "incoterms_place_missing",
        "Incoterms rule without a named place",
        "delivery",
        "both",
        "yellow",
        "The place decides where delivery happens and where the risk passes. Without it the rule is incomplete.",
        "Name the place, for example 'FCA Rotterdam terminal (Incoterms 2020)'.",
        {},
        (),
    ),
    RuleDef(
        "incoterms_version",
        "Incoterms edition is missing or outdated",
        "delivery",
        "both",
        "yellow",
        "Rules differ between editions (DAT became DPU in 2020), so the edition decides the meaning.",
        "State the edition: 'Incoterms 2020'.",
        {},
        (),
    ),
    RuleDef(
        "incoterms_mode",
        "A sea-only rule is used for other transport",
        "delivery",
        "both",
        "yellow",
        "FAS, FOB, CFR and CIF fit sea and inland waterway cargo only. For containers or air freight the risk may pass at a point you do not control.",
        "Use FCA, CPT or CIP instead for containers, road, rail or air.",
        {},
        (),
    ),
    RuleDef(
        "incoterms_conflict",
        "More than one Incoterms rule",
        "delivery",
        "both",
        "yellow",
        "Two rules in one contract can contradict each other on risk and cost.",
        "Keep one rule per delivery and say which goods it covers.",
        {},
        (),
    ),
    RuleDef(
        "incoterms_role_watch",
        "What this Incoterms rule means for you",
        "delivery",
        "both",
        "info",
        "See the note on the rule.",
        "Check that the price includes what this rule makes you pay.",
        {},
        (),
    ),
    RuleDef(
        "delivery_date_vague",
        "Delivery date is only approximate",
        "delivery",
        "buy",
        "yellow",
        "An approximate date gives you no right to complain about a delay.",
        "Ask for a firm date or a latest date, with a remedy for delay (penalty or right to cancel).",
        {},
        (),
    ),
    RuleDef(
        "retention_of_title_missing",
        "No retention of title",
        "title",
        "sell",
        "yellow",
        "If the buyer does not pay, you cannot claim the goods back as yours.",
        "Add a retention-of-title clause until the price is paid, and check it is valid in the buyer's country.",
        {},
        (),
    ),
    RuleDef(
        "data_processing_missing",
        "Personal data but no data processing terms",
        "data",
        "both",
        "yellow",
        "When one side handles personal data for the other, the law requires a written contract with set terms.",
        "Add a data processing agreement (GDPR Article 28 terms) or confirm that no personal data is processed for the other side.",
        {},
        (_c("eu-2016-679", "28"), _c("rs-pdp")),
    ),
    RuleDef(
        "data_transfer",
        "Data transfer outside the EEA without a stated safeguard",
        "data",
        "both",
        "yellow",
        "Sending personal data to another country needs a legal basis such as standard contractual clauses.",
        "State the safeguard (standard contractual clauses or an adequacy decision) and where the data goes.",
        {},
        (_c("eu-2016-679", "44"), _c("eu-2016-679", "46"), _c("cn-pipl"), _c("ae-pdpl")),
    ),
    RuleDef(
        "sanctions_clause_missing",
        "No sanctions or export-control clause",
        "sanctions",
        "both",
        "yellow",
        "Goods and money may not move to or through sanctioned parties and countries, and EU rules require a no-re-export clause for some goods sold to third countries.",
        "Add a clause on sanctions and export control, a ban on re-export to sanctioned destinations, and a right to stop performance.",
        {},
        (_c("eu-833-2014", "12g"), _c("eu-2021-821"), _c("cn-export-control")),
    ),
    RuleDef(
        "embargo_mention",
        "A country under strict sanctions is mentioned",
        "sanctions",
        "both",
        "red",
        "Dealing with these destinations may be prohibited or need a licence. A clause that only forbids re-export is a safeguard, not a risk.",
        "Run the sanctions check on all parties and on the end destination before you sign; stop if there is a link to a listed party.",
        {"countries": EMBARGO},
        (_c("eu-833-2014"), _c("eu-269-2014"), _c("cn-anti-sanctions")),
    ),
    RuleDef(
        "force_majeure_missing",
        "No force majeure clause",
        "force_majeure",
        "both",
        "info",
        "Without it the law's default applies, which is often stricter and less clear about notice and the right to end.",
        "Add a clause naming the events, the notice duty and when either side may end the contract.",
        {},
        (),
    ),
    RuleDef(
        "confidentiality_missing",
        "No confidentiality clause",
        "confidentiality",
        "both",
        "info",
        "Prices, drawings and customer lists may be passed on freely.",
        "Add a mutual confidentiality clause or sign a separate NDA.",
        {},
        (),
    ),
    RuleDef(
        "saas_data_exit",
        "No way to get your data out",
        "subscription",
        "buy",
        "yellow",
        "On termination you may lose access to your data, and switching provider becomes costly. The EU Data Act gives customers of data-processing services a right to switch.",
        "Ask for export of your data in a common format, a transition period and deletion afterwards.",
        {},
        (_c("eu-2023-2854"),),
    ),
    RuleDef(
        "saas_service_level",
        "No uptime or service level",
        "subscription",
        "buy",
        "yellow",
        "Without a service level you have no remedy when the service is down.",
        "Ask for a stated availability, response times, and service credits.",
        {},
        (),
    ),
]


def get_rule(key: str) -> RuleDef | None:
    return next((r for r in RULES if r.key == key), None)

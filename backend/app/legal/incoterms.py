"""Incoterms 2020 as structured data, in our own words.

The ICC owns the wording of the rules, so none of it is copied here. Each rule is described by the same
ten topics the official text uses (general duties, delivery, risk, carriage, insurance, documents,
clearance, checking and packing, costs, notices), written from what is publicly known about them. A
person with the official ICC publication should compare before relying on a detail; the interface says so."""

# ruff: noqa: E501

from typing import Any

VERSION = "2020"
TOPICS = [
    ("general", "General duties"),
    ("delivery", "Delivery"),
    ("risk", "Transfer of risk"),
    ("carriage", "Carriage"),
    ("insurance", "Insurance"),
    ("documents", "Documents and proof of delivery"),
    ("clearance", "Export and import clearance"),
    ("checking", "Checking, packaging, marking"),
    ("costs", "Who pays what"),
    ("notices", "Notices and help"),
]
GROUPS = {
    "E": "Departure",
    "F": "Main carriage not paid by seller",
    "C": "Main carriage paid by seller",
    "D": "Arrival",
}

# What the contract still has to settle, whatever the rule: Incoterms say nothing about these.
NOT_COVERED = [
    "when ownership of the goods passes to the buyer",
    "the price and when it is paid",
    "what happens after a breach and who may terminate",
    "force majeure and hardship",
    "which law and which court or arbitration apply",
]

_COMMON = {
    "general": (
        "Supplies the goods and the commercial invoice as the contract says, and any proof of conformity the contract asks for.",
        "Pays the price as the contract says.",
    ),
    "checking": (
        "Pays for the checks needed to deliver (quality, measuring, weighing, counting) and packs the goods suitably for the transport, unless that trade ships them unpacked.",
        "Pays for any pre-shipment inspection it orders, except one required by the authorities of the exporting country.",
    ),
}

_SEA_ONLY = {"FAS", "FOB", "CFR", "CIF"}


def _t(**kw: Any) -> dict[str, Any]:
    return kw


_RULES: dict[str, dict[str, Any]] = {
    "EXW": _t(
        name="Ex Works",
        group="E",
        place="named place, often the seller's premises",
        summary="The seller only makes the goods available. The buyer collects, loads, exports and carries.",
        delivery=(
            "Places the goods at the buyer's disposal at the named place, not loaded on the collecting vehicle.",
            "Takes delivery when they are so placed.",
        ),
        risk=(
            "Bears loss or damage until that moment.",
            "Bears loss or damage from that moment, including during loading.",
        ),
        carriage=(
            "No obligation to arrange carriage.",
            "Arranges and pays all carriage from the named place and loads the goods. If the seller loads, it does so at the buyer's risk and cost.",
        ),
        insurance=(
            "No obligation; gives the buyer, on request, the information it needs to insure.",
            "No duty to the seller; insures in its own interest.",
        ),
        documents=(
            "No duty to supply a transport document.",
            "Gives the seller evidence that it took delivery.",
        ),
        clearance=(
            "Helps the buyer on request, at the buyer's risk and cost, to obtain export documents.",
            "Clears the goods for export and import, and obtains all licences.",
        ),
        costs=(
            "Costs up to the moment of delivery.",
            "All costs from delivery, including export and import formalities, duties and taxes, and the cost of the seller's help.",
        ),
        notices=(
            "Tells the buyer where and when the goods will be available.",
            "Tells the seller the time within the agreed period and the point where it will take delivery.",
        ),
        watch_buy="You must clear the goods for export in the seller's country and load them yourself. That is often hard for a foreign buyer; FCA is usually safer.",
        watch_sell="You carry little, but you cannot be sure the goods are really exported (proof is needed for tax-free export), and loading is at the buyer's risk. FCA gives you proof of delivery.",
    ),
    "FCA": _t(
        name="Free Carrier",
        group="F",
        place="named place where the goods are handed to the buyer's carrier",
        summary="The seller hands the goods, cleared for export, to the carrier the buyer names.",
        delivery=(
            "Delivers the goods cleared for export: loaded on the buyer's transport if the named place is the seller's premises, otherwise on the seller's transport, ready for unloading, at the disposal of the buyer's carrier.",
            "Takes delivery at the named place.",
        ),
        risk=("Bears loss or damage until delivery.", "Bears loss or damage from delivery."),
        carriage=(
            "No obligation to arrange carriage; may help on request at the buyer's risk and cost.",
            "Contracts and pays carriage from the named place and names the carrier.",
        ),
        insurance=(
            "No obligation; gives information for insurance on request.",
            "No duty to the seller; insures in its own interest.",
        ),
        documents=(
            "Gives the buyer proof of delivery. If agreed, the buyer instructs its carrier to issue an on-board bill of lading to the seller, who passes it on.",
            "Accepts the proof of delivery.",
        ),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Costs up to delivery and the cost of export clearance.",
            "Costs from delivery, including import clearance.",
        ),
        notices=(
            "Tells the buyer that the goods were delivered, or that the carrier did not take them.",
            "Tells the seller the carrier's name and the times, and where relevant the loading point.",
        ),
        watch_buy="Name the exact place: it decides who loads and where risk passes.",
        watch_sell="If the named place is not your premises you must be able to put the goods on your vehicle at that place, ready for unloading.",
    ),
    "CPT": _t(
        name="Carriage Paid To",
        group="C",
        place="named place of destination",
        summary="The seller pays carriage to the destination, but risk passes when the first carrier takes the goods.",
        delivery=(
            "Hands the goods to the first carrier it has contracted, at the agreed place.",
            "Takes delivery from the carrier at destination.",
        ),
        risk=(
            "Bears loss or damage until the goods are handed to the first carrier.",
            "Bears loss or damage from that handover, although the seller pays for carriage.",
        ),
        carriage=(
            "Contracts and pays carriage to the named destination.",
            "No duty to arrange the main carriage.",
        ),
        insurance=(
            "No obligation; gives information for insurance on request.",
            "Insures in its own interest.",
        ),
        documents=(
            "Gives the buyer, at its own cost, the usual transport document for the carriage to destination.",
            "Accepts the transport document.",
        ),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Carriage to destination and export clearance; unloading at destination only if the carriage contract puts it on the seller.",
            "All other costs from delivery, import clearance, and unloading unless included in the carriage contract.",
        ),
        notices=(
            "Tells the buyer that the goods were handed over and what it needs to receive them.",
            "Tells the seller the time and place of receipt if it may decide them.",
        ),
        watch_buy="Risk passes at the first handover, yet you do not control the carrier. Insurance is yours to arrange.",
        watch_sell="You pay carriage, but risk has already passed. Unloading costs can fall on you if your carriage contract includes them.",
    ),
    "CIP": _t(
        name="Carriage and Insurance Paid To",
        group="C",
        place="named place of destination",
        summary="Like CPT, and the seller must also insure the goods with wide cover for the buyer.",
        delivery=(
            "Hands the goods to the first carrier it has contracted, at the agreed place.",
            "Takes delivery from the carrier at destination.",
        ),
        risk=(
            "Bears loss or damage until the goods are handed to the first carrier.",
            "Bears loss or damage from that handover.",
        ),
        carriage=(
            "Contracts and pays carriage to the named destination.",
            "No duty to arrange the main carriage.",
        ),
        insurance=(
            "Buys insurance at its own cost with at least the Institute Cargo Clauses (A) (wide cover), for at least 110% of the contract price, in the contract currency, for the buyer's benefit.",
            "Gives the seller what it needs if it wants extra cover, and may buy more itself.",
        ),
        documents=(
            "Gives the buyer, at its own cost, the transport document and the insurance document.",
            "Accepts the documents.",
        ),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Carriage and insurance to destination and export clearance.",
            "All other costs from delivery, import clearance, and unloading unless included in the carriage contract.",
        ),
        notices=(
            "Tells the buyer that the goods were handed over and what it needs to receive them.",
            "Tells the seller the time and place of receipt if it may decide them.",
        ),
        watch_buy="Cover is wide and the beneficiary is you: ask for the policy and check the amount.",
        watch_sell="You must buy wider cover (A) than the minimum cover that CIF requires.",
    ),
    "DAP": _t(
        name="Delivered at Place",
        group="D",
        place="named place of destination",
        summary="The seller brings the goods to the named place, ready to unload. The buyer unloads and clears import.",
        delivery=(
            "Places the goods, on the arriving transport and ready for unloading, at the buyer's disposal at the named place.",
            "Takes delivery at the named place.",
        ),
        risk=(
            "Bears loss or damage until delivery at destination.",
            "Bears loss or damage from that moment.",
        ),
        carriage=("Contracts and pays carriage to the named place.", "No duty to arrange carriage."),
        insurance=(
            "No obligation (insure the journey in your own interest, because the risk is yours).",
            "No duty to the seller.",
        ),
        documents=("Gives the buyer the documents it needs to take delivery.", "Accepts the documents."),
        clearance=(
            "Clears the goods for export and pays transit charges.",
            "Clears the goods for import and pays import duties and taxes.",
        ),
        costs=(
            "Carriage to the named place, export clearance, transit costs.",
            "Unloading, import clearance and duties.",
        ),
        notices=(
            "Tells the buyer when the goods will arrive.",
            "Tells the seller the time and place within the period if it may decide them.",
        ),
        watch_buy="You unload and clear import: have equipment and a customs agent ready.",
        watch_sell="Risk during the whole journey and at the destination is yours. Insure all of it.",
    ),
    "DPU": _t(
        name="Delivered at Place Unloaded",
        group="D",
        place="named place of destination",
        summary="Like DAP, but the seller also unloads. Replaced DAT in 2020.",
        delivery=(
            "Unloads the goods from the arriving transport and places them at the buyer's disposal at the named place.",
            "Takes delivery after unloading.",
        ),
        risk=("Bears loss or damage until unloading is complete.", "Bears loss or damage from that moment."),
        carriage=(
            "Contracts and pays carriage to the named place and unloads there.",
            "No duty to arrange carriage.",
        ),
        insurance=(
            "No obligation (insure the journey and the unloading in your own interest).",
            "No duty to the seller.",
        ),
        documents=("Gives the buyer the documents it needs to take delivery.", "Accepts the documents."),
        clearance=(
            "Clears the goods for export and pays transit charges.",
            "Clears the goods for import and pays import duties and taxes.",
        ),
        costs=(
            "Carriage to the named place, unloading, export clearance, transit costs.",
            "Import clearance and duties.",
        ),
        notices=(
            "Tells the buyer when the goods will arrive.",
            "Tells the seller the time and place within the period if it may decide them.",
        ),
        watch_buy="The seller unloads: check that the place can receive a delivery.",
        watch_sell="This is the only rule where you must unload. Be sure you can do it at the named place; delay and damage there are yours.",
    ),
    "DDP": _t(
        name="Delivered Duty Paid",
        group="D",
        place="named place of destination",
        summary="The seller delivers to the named place and also clears import and pays duties. Maximum duty for the seller.",
        delivery=(
            "Places the goods, on the arriving transport and ready for unloading, at the buyer's disposal at the named place, cleared for import.",
            "Takes delivery at the named place.",
        ),
        risk=(
            "Bears loss or damage until delivery at destination.",
            "Bears loss or damage from that moment.",
        ),
        carriage=("Contracts and pays carriage to the named place.", "No duty to arrange carriage."),
        insurance=(
            "No obligation (insure the journey in your own interest, because the risk is yours).",
            "No duty to the seller.",
        ),
        documents=("Gives the buyer the documents it needs to take delivery.", "Accepts the documents."),
        clearance=(
            "Clears the goods for export and for import, and pays import duties and charges (taxes depend on local rules).",
            "Helps the seller on request to obtain import documents and information.",
        ),
        costs=(
            "Everything up to the named place, including export and import formalities, duties and charges.",
            "Unloading, and the cost of its help with import documents.",
        ),
        notices=(
            "Tells the buyer when the goods will arrive.",
            "Tells the seller the time and place within the period if it may decide them.",
        ),
        watch_buy="The seller handles import. Check that it may act as importer in your country, and who bears import VAT.",
        watch_sell="All cost, risk, duty and delay to the buyer's door are yours, and the cost is hard to fix in advance. Be sure you can register as importer in the buyer's country.",
    ),
    "FAS": _t(
        name="Free Alongside Ship",
        group="F",
        place="named port of shipment",
        summary="The seller places the goods alongside the buyer's vessel. Sea and inland waterway only.",
        delivery=(
            "Places the goods alongside the vessel the buyer named (on the quay or a barge) at the named port, or buys goods already so delivered.",
            "Takes delivery alongside the vessel.",
        ),
        risk=(
            "Bears loss or damage until the goods are alongside the vessel.",
            "Bears loss or damage from that moment.",
        ),
        carriage=(
            "No obligation to arrange carriage.",
            "Contracts and pays carriage from the port and names the vessel.",
        ),
        insurance=(
            "No obligation; gives information for insurance on request.",
            "Insures in its own interest.",
        ),
        documents=("Gives the buyer proof of delivery.", "Accepts the proof."),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Costs up to delivery alongside the vessel and export clearance.",
            "Costs from delivery, including loading and import clearance.",
        ),
        notices=(
            "Tells the buyer that the goods were delivered alongside the vessel.",
            "Tells the seller the vessel, the loading point and the delivery time.",
        ),
        watch_buy="You carry the goods from the quay. For containers FCA is the usual rule.",
        watch_sell="Suits bulk and heavy cargo. Not for containers handed over at a terminal.",
    ),
    "FOB": _t(
        name="Free On Board",
        group="F",
        place="named port of shipment",
        summary="The seller loads the goods on the buyer's vessel. Sea and inland waterway only.",
        delivery=(
            "Places the goods on board the vessel the buyer named at the named port, or buys goods already so delivered.",
            "Takes delivery on board.",
        ),
        risk=("Bears loss or damage until the goods are on board.", "Bears loss or damage from that moment."),
        carriage=(
            "No obligation to arrange carriage.",
            "Contracts and pays carriage from the port and names the vessel.",
        ),
        insurance=(
            "No obligation; gives information for insurance on request.",
            "Insures in its own interest.",
        ),
        documents=("Gives the buyer proof of delivery.", "Accepts the proof."),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Costs up to delivery on board and export clearance.",
            "Costs from delivery, including import clearance.",
        ),
        notices=(
            "Tells the buyer that the goods were delivered on board.",
            "Tells the seller the vessel, the loading point and the delivery time.",
        ),
        watch_buy="You must name the vessel and book the carriage; the seller's duty ends on board.",
        watch_sell="Not suited to containers you hand over at a terminal before loading: the risk would stay with you while the buyer assumes it passed on board. FCA fits better.",
    ),
    "CFR": _t(
        name="Cost and Freight",
        group="C",
        place="named port of destination",
        summary="The seller pays sea freight to the destination port, but risk passes when the goods are on board at the port of shipment.",
        delivery=(
            "Places the goods on board the vessel at the port of shipment, or buys goods already so delivered.",
            "Takes delivery from the carrier at the destination port.",
        ),
        risk=(
            "Bears loss or damage until the goods are on board.",
            "Bears loss or damage from that moment, although the seller pays freight.",
        ),
        carriage=(
            "Contracts and pays carriage to the named port of destination.",
            "No duty to arrange the main carriage.",
        ),
        insurance=(
            "No obligation; gives information for insurance on request.",
            "Insures in its own interest.",
        ),
        documents=(
            "Gives the buyer, at its own cost, the usual transport document for the carriage to the port.",
            "Accepts the transport document.",
        ),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Freight to the destination port and export clearance; unloading there only if the carriage contract puts it on the seller.",
            "All other costs from delivery, and unloading unless included in the carriage contract.",
        ),
        notices=(
            "Tells the buyer that the goods were delivered on board and what it needs to receive them.",
            "Tells the seller the time and place of receipt if it may decide them.",
        ),
        watch_buy="Risk passes at shipment, yet you do not control the vessel and the seller gives you no insurance.",
        watch_sell="Risk passes at loading but you pay freight to the destination port.",
    ),
    "CIF": _t(
        name="Cost, Insurance and Freight",
        group="C",
        place="named port of destination",
        summary="Like CFR, and the seller must also buy minimum cargo insurance for the buyer.",
        delivery=(
            "Places the goods on board the vessel at the port of shipment, or buys goods already so delivered.",
            "Takes delivery from the carrier at the destination port.",
        ),
        risk=("Bears loss or damage until the goods are on board.", "Bears loss or damage from that moment."),
        carriage=(
            "Contracts and pays carriage to the named port of destination.",
            "No duty to arrange the main carriage.",
        ),
        insurance=(
            "Buys insurance at its own cost with at least the Institute Cargo Clauses (C) (minimum cover), for at least 110% of the contract price, in the contract currency, for the buyer's benefit.",
            "Gives the seller what it needs if it wants extra cover, and may buy more itself.",
        ),
        documents=(
            "Gives the buyer, at its own cost, the transport document and the insurance document.",
            "Accepts the documents.",
        ),
        clearance=("Clears the goods for export.", "Clears the goods for import and pays import duties."),
        costs=(
            "Freight and insurance to the destination port and export clearance.",
            "All other costs from delivery, import clearance, and unloading unless included in the carriage contract.",
        ),
        notices=(
            "Tells the buyer that the goods were delivered on board and what it needs to receive them.",
            "Tells the seller the time and place of receipt if it may decide them.",
        ),
        watch_buy="The seller's insurance is only the minimum (C). Ask for wider cover or insure yourself.",
        watch_sell="You must insure at least Clause (C) for 110% of the price, and the policy must be for the buyer's benefit.",
    ),
}

CODES = list(_RULES)


def is_sea_only(code: str) -> bool:
    return code in _SEA_ONLY


OUTDATED = {
    "DAT": "DAT (Delivered at Terminal) was renamed DPU (Delivered at Place Unloaded) in Incoterms 2020.",
    "DAF": "DAF, DES, DEQ and DDU were removed in Incoterms 2010.",
    "DES": "DAF, DES, DEQ and DDU were removed in Incoterms 2010.",
    "DEQ": "DAF, DES, DEQ and DDU were removed in Incoterms 2010.",
    "DDU": "DAF, DES, DEQ and DDU were removed in Incoterms 2010.",
    "CNF": "CNF and C&F are not Incoterms; the standard rule is CFR.",
}


def build(code: str) -> dict[str, Any]:
    """The full structured record of one rule: summary, ten topics with each side's duty, and watch-outs."""
    r = _RULES[code]
    topics = []
    for key, label in TOPICS:
        seller, buyer = _COMMON[key] if key in _COMMON else r[key]
        topics.append({"key": key, "label": label, "seller": seller, "buyer": buyer})
    return {
        "code": code,
        "name": r["name"],
        "group": r["group"],
        "group_label": GROUPS[r["group"]],
        "modes": "sea and inland waterway" if code in _SEA_ONLY else "any mode",
        "sea_only": code in _SEA_ONLY,
        "place": r["place"],
        "summary": r["summary"],
        "topics": topics,
        "watch": {"buy": r["watch_buy"], "sell": r["watch_sell"]},
        "not_covered": NOT_COVERED,
        "source": "Own summary of Incoterms 2020; compare with the official ICC text before relying on a detail.",
    }


def seed(session) -> int:
    from app.models import LegalIncoterm

    added = 0
    for code in CODES:
        row = session.get(LegalIncoterm, code)
        if row is None:
            session.add(LegalIncoterm(code=code, version=VERSION, data=build(code)))
            added += 1
    return added

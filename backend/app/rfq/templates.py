"""Letter templates (Serbian Latin and English). Drafts are plain text a person can edit before approving.
An AI drafting step can later replace these through the same function signatures."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ItemLine:
    description: str
    quantity: float | None
    part_number: str | None = None


def fmt_qty(q: float | None) -> str:
    if q is None:
        return "?"
    return str(int(q)) if float(q).is_integer() else str(q)


def pick_language(languages: list[str]) -> str:
    for lang in languages:
        if lang in ("sr", "en"):
            return lang
    return "en"


def _lines(items: list[ItemLine]) -> str:
    return "\n".join(
        f"- {fmt_qty(i.quantity)} x {i.description}" + (f" ({i.part_number})" if i.part_number else "")
        for i in items
    )


def rfq_letter(
    lang: str, supplier_name: str, items: list[ItemLine], needed_by: str | None, ref: str
) -> tuple[str, str]:
    if lang == "sr":
        subject = f"Upit za ponudu [{ref}]"
        deadline = f"Željeni rok isporuke: {needed_by}.\n" if needed_by else ""
        body = (
            f"Poštovani ({supplier_name}),\n\n"
            "molimo vas za ponudu za sledeće stavke:\n"
            f"{_lines(items)}\n\n{deadline}"
            "U ponudi navedite: jediničnu cenu i valutu, minimalnu količinu porudžbine, rok isporuke, "
            "uslove plaćanja, garanciju i rok važenja ponude.\n\n"
            "Srdačan pozdrav,\nPowerProcurement (demo)"
        )
    else:
        subject = f"Request for quotation [{ref}]"
        deadline = f"Required delivery date: {needed_by}.\n" if needed_by else ""
        body = (
            f"Dear {supplier_name},\n\n"
            "please send us a quotation for the following items:\n"
            f"{_lines(items)}\n\n{deadline}"
            "Please state: unit price and currency, minimum order quantity, lead time, payment terms, "
            "warranty and the validity of the offer.\n\n"
            "Kind regards,\nPowerProcurement (demo)"
        )
    return subject, body

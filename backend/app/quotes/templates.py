from app.rfq.templates import ItemLine, fmt_qty


def _lines(items: list[ItemLine]) -> str:
    return "\n".join(f"- {fmt_qty(i.quantity)} x {i.description}" for i in items)


def quote_letter(
    lang: str, items: list[ItemLine], price: float, currency: str, lead_days: int, ref: str
) -> tuple[str, str]:
    amount = f"{price:,.2f} {currency}"
    if lang == "sr":
        return (
            f"Ponuda [{ref}]",
            "Poštovani,\n\nhvala na upitu. Naša ponuda:\n"
            f"{_lines(items)}\n\nUkupna cena: {amount}\nRok isporuke: {lead_days} dana od porudžbine\n"
            "Ponuda važi 14 dana.\n\nSrdačan pozdrav,\nPowerProcurement (demo)",
        )
    return (
        f"Quotation [{ref}]",
        "Dear customer,\n\nthank you for your request. Our offer:\n"
        f"{_lines(items)}\n\nTotal price: {amount}\nLead time: {lead_days} days from order\n"
        "This offer is valid for 14 days.\n\nKind regards,\nPowerProcurement (demo)",
    )

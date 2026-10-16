from app.rfq.templates import ItemLine, fmt_qty


def _lines(items: list[ItemLine]) -> str:
    return "\n".join(f"- {fmt_qty(i.quantity)} x {i.description}" for i in items)


def po_letter(lang: str, supplier_name: str, items: list[ItemLine], total: float, currency: str, ref: str):
    amount = f"{total:,.2f} {currency}"
    if lang == "sr":
        return (
            f"Narudžbenica [{ref}]",
            f"Poštovani ({supplier_name}),\n\npotvrđujemo narudžbinu prema vašoj ponudi:\n{_lines(items)}\n\n"
            f"Ukupno: {amount}\n\nSrdačan pozdrav,\nPowerProcurement (demo)",
        )
    return (
        f"Purchase order [{ref}]",
        f"Dear {supplier_name},\n\nwe confirm our order based on your offer:\n{_lines(items)}\n\n"
        f"Total: {amount}\n\nKind regards,\nPowerProcurement (demo)",
    )


def invoice_request_letter(lang: str, supplier_name: str, ref: str) -> tuple[str, str]:
    if lang == "sr":
        return (
            f"Molba za fakturu [{ref}]",
            f"Poštovani ({supplier_name}),\n\nmolimo vas da nam pošaljete (profaktura) fakturu za "
            f"narudžbenicu {ref}.\n\nSrdačan pozdrav,\nPowerProcurement (demo)",
        )
    return (
        f"Invoice request [{ref}]",
        f"Dear {supplier_name},\n\nplease send us the (pro-forma) invoice for purchase order {ref}.\n\n"
        "Kind regards,\nPowerProcurement (demo)",
    )

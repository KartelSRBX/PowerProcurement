"""Letter drafting. Each function returns (subject, body, drafted_by). The template is the baseline; when
AI is on the model writes the letter, and its text is used only if it passes the checks below (the reference,
every item and every figure we gave it must be present). Otherwise the template is used and says so."""

import re

from sqlalchemy.orm import Session

from app.ai.tasks import ai_enabled, run_task
from app.assist.schemas import LetterDraft
from app.config import Settings
from app.orders.templates import invoice_request_letter
from app.quotes.templates import quote_letter
from app.rfq.templates import ItemLine, fmt_qty, rfq_letter

SENDER_NAME = "PowerProcurement"
LANGUAGE_NAME = {"sr": "Serbian (Latin script)", "en": "English"}
_PLACEHOLDER = re.compile(r"\{\{|\[(your|name|company|insert)\b|<(name|company|date)>", re.I)


def items_text(items: list[ItemLine]) -> str:
    return "\n".join(
        f"{n}. {fmt_qty(i.quantity)} x {i.description}"
        + (f" (part number {i.part_number})" if i.part_number else "")
        for n, i in enumerate(items, start=1)
    )


_MONEY = re.compile(
    r"(?<![\w.,])(\d[\d.,\s]*\d|\d)\s*(?:EUR|RSD|USD|€|\$|din\b|dinar)|(?:EUR|RSD|USD|€|\$)\s*(\d[\d.,]*\d|\d)",
    re.IGNORECASE,
)


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _has(low: str, needle: str) -> bool:
    """Substring test, but a number must stand alone: '5' is not found inside '15' or '2,500'."""
    n = needle.casefold().strip()
    if n and re.fullmatch(r"[\d.,]+(\s?[a-z€$]+)?", n):
        return re.search(r"(?<![\d.,])" + re.escape(n) + r"(?![\d]|[.,]\d)", low) is not None
    return n in low


def _check(subject: str, body: str, ref: str, must_contain: list[str], amounts: list[str]) -> str | None:
    """Why this AI text cannot be used, or None when it is fine. `amounts` are the only money figures
    the letter may state (the exact ones code computed); any other amount rejects the draft."""
    if len(body.strip()) < 40:
        return "the text is too short"
    if _PLACEHOLDER.search(subject + body):
        return "the text still contains a placeholder"
    low = body.casefold()
    for needle in must_contain:
        if not _has(low, needle):
            return f"the text does not contain “{needle}”"
    allowed = {_digits(a) for a in amounts}
    for m in _MONEY.finditer(body):
        if _digits(m.group(1) or m.group(2)) not in allowed:
            return f"the text states an amount that was not given: {m.group(0).strip()}"
    return None


def _ai_letter(
    session: Session,
    settings: Settings,
    prompt_id: str,
    variables: dict[str, str],
    ref: str,
    must_contain: list[str],
    amounts: list[str],
) -> tuple[str, str, str] | tuple[None, None, str]:
    """(subject, body, drafted_by) from the model, or (None, None, drafted_by) to use the template."""
    if not ai_enabled(settings):
        return None, None, "template"
    result, note = run_task(session, settings, prompt_id, variables, LetterDraft)
    if result is None:
        return None, None, "template · AI unavailable" if note else "template"
    subject, body = result.parsed.subject.strip(), result.parsed.body.strip()
    problem = _check(subject, body, ref, must_contain, amounts)
    subject = subject[:280]
    if problem:
        return None, None, "template · AI draft rejected"
    if f"[{ref}]" not in subject:
        subject = f"{subject} [{ref}]"
    return subject, body, f"AI · {result.model}"


def rfq_text(
    session: Session,
    settings: Settings,
    lang: str,
    supplier_name: str,
    items: list[ItemLine],
    needed_by: str | None,
    ref: str,
) -> tuple[str, str, str]:
    subject, body, by = _ai_letter(
        session,
        settings,
        "rfq_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "supplier_name": supplier_name,
            "ref": ref,
            "needed_by": needed_by or "not specified",
            "items": items_text(items),
        },
        ref,
        [x for i in items for x in (i.description, fmt_qty(i.quantity))],
        [],
    )
    if subject is None:
        subject, body = rfq_letter(lang, supplier_name, items, needed_by, ref)
    return subject, body, by


def quote_text(
    session: Session,
    settings: Settings,
    lang: str,
    items: list[ItemLine],
    price: float,
    currency: str,
    lead_days: int,
    ref: str,
) -> tuple[str, str, str]:
    price_text = f"{price:,.2f} {currency}"
    subject, body, by = _ai_letter(
        session,
        settings,
        "quote_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "ref": ref,
            "price_text": price_text,
            "lead_days": str(lead_days),
            "items": items_text(items),
        },
        ref,
        [price_text, str(lead_days), *[i.description for i in items]],
        [price_text],
    )
    if subject is None:
        subject, body = quote_letter(lang, items, price, currency, lead_days, ref)
    return subject, body, by


def invoice_text(
    session: Session,
    settings: Settings,
    lang: str,
    supplier_name: str,
    items: list[ItemLine],
    total_text: str,
    ref: str,
) -> tuple[str, str, str]:
    subject, body, by = _ai_letter(
        session,
        settings,
        "invoice_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "supplier_name": supplier_name,
            "ref": ref,
            "items": items_text(items),
            "total_text": total_text or "not specified",
        },
        ref,
        [ref, *([total_text] if total_text else []), *[i.description for i in items]],
        [total_text] if total_text else [],
    )
    if subject is None:
        subject, body = invoice_request_letter(lang, supplier_name, ref)
    return subject, body, by


def followup_text(
    session: Session,
    settings: Settings,
    lang: str,
    supplier_name: str,
    items: list[ItemLine],
    needs: list[str],
    ref: str,
) -> tuple[str, str, str]:
    subject, body, by = _ai_letter(
        session,
        settings,
        "followup_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "supplier_name": supplier_name,
            "ref": ref,
            "items": items_text(items),
            "needs": "; ".join(needs),
        },
        ref,
        [],
        [],
    )
    if subject is None:
        subject, body = _followup_template(lang, supplier_name, items, needs, ref)
    return subject, body, by


def reminder_text(
    session: Session,
    settings: Settings,
    lang: str,
    items: list[ItemLine],
    price: float,
    currency: str,
    ref: str,
) -> tuple[str, str, str]:
    price_text = f"{price:,.2f} {currency}"
    subject, body, by = _ai_letter(
        session,
        settings,
        "reminder_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "ref": ref,
            "price_text": price_text,
            "items": items_text(items),
        },
        ref,
        [price_text],
        [price_text],
    )
    if subject is None:
        subject, body = _reminder_template(lang, items, price_text, ref)
    return subject, body, by


def order_confirmation_text(
    session: Session,
    settings: Settings,
    lang: str,
    items: list[ItemLine],
    price: float,
    currency: str,
    lead_days: int,
    ref: str,
) -> tuple[str, str, str]:
    price_text = f"{price:,.2f} {currency}"
    subject, body, by = _ai_letter(
        session,
        settings,
        "order_confirmation_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "ref": ref,
            "price_text": price_text,
            "lead_days": str(lead_days),
            "items": items_text(items),
        },
        ref,
        [price_text, str(lead_days), *[i.description for i in items]],
        [price_text],
    )
    if subject is None:
        subject, body = _confirmation_template(lang, items, price_text, lead_days, ref)
    return subject, body, by


def delivery_question_text(
    session: Session,
    settings: Settings,
    lang: str,
    supplier_name: str,
    items: list[ItemLine],
    ref: str,
) -> tuple[str, str, str]:
    subject, body, by = _ai_letter(
        session,
        settings,
        "delivery_question_draft",
        {
            "language_name": LANGUAGE_NAME.get(lang, "English"),
            "sender_name": SENDER_NAME,
            "supplier_name": supplier_name,
            "ref": ref,
            "items": items_text(items),
        },
        ref,
        [ref, *[i.description for i in items]],
        [],
    )
    if subject is None:
        subject, body = _delivery_template(lang, supplier_name, items, ref)
    return subject, body, by


def _lines(items: list[ItemLine]) -> str:
    return "\n".join(f"- {fmt_qty(i.quantity)} x {i.description}" for i in items)


def _followup_template(
    lang: str, supplier_name: str, items: list[ItemLine], needs: list[str], ref: str
) -> tuple[str, str]:
    wanted = "\n".join(f"- {n}" for n in needs)
    if lang == "sr":
        return (
            f"Podsetnik: upit za ponudu [{ref}]",
            f"Poštovani ({supplier_name}),\n\nodnosi se na naš raniji upit za stavke:\n{_lines(items)}\n\n"
            f"Molimo vas da nam dostavite:\n{wanted}\n\nSrdačan pozdrav,\n{SENDER_NAME} (demo)",
        )
    return (
        f"Follow-up: request for quotation [{ref}]",
        f"Dear {supplier_name},\n\nthis refers to our earlier request for:\n{_lines(items)}\n\n"
        f"Could you please send us:\n{wanted}\n\nKind regards,\n{SENDER_NAME} (demo)",
    )


def _reminder_template(lang: str, items: list[ItemLine], price_text: str, ref: str) -> tuple[str, str]:
    if lang == "sr":
        return (
            f"Podsetnik: ponuda [{ref}]",
            "Poštovani,\n\nsamo da proverimo da li ste imali priliku da pogledate našu ponudu:\n"
            f"{_lines(items)}\n\nUkupna cena: {price_text}\n\nRado ćemo odgovoriti na sva pitanja.\n\n"
            f"Srdačan pozdrav,\n{SENDER_NAME} (demo)",
        )
    return (
        f"Reminder: quotation [{ref}]",
        "Dear customer,\n\na quick reminder about our quotation:\n"
        f"{_lines(items)}\n\nTotal price: {price_text}\n\n"
        f"We are happy to answer any questions.\n\nKind regards,\n{SENDER_NAME} (demo)",
    )


def _confirmation_template(
    lang: str, items: list[ItemLine], price_text: str, lead_days: int, ref: str
) -> tuple[str, str]:
    if lang == "sr":
        return (
            f"Potvrda narudžbine [{ref}]",
            f"Poštovani,\n\nhvala vam na prihvatanju ponude. Potvrđujemo narudžbinu:\n{_lines(items)}\n\n"
            f"Ukupna cena: {price_text}\nOčekivani rok isporuke: {lead_days} dana.\n\n"
            f"Obavestićemo vas ako dođe do promene.\n\nSrdačan pozdrav,\n{SENDER_NAME} (demo)",
        )
    return (
        f"Order confirmation [{ref}]",
        "Dear customer,\n\nthank you for accepting our quotation. We confirm your order:\n"
        f"{_lines(items)}\n\n"
        f"Total price: {price_text}\nExpected delivery: {lead_days} days.\n\n"
        f"We will let you know if anything changes.\n\nKind regards,\n{SENDER_NAME} (demo)",
    )


def _delivery_template(lang: str, supplier_name: str, items: list[ItemLine], ref: str) -> tuple[str, str]:
    if lang == "sr":
        return (
            f"Isporuka narudžbenice [{ref}]",
            f"Poštovani ({supplier_name}),\n\npitanje se odnosi na narudžbenicu {ref}:\n{_lines(items)}\n\n"
            "Molimo vas da nam potvrdite datum otpreme, prevoznika i broj za praćenje pošiljke, kao i "
            "otpremne dokumente (paking lista, faktura, sertifikat o poreklu ako je potreban). "
            f"Obavestite nas odmah o eventualnom kašnjenju.\n\nSrdačan pozdrav,\n{SENDER_NAME} (demo)",
        )
    return (
        f"Delivery of purchase order [{ref}]",
        f"Dear {supplier_name},\n\nthis is about purchase order {ref}:\n{_lines(items)}\n\n"
        "Could you please confirm the dispatch date, the carrier and the tracking number, and send the "
        "shipping documents (packing list, commercial invoice, certificate of origin if applicable)? "
        f"Please tell us at once about any delay.\n\nKind regards,\n{SENDER_NAME} (demo)",
    )

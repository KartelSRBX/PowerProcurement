"""The reading and explaining jobs: classify a customer's reply, explain a supplier comparison in words,
describe analytics in words, and parse the whole inbox. These need the model; with AI off they say so
plainly instead of guessing. None of them changes a number or sends anything."""

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.tasks import ai_enabled, run_task
from app.analytics import pricing
from app.assist.schemas import CustomerAnswer, Narrative, ScoreExplanation
from app.config import Settings
from app.crm import service as crm
from app.intake.mailbox import InboundEmail
from app.intake.service import intake_email
from app.models import CustomerQuote, CustomerRequest, InboxEmail
from app.pipeline.service import PipelineError, score_request
from app.scoring.scoring import Weights

AI_OFF = "AI is off: add your Anthropic key in Settings first"


def _need_ai(settings: Settings) -> None:
    if not ai_enabled(settings):
        raise PipelineError(AI_OFF)


def read_customer_answer(session: Session, settings: Settings, quote_id: int, text: str) -> dict:
    """Proposal for the outcome form. A person still records the outcome."""
    _need_ai(settings)
    quote = session.get(CustomerQuote, quote_id)
    if quote is None:
        raise LookupError("quote not found")
    if quote.status != "sent":
        raise PipelineError("an answer can only be read for a quote that was sent")
    if not text.strip():
        raise PipelineError("paste the customer's reply first")
    result, note = run_task(
        session,
        settings,
        "customer_answer",
        {
            "currency": quote.currency,
            "price": f"{quote.price:,.2f}",
            "quote": quote.body,
            "text": text.strip()[:20000],
        },
        CustomerAnswer,
    )
    if result is None:
        raise PipelineError(note or AI_OFF)
    a = result.parsed
    return {
        "kind": a.kind,
        "price": a.price if a.kind == "counter" else None,
        "currency": (a.currency or quote.currency) if a.kind == "counter" and a.price else None,
        "reason": a.reason,
        "confidence": a.confidence,
        "model": result.model,
    }


def explain_scores(session: Session, settings: Settings, request_id: int, weights: Weights) -> dict:
    _need_ai(settings)
    ranked = score_request(session, settings, request_id, weights)
    slim = [
        {
            "offer_id": r["offer_id"],
            "supplier": r["supplier"],
            "country": r["country"],
            "excluded": r["excluded"],
            "total": r["total"],
            "scores": r["scores"],
            "flags": r["flags"],
            "landed_cost_eur": r["landed_cost_eur"],
            "lead_time_days": r["lead_time_days"],
        }
        for r in ranked
    ]
    result, note = run_task(
        session,
        settings,
        "score_explain",
        {"ranked": json.dumps(slim, ensure_ascii=False), "weights": json.dumps(weights.__dict__)},
        ScoreExplanation,
    )
    if result is None:
        raise PipelineError(note or AI_OFF)
    ids = {r["offer_id"] for r in ranked}
    return {
        "summary": result.parsed.summary,
        "suppliers": {s.offer_id: s.text for s in result.parsed.suppliers if s.offer_id in ids},
        "model": result.model,
        "ranked": ranked,
    }


def narrative(
    session: Session,
    settings: Settings,
    topic: str,
    days: int = 30,
    customer: str | None = None,
    category: str | None = None,
) -> dict:
    _need_ai(settings)
    if topic == "messages":
        data = crm.message_analytics(session, max(1, min(days, 180)))
        label = f"incoming email and the funnel over the last {days} days"
    elif topic == "pricing":
        rows = pricing.load_rows(session, settings)
        data = pricing.overview(rows, customer or None, category or None)
        label = "quote win rate by markup and the suggested markup"
    else:
        raise PipelineError("topic must be messages or pricing")
    result, note = run_task(
        session,
        settings,
        "narrative",
        {"topic": label, "data": json.dumps(data, ensure_ascii=False, default=str)[:30000]},
        Narrative,
    )
    if result is None:
        raise PipelineError(note or AI_OFF)
    return {"headline": result.parsed.headline, "points": result.parsed.points, "model": result.model}


def parse_inbox(session: Session, settings: Settings, limit: int = 20) -> dict:
    """Read every stored email that has no request yet. A person reviews the results in Mail."""
    _need_ai(settings)
    from app.ai import tasks

    adapter = tasks._factory(settings)  # noqa: SLF001 - same adapter the other AI steps use
    known = set(session.scalars(select(CustomerRequest.message_id)))
    todo = [
        e for e in session.scalars(select(InboxEmail).order_by(InboxEmail.id)) if e.message_id not in known
    ]
    counts = {"parsed": 0, "needs_review": 0, "not_request": 0, "failed": 0, "left": 0}
    for n, e in enumerate(todo):
        if n >= max(1, min(limit, 50)):
            counts["left"] = len(todo) - n
            break
        try:
            row = intake_email(
                session,
                adapter,
                settings,
                InboundEmail(e.message_id, e.sender, e.subject, e.body, e.received_at),
            )
            counts[row.status] = counts.get(row.status, 0) + 1
        except Exception:  # noqa: BLE001 - one bad email must not stop the rest
            session.rollback()
            counts["failed"] += 1
    return counts | {"today": date.today().isoformat()}

"""Legal module logic: seeding, the norm base, the playbook, contracts and their findings, reports, and the
portfolio view. Nothing here sends anything outside; the optional AI read of a contract is in review_ai."""

# ruff: noqa: E501

import io
import json
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.ai.tasks import ai_enabled, run_task
from app.config import Settings
from app.legal import analysis, incoterms, playbook
from app.legal.catalog import CATALOG, JURISDICTIONS
from app.legal.schemas import ContractReview
from app.models import (
    AppSetting,
    AuditLog,
    Contract,
    ContractClause,
    ContractFinding,
    CustomerRequest,
    LegalIncoterm,
    LegalProvision,
    LegalRule,
    LegalSource,
)

SETTINGS_KEY = "legal_settings"
STATES = ("open", "accepted", "dismissed", "to_lawyer")
OPEN_STATES = ("open", "to_lawyer")
MAX_TEXT = 400_000
AI_MAX_CHARS = 60_000


class LegalError(ValueError):
    """A reason the action was refused, in plain words."""


def _named(person: str) -> str:
    if not person or not person.strip():
        raise LegalError("a named person is required for this action")
    return person.strip()


# ---- seeding -------------------------------------------------------------------------------------


def ensure_seed(session: Session) -> None:
    """Fill in what the code ships with, without touching what people changed or loaded."""
    changed = False
    have = {k for (k,) in session.execute(select(LegalSource.key))}
    for e in CATALOG:
        if e["key"] not in have:
            session.add(
                LegalSource(
                    key=e["key"],
                    jurisdiction=e["jurisdiction"],
                    kind=e["kind"],
                    title=e["title"],
                    short=e["short"],
                    ref=e.get("ref"),
                    language="en",
                    topics=e["topics"],
                    fetch=e["fetch"],
                    source_url=e.get("source_url"),
                    note=e.get("note", ""),
                    status="not_loaded",
                    provision_count=0,
                )
            )
            changed = True
    if session.scalar(select(func.count()).select_from(LegalIncoterm)) < len(incoterms.CODES):
        changed = incoterms.seed(session) > 0 or changed
    have_rules = {k for (k,) in session.execute(select(LegalRule.key))}
    for r in playbook.RULES:
        if r.key not in have_rules:
            session.add(
                LegalRule(
                    key=r.key,
                    title=r.title,
                    clause_type=r.clause_type,
                    role=r.role,
                    severity=r.severity,
                    enabled=True,
                    params=dict(r.params),
                    risk=r.risk,
                    suggest=r.suggest,
                    citations=list(r.citations),
                    draft=True,
                )
            )
            changed = True
    if changed:
        session.commit()


# ---- settings ------------------------------------------------------------------------------------


def get_settings(session: Session) -> dict[str, Any]:
    out = json.loads(json.dumps(playbook.DEFAULT_SETTINGS))
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is not None:
        try:
            saved = json.loads(row.value)
        except ValueError:
            saved = {}
        for k in out:
            if k in saved:
                out[k] = saved[k]
    return out


def save_settings(session: Session, person: str, values: dict[str, Any]) -> dict[str, Any]:
    person = _named(person)
    cur = get_settings(session)
    for k in ("approved_laws", "approved_forums"):
        if k in values:
            if not isinstance(values[k], list) or not all(isinstance(v, str) for v in values[k]):
                raise LegalError(f"{k} must be a list of names")
            cur[k] = [v.strip().lower() for v in values[k] if v.strip()]
    if "weights" in values:
        w = values["weights"]
        if (
            not isinstance(w, dict)
            or set(w) != {"red", "yellow", "info"}
            or not all(isinstance(v, int) and 0 <= v <= 1000 for v in w.values())
        ):
            raise LegalError("weights need whole numbers from 0 to 1000 for red, yellow and info")
        cur["weights"] = w
    if "require_signoff" in values:
        cur["require_signoff"] = bool(values["require_signoff"])
    text = json.dumps(cur)
    row = session.get(AppSetting, SETTINGS_KEY)
    if row is None:
        session.add(AppSetting(key=SETTINGS_KEY, value=text, secret=False, updated_by=person))
    else:
        row.value, row.updated_by = text, person
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="legal.settings",
            payload={"require_signoff": cur["require_signoff"]},
        )
    )
    session.commit()
    return cur


# ---- norm base -----------------------------------------------------------------------------------


def source_row(s: LegalSource) -> dict[str, Any]:
    return {
        "key": s.key,
        "jurisdiction": s.jurisdiction,
        "jurisdiction_name": JURISDICTIONS.get(s.jurisdiction, s.jurisdiction),
        "kind": s.kind,
        "title": s.title,
        "short": s.short,
        "ref": s.ref,
        "topics": s.topics,
        "fetch": s.fetch,
        "source_url": s.source_url,
        "note": s.note,
        "status": s.status,
        "provision_count": s.provision_count,
        "loaded_at": s.loaded_at,
        "loaded_by": s.loaded_by,
        "text_hash": s.text_hash,
        "check_name": s.jurisdiction in ("RS", "CN", "AE"),
    }


def sources(session: Session) -> dict[str, Any]:
    ensure_seed(session)
    rows = session.scalars(select(LegalSource).order_by(LegalSource.jurisdiction, LegalSource.key)).all()
    loaded = sum(1 for s in rows if s.status == "loaded")
    return {
        "total": len(rows),
        "loaded": loaded,
        "articles": sum(s.provision_count for s in rows),
        "jurisdictions": JURISDICTIONS,
        "sources": [source_row(s) for s in rows],
    }


def provisions(session: Session, key: str) -> dict[str, Any]:
    s = session.get(LegalSource, key)
    if s is None:
        raise LookupError("unknown act")
    items = session.scalars(
        select(LegalProvision).where(LegalProvision.source_key == key).order_by(LegalProvision.position)
    ).all()
    return {
        **source_row(s),
        "provisions": [{"number": p.number, "heading": p.heading, "text": p.text} for p in items],
    }


def search(
    session: Session, q: str, jurisdiction: str | None = None, limit: int = 30
) -> list[dict[str, Any]]:
    q = q.strip()
    if len(q) < 3:
        raise LegalError("type at least 3 characters")
    like = f"%{q.lower()}%"
    stmt = (
        select(LegalProvision, LegalSource)
        .join(LegalSource, LegalSource.key == LegalProvision.source_key)
        .where(or_(func.lower(LegalProvision.text).like(like), func.lower(LegalProvision.heading).like(like)))
        .order_by(LegalSource.key, LegalProvision.position)
        .limit(min(limit, 100))
    )
    if jurisdiction:
        stmt = stmt.where(LegalSource.jurisdiction == jurisdiction)
    out = []
    for p, s in session.execute(stmt):
        i = p.text.lower().find(q.lower())
        excerpt = p.text[max(0, i - 120) : i + 240] if i >= 0 else p.text[:300]
        out.append(
            {
                "source": s.key,
                "short": s.short,
                "jurisdiction": s.jurisdiction,
                "number": p.number,
                "heading": p.heading,
                "excerpt": excerpt,
            }
        )
    return out


def citation(session: Session, cit: dict[str, Any]) -> dict[str, Any]:
    """A rule's reference with the base's answer: is the act loaded, and does the article exist there."""
    s = session.get(LegalSource, cit["source"])
    out = {
        "source": cit["source"],
        "article": cit.get("article"),
        "short": s.short if s else cit["source"],
        "title": s.title if s else "",
        "jurisdiction": s.jurisdiction if s else "",
        "heading": "",
        "excerpt": "",
    }
    if s is None or s.status != "loaded":
        return {**out, "status": "not_loaded"}
    if not cit.get("article"):
        return {**out, "status": "verified"}
    p = session.scalar(
        select(LegalProvision).where(
            LegalProvision.source_key == s.key, LegalProvision.number == str(cit["article"]).lower()
        )
    )
    if p is None:
        return {**out, "status": "article_missing"}
    return {**out, "status": "verified", "heading": p.heading, "excerpt": p.text[:500]}


# ---- Incoterms -----------------------------------------------------------------------------------


def incoterm_list(session: Session) -> dict[str, Any]:
    ensure_seed(session)
    rows = session.scalars(select(LegalIncoterm).order_by(LegalIncoterm.code)).all()
    order = {c: i for i, c in enumerate(incoterms.CODES)}
    rows = sorted(rows, key=lambda r: order.get(r.code, 99))
    return {
        "version": incoterms.VERSION,
        "topics": [{"key": k, "label": v} for k, v in incoterms.TOPICS],
        "rules": [r.data for r in rows],
        "not_covered": incoterms.NOT_COVERED,
    }


# ---- playbook ------------------------------------------------------------------------------------


def rule_row(r: LegalRule) -> dict[str, Any]:
    return {c.name: getattr(r, c.name) for c in r.__table__.columns}


def rules(session: Session) -> list[dict[str, Any]]:
    ensure_seed(session)
    order = {r.key: i for i, r in enumerate(playbook.RULES)}
    rows = sorted(session.scalars(select(LegalRule)).all(), key=lambda r: order.get(r.key, 999))
    return [{**rule_row(r), "citations_checked": [citation(session, c) for c in r.citations]} for r in rows]


def update_rule(session: Session, person: str, key: str, values: dict[str, Any]) -> dict[str, Any]:
    person = _named(person)
    r = session.get(LegalRule, key)
    if r is None:
        raise LookupError("unknown rule")
    if "enabled" in values:
        r.enabled = bool(values["enabled"])
    if "severity" in values:
        if values["severity"] not in playbook.SEVERITIES:
            raise LegalError("severity must be red, yellow or info")
        r.severity = values["severity"]
    if "params" in values:
        base = playbook.get_rule(key)
        new = values["params"]
        if not isinstance(new, dict) or set(new) - set(base.params if base else {}):
            raise LegalError("unknown setting for this rule")
        for k, v in new.items():
            ref = base.params[k]
            if isinstance(ref, list):
                if not isinstance(v, list):
                    raise LegalError(f"{k} must be a list")
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                raise LegalError(f"{k} must be a number, zero or more")
        r.params = {**r.params, **new}
    if "draft" in values:
        r.draft = bool(values["draft"])
    for f in ("risk", "suggest"):
        if f in values and isinstance(values[f], str) and values[f].strip():
            setattr(r, f, values[f].strip())
    r.updated_by = person
    session.add(AuditLog(actor="human", actor_id=person, action="legal.rule", payload={"rule": key}))
    session.commit()
    return rule_row(r)


# ---- contracts -----------------------------------------------------------------------------------


def create_contract(
    session: Session,
    person: str,
    *,
    title: str,
    counterparty: str,
    role: str,
    text: str,
    filename: str = "",
    request_id: int | None = None,
    ai_allowed: bool = False,
    expires_on: date | None = None,
) -> Contract:
    import hashlib

    person = _named(person)
    if role not in ("buy", "sell"):
        raise LegalError("role must be buy (we buy from them) or sell (we sell to them)")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < 40:
        raise LegalError("the contract text is empty or too short")
    if len(text) > MAX_TEXT:
        raise LegalError("the contract text is longer than 400,000 characters")
    if not title.strip():
        raise LegalError("give the contract a title")
    if request_id is not None and session.get(CustomerRequest, request_id) is None:
        raise LookupError("request not found")
    c = Contract(
        title=title.strip()[:300],
        counterparty=counterparty.strip()[:300],
        role=role,
        request_id=request_id,
        filename=filename[:300],
        text=text,
        text_hash=hashlib.sha256(text.encode()).hexdigest(),
        ai_allowed=ai_allowed,
        status="uploaded",
        score=0,
        created_by=person,
        expires_on=expires_on,
    )
    session.add(c)
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="legal.contract",
            payload={"title": c.title, "role": role, "chars": len(text)},
        )
    )
    session.commit()
    return c


def _weights(session: Session) -> dict[str, int]:
    return get_settings(session)["weights"]


def _score(session: Session, contract_id: int) -> int:
    w = _weights(session)
    rows = session.execute(
        select(ContractFinding.severity, func.count())
        .where(ContractFinding.contract_id == contract_id, ContractFinding.state.in_(OPEN_STATES))
        .group_by(ContractFinding.severity)
    )
    return sum(w.get(sev, 0) * n for sev, n in rows)


def analyse(session: Session, person: str, contract_id: int) -> dict[str, Any]:
    """Read the contract with the rules. Decisions already taken on an unchanged remark are kept."""
    person = _named(person)
    ensure_seed(session)
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    settings = get_settings(session)
    old = {
        (f.rule_key, f.quote): f
        for f in session.scalars(
            select(ContractFinding).where(ContractFinding.contract_id == c.id, ContractFinding.by == "rules")
        )
    }
    kept = {k: (f.state, f.decided_by, f.decided_at, f.note) for k, f in old.items() if f.state != "open"}
    for f in session.scalars(select(ContractFinding).where(ContractFinding.contract_id == c.id)):
        f.clause_id = None
    for f in old.values():
        session.delete(f)
    for cl in session.scalars(select(ContractClause).where(ContractClause.contract_id == c.id)):
        session.delete(cl)
    session.flush()

    clauses = analysis.analyse(c.text)
    rows: dict[int, ContractClause] = {}
    for cl in clauses:
        row = ContractClause(
            contract_id=c.id,
            position=cl.position,
            heading=cl.heading[:200],
            text=cl.text,
            clause_type=cl.clause_type,
            types=cl.types,
            facts=cl.facts,
        )
        session.add(row)
        rows[cl.position] = row
    session.flush()

    made, seen = 0, set()
    for r in session.scalars(select(LegalRule).where(LegalRule.enabled.is_(True))):
        if r.role not in ("both", c.role) or r.key not in playbook.CHECKS:
            continue
        ctx = playbook.Ctx(role=c.role, text=c.text, clauses=clauses, params=r.params, settings=settings)
        for h in playbook.CHECKS[r.key](ctx):
            quote = h.quote.strip()
            if quote and quote not in c.text:
                quote = ""  # never show a quote that is not in the contract
            ident = (r.key, quote, h.extra)
            if ident in seen:
                continue
            seen.add(ident)
            f = ContractFinding(
                contract_id=c.id,
                clause_id=rows[h.clause.position].id if h.clause else None,
                rule_key=r.key,
                severity=h.severity or r.severity,
                title=f"{r.title}: {h.extra}" if h.extra else r.title,
                quote=quote,
                risk=h.risk or r.risk,
                suggest=r.suggest,
                citations=h.citations if h.citations is not None else list(r.citations),
                by="rules",
            )
            if (r.key, quote) in kept:
                f.state, f.decided_by, f.decided_at, f.note = kept[(r.key, quote)]
            session.add(f)
            made += 1
    c.status, c.analysed_at = "analysed", datetime.now(UTC)
    session.flush()
    c.score = _score(session, c.id)
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="legal.analysed",
            payload={"contract": c.id, "findings": made, "score": c.score},
        )
    )
    session.commit()
    return contract_view(session, c.id)


def decide(session: Session, person: str, finding_id: int, state: str, note: str = "") -> dict[str, Any]:
    person = _named(person)
    f = session.get(ContractFinding, finding_id)
    if f is None:
        raise LookupError("remark not found")
    if state not in STATES:
        raise LegalError("state must be open, accepted, dismissed or to_lawyer")
    f.state, f.note = state, note.strip()
    f.decided_by, f.decided_at = (None, None) if state == "open" else (person, datetime.now(UTC))
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="legal.decision",
            payload={"finding": f.id, "contract": f.contract_id, "state": state},
        )
    )
    session.flush()
    c = session.get(Contract, f.contract_id)
    c.score = _score(session, c.id)
    session.commit()
    return finding_view(session, f)


def finding_view(session: Session, f: ContractFinding) -> dict[str, Any]:
    d = {c.name: getattr(f, c.name) for c in f.__table__.columns}
    d["citations"] = [citation(session, ct) for ct in f.citations]
    return d


def counts(session: Session, contract_id: int) -> dict[str, int]:
    out = {"red": 0, "yellow": 0, "info": 0, "open": 0}
    for sev, state, n in session.execute(
        select(ContractFinding.severity, ContractFinding.state, func.count())
        .where(ContractFinding.contract_id == contract_id)
        .group_by(ContractFinding.severity, ContractFinding.state)
    ):
        if state in OPEN_STATES:
            out[sev] += n
            out["open"] += n
    return out


def contract_row(c: Contract, session: Session) -> dict[str, Any]:
    d = {col.name: getattr(c, col.name) for col in c.__table__.columns if col.name != "text"}
    d["chars"] = len(c.text)
    d["counts"] = counts(session, c.id)
    return d


def contract_view(session: Session, contract_id: int) -> dict[str, Any]:
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    clauses = session.scalars(
        select(ContractClause).where(ContractClause.contract_id == c.id).order_by(ContractClause.position)
    ).all()
    findings = session.scalars(select(ContractFinding).where(ContractFinding.contract_id == c.id)).all()
    rank = {"red": 0, "yellow": 1, "info": 2}
    findings = sorted(findings, key=lambda f: (f.state not in OPEN_STATES, rank[f.severity], f.id))
    by_clause: dict[int, list[int]] = {}
    for f in findings:
        if f.clause_id:
            by_clause.setdefault(f.clause_id, []).append(f.id)
    return {
        **contract_row(c, session),
        "text": c.text,
        "summary": summary(clauses),
        "clauses": [
            {
                "id": cl.id,
                "position": cl.position,
                "heading": cl.heading,
                "text": cl.text,
                "clause_type": cl.clause_type,
                "types": cl.types,
                "findings": by_clause.get(cl.id, []),
            }
            for cl in clauses
        ],
        "findings": [finding_view(session, f) for f in findings],
    }


def summary(clauses: list[ContractClause]) -> dict[str, Any]:
    """The key terms found, for the first screen and the portfolio table."""

    def first(kind: str):
        for cl in clauses:
            if cl.facts.get(kind):
                return cl.facts[kind][0]["value"]
        return None

    terms = []
    for cl in clauses:
        for f in cl.facts.get("incoterm", []):
            v = f["value"]
            label = f"{v['code']} {v['place']}".strip()
            if label not in terms:
                terms.append(label)
    forum = first("forum")
    return {
        "payment_days": first("payment_days"),
        "law": first("law"),
        "forum": (
            f"{forum['kind']}: {forum.get('place') or forum.get('rules') or ''}".strip() if forum else None
        ),
        "incoterms": terms,
        "warranty_months": first("warranty_months"),
        "auto_renewal": bool(first("renewal")),
        "cisg_excluded": bool(first("cisg_excluded")),
    }


def contracts(session: Session, request_id: int | None = None) -> list[dict[str, Any]]:
    stmt = select(Contract).order_by(Contract.id.desc())
    if request_id is not None:
        stmt = stmt.where(Contract.request_id == request_id)
    out = []
    for c in session.scalars(stmt):
        d = contract_row(c, session)
        cls = session.scalars(select(ContractClause).where(ContractClause.contract_id == c.id)).all()
        d["summary"] = summary(cls)
        out.append(d)
    return out


def delete_contract(session: Session, person: str, contract_id: int) -> None:
    person = _named(person)
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    # children first, in this order: the tables have no ORM relations, so Postgres would see them out of order
    session.execute(delete(ContractFinding).where(ContractFinding.contract_id == c.id))
    session.execute(delete(ContractClause).where(ContractClause.contract_id == c.id))
    session.add(
        AuditLog(
            actor="human",
            actor_id=person,
            action="legal.deleted",
            payload={"contract": c.id, "title": c.title},
        )
    )
    session.delete(c)
    session.commit()


def update_contract(
    session: Session, person: str, contract_id: int, values: dict[str, Any]
) -> dict[str, Any]:
    person = _named(person)
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    if "request_id" in values:
        rid = values["request_id"]
        if rid is not None and session.get(CustomerRequest, rid) is None:
            raise LookupError("request not found")
        c.request_id = rid
    if "ai_allowed" in values:
        c.ai_allowed = bool(values["ai_allowed"])
    if "expires_on" in values:
        c.expires_on = date.fromisoformat(values["expires_on"]) if values["expires_on"] else None
    for f in ("title", "counterparty"):
        if f in values and str(values[f]).strip():
            setattr(c, f, str(values[f]).strip()[:300])
    if "role" in values:
        if values["role"] not in ("buy", "sell"):
            raise LegalError("role must be buy or sell")
        c.role = values["role"]
    session.add(
        AuditLog(actor="human", actor_id=person, action="legal.contract.updated", payload={"contract": c.id})
    )
    session.commit()
    return contract_row(c, session)


# ---- the optional AI read ------------------------------------------------------------------------


def ai_preview(session: Session, settings: Settings, contract_id: int) -> dict[str, Any]:
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    sent = min(len(c.text), AI_MAX_CHARS)
    return {
        "enabled": ai_enabled(settings),
        "allowed": c.ai_allowed,
        "chars_sent": sent,
        "cut": len(c.text) > AI_MAX_CHARS,
        "approx_tokens": sent // 4,
    }


def review_ai(session: Session, settings: Settings, person: str, contract_id: int) -> dict[str, Any]:
    """Ask the model for extra remarks. Only a quote that is really in the contract is kept; the rest is dropped."""
    person = _named(person)
    c = session.get(Contract, contract_id)
    if c is None:
        raise LookupError("contract not found")
    if not c.ai_allowed:
        raise LegalError("AI reading is switched off for this contract; switch it on for this contract first")
    if not ai_enabled(settings):
        raise LegalError("AI is not set up (no Anthropic key)")
    if c.status != "analysed":
        raise LegalError("run the rule check first, so the model does not repeat it")
    checked = "\n".join(
        f"- {r.title}" for r in session.scalars(select(LegalRule).where(LegalRule.enabled.is_(True)))
    )
    role_text = "we buy from the other party" if c.role == "buy" else "we sell to the other party"
    result, note = run_task(
        session,
        settings,
        "contract_review",
        {"role": c.role, "role_text": role_text, "checked": checked, "text": c.text[:AI_MAX_CHARS]},
        ContractReview,
    )
    if result is None:
        return {
            "added": 0,
            "dropped": 0,
            "note": note or "AI is off",
            "contract": contract_view(session, c.id),
        }
    flat = re.sub(r"\s+", " ", c.text)
    added = dropped = 0
    for f in session.scalars(
        select(ContractFinding).where(ContractFinding.contract_id == c.id, ContractFinding.by == "ai")
    ):
        if f.state == "open":
            session.delete(f)
    for a in result.parsed.findings[:25]:
        q = a.quote.strip()
        if len(q) < 12 or re.sub(r"\s+", " ", q) not in flat:
            dropped += 1
            continue
        clause = session.scalars(select(ContractClause).where(ContractClause.contract_id == c.id)).all()
        cid = next((cl.id for cl in clause if re.sub(r"\s+", " ", q) in re.sub(r"\s+", " ", cl.text)), None)
        session.add(
            ContractFinding(
                contract_id=c.id,
                clause_id=cid,
                rule_key="ai",
                severity=a.severity,
                title=a.title[:300],
                quote=q,
                risk=a.risk,
                suggest=a.suggest,
                citations=[],
                by="ai",
            )
        )
        added += 1
    c.ai_model = result.model
    session.flush()
    c.score = _score(session, c.id)
    session.add(
        AuditLog(
            actor="system",
            action="legal.ai_review",
            payload={
                "contract": c.id,
                "added": added,
                "dropped": dropped,
                "model": result.model,
                "by": person,
            },
        )
    )
    session.commit()
    return {"added": added, "dropped": dropped, "note": None, "contract": contract_view(session, c.id)}


# ---- sign-off gate and request summary ------------------------------------------------------------


def request_summary(session: Session, request_id: int) -> dict[str, Any]:
    cs = session.scalars(select(Contract).where(Contract.request_id == request_id)).all()
    red = sum(counts(session, c.id)["red"] for c in cs)
    return {
        "contracts": [
            {
                "id": c.id,
                "title": c.title,
                "counterparty": c.counterparty,
                "score": c.score,
                "status": c.status,
                "counts": counts(session, c.id),
            }
            for c in cs
        ],
        "open_red": red,
        "require_signoff": get_settings(session)["require_signoff"],
    }


def blocker(session: Session, request_id: int) -> str | None:
    """A reason to stop the purchase order, only when the company switched the sign-off rule on."""
    if not get_settings(session)["require_signoff"]:
        return None
    s = request_summary(session, request_id)
    if s["open_red"]:
        return f"{s['open_red']} red remark(s) on a linked contract are still open: accept, dismiss or hand them to the lawyer first"
    return None


# ---- reports -------------------------------------------------------------------------------------

_SEV = {"red": "RED", "yellow": "YELLOW", "info": "INFO"}


def report_markdown(session: Session, contract_id: int) -> str:
    v = contract_view(session, contract_id)
    lines = [
        f"# Contract review: {v['title']}",
        "",
        f"Counterparty: {v['counterparty'] or '-'} · our side: {'buyer' if v['role'] == 'buy' else 'seller'} · risk score {v['score']} · "
        f"open: {v['counts']['red']} red, {v['counts']['yellow']} yellow, {v['counts']['info']} info",
        "",
        "This list comes from fixed rules (and an optional AI read) and is not legal advice. A person decides.",
        "",
    ]
    for f in v["findings"]:
        norms = (
            "; ".join(
                f"{c['short']}{' Art. ' + str(c['article']) if c['article'] else ''} ({c['status'].replace('_', ' ')})"
                for c in f["citations"]
            )
            or "none attached"
        )
        lines += [
            f"## [{_SEV[f['severity']]}] {f['title']}",
            f"- Clause says: {f['quote'] or '(nothing found in the text)'}",
            f"- Risk: {f['risk']}",
            f"- Ask for: {f['suggest']}",
            f"- Norms: {norms}",
            f"- Decision: {f['state']}{' by ' + f['decided_by'] if f['decided_by'] else ''}{' - ' + f['note'] if f['note'] else ''}",
            "",
        ]
    return "\n".join(lines)


def report_xlsx(session: Session, contract_id: int) -> bytes:
    from openpyxl import Workbook

    v = contract_view(session, contract_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "Remarks"
    ws.append(
        [
            "Severity",
            "Remark",
            "Clause says",
            "Risk",
            "Ask for",
            "Norms",
            "Decision",
            "Decided by",
            "Note",
            "Found by",
        ]
    )
    for f in v["findings"]:
        norms = "; ".join(
            f"{c['short']}{' Art. ' + str(c['article']) if c['article'] else ''} ({c['status'].replace('_', ' ')})"
            for c in f["citations"]
        )
        ws.append(
            [
                f["severity"],
                f["title"],
                f["quote"],
                f["risk"],
                f["suggest"],
                norms,
                f["state"],
                f["decided_by"] or "",
                f["note"],
                f["by"],
            ]
        )
    for col, w in zip("ABCDEFGHIJ", (9, 44, 60, 60, 60, 36, 11, 14, 30, 8), strict=True):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---- portfolio -----------------------------------------------------------------------------------


def portfolio(session: Session) -> dict[str, Any]:
    cs = session.scalars(select(Contract).order_by(Contract.id)).all()
    today = date.today()
    table, rule_count, by_party = [], Counter(), {}
    for c in cs:
        cls = session.scalars(select(ContractClause).where(ContractClause.contract_id == c.id)).all()
        s = summary(cls)
        cnt = counts(session, c.id)
        table.append(
            {
                "id": c.id,
                "title": c.title,
                "counterparty": c.counterparty,
                "role": c.role,
                "score": c.score,
                "status": c.status,
                "expires_on": c.expires_on,
                "red": cnt["red"],
                "yellow": cnt["yellow"],
                **s,
            }
        )
        seen: set[tuple[str, str]] = set()  # one count per contract, however many times a rule fired
        for f in session.scalars(
            select(ContractFinding).where(
                ContractFinding.contract_id == c.id, ContractFinding.state.in_(OPEN_STATES)
            )
        ):
            seen.add((f.rule_key, f.title.split(":")[0]))
        rule_count.update(seen)
        by_party.setdefault(c.counterparty or "(no name)", []).append(c.score)
    soon = [t for t in table if t["expires_on"] and today <= t["expires_on"] <= today + timedelta(days=90)]
    renewing = [t for t in table if t["auto_renewal"]]
    days = [t["payment_days"] for t in table if t["payment_days"] is not None]
    return {
        "contracts": len(cs),
        "analysed": sum(1 for c in cs if c.status == "analysed"),
        "open_red": sum(t["red"] for t in table),
        "open_yellow": sum(t["yellow"] for t in table),
        "average_payment_days": round(sum(days) / len(days), 1) if days else None,
        "bottlenecks": [{"rule": r, "title": t, "contracts": n} for (r, t), n in rule_count.most_common(8)],
        "expiring_90_days": [
            {"id": t["id"], "title": t["title"], "expires_on": t["expires_on"]} for t in soon
        ],
        "auto_renewing": [{"id": t["id"], "title": t["title"]} for t in renewing],
        "counterparties": sorted(
            (
                {"counterparty": k, "contracts": len(v), "average_score": round(sum(v) / len(v), 1)}
                for k, v in by_party.items()
            ),
            key=lambda x: -x["average_score"],
        ),
        "table": table,
    }

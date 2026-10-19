# ruff: noqa: E501
import base64
import binascii
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.legal import loader
from app.legal import service as svc

router = APIRouter(tags=["legal"])

# Replaced in tests so the fetch talks to a scripted site instead of the internet.
TRANSPORT = None
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_B64 = loader.MAX_BYTES * 4 // 3 + 16


def guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (svc.LegalError, loader.LoadError) as exc:
        raise HTTPException(409, str(exc)) from exc


class ByIn(BaseModel):
    by: str


class FileIn(BaseModel):
    filename: str
    content_base64: str
    by: str


class SettingsIn(BaseModel):
    changed_by: str
    values: dict


class RuleIn(BaseModel):
    changed_by: str
    values: dict


class ContractIn(BaseModel):
    by: str
    title: str
    counterparty: str = ""
    role: str
    text: str = ""
    filename: str = ""
    content_base64: str | None = None
    request_id: int | None = None
    ai_allowed: bool = False
    expires_on: date | None = None


class ContractPatch(BaseModel):
    by: str
    values: dict


class DecisionIn(BaseModel):
    state: str
    note: str = ""
    by: str


def _bytes(b64: str) -> bytes:
    if len(b64) > MAX_UPLOAD_B64:
        raise HTTPException(413, "file too large")
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "content_base64 is not valid base64") from exc


@router.get("/legal/sources")
def sources(session: Session = Depends(get_session)):
    return svc.sources(session)


@router.get("/legal/sources/{key}")
def source(key: str, session: Session = Depends(get_session)):
    svc.ensure_seed(session)
    return guard(svc.provisions, session, key)


@router.post("/legal/sources/{key}/fetch")
def fetch_source(key: str, body: ByIn, session: Session = Depends(get_session)):
    svc.ensure_seed(session)
    by = guard(svc._named, body.by)
    n = guard(loader.load_source, session, key, by, TRANSPORT)
    return {"articles": n, "source": guard(svc.provisions, session, key)}


@router.post("/legal/sources/{key}/upload")
def upload_source(key: str, body: FileIn, session: Session = Depends(get_session)):
    svc.ensure_seed(session)
    by = guard(svc._named, body.by)
    n = guard(loader.load_file, session, key, _bytes(body.content_base64), body.filename, by)
    return {"articles": n, "source": guard(svc.provisions, session, key)}


@router.get("/legal/search")
def search(q: str, jurisdiction: str | None = None, session: Session = Depends(get_session)):
    return guard(svc.search, session, q, jurisdiction)


@router.get("/legal/incoterms")
def incoterms(session: Session = Depends(get_session)):
    return svc.incoterm_list(session)


@router.get("/legal/rules")
def rules(session: Session = Depends(get_session)):
    return svc.rules(session)


@router.patch("/legal/rules/{key}")
def patch_rule(key: str, body: RuleIn, session: Session = Depends(get_session)):
    svc.ensure_seed(session)
    return guard(svc.update_rule, session, body.changed_by, key, body.values)


@router.get("/legal/settings")
def get_legal_settings(session: Session = Depends(get_session)):
    return svc.get_settings(session)


@router.put("/legal/settings")
def put_legal_settings(body: SettingsIn, session: Session = Depends(get_session)):
    return guard(svc.save_settings, session, body.changed_by, body.values)


@router.get("/legal/contracts")
def contracts(request_id: int | None = None, session: Session = Depends(get_session)):
    return svc.contracts(session, request_id)


@router.post("/legal/contracts")
def create_contract(body: ContractIn, session: Session = Depends(get_session)):
    text = body.text
    if body.content_base64:
        text = guard(loader.to_text, _bytes(body.content_base64), body.filename)
    c = guard(
        svc.create_contract,
        session,
        body.by,
        title=body.title,
        counterparty=body.counterparty,
        role=body.role,
        text=text,
        filename=body.filename,
        request_id=body.request_id,
        ai_allowed=body.ai_allowed,
        expires_on=body.expires_on,
    )
    return guard(svc.analyse, session, body.by, c.id)


@router.get("/legal/contracts/{contract_id}")
def contract(contract_id: int, session: Session = Depends(get_session)):
    return guard(svc.contract_view, session, contract_id)


@router.patch("/legal/contracts/{contract_id}")
def patch_contract(contract_id: int, body: ContractPatch, session: Session = Depends(get_session)):
    return guard(svc.update_contract, session, body.by, contract_id, body.values)


@router.delete("/legal/contracts/{contract_id}")
def delete_contract(contract_id: int, by: str, session: Session = Depends(get_session)):
    guard(svc.delete_contract, session, by, contract_id)
    return {"deleted": contract_id}


@router.post("/legal/contracts/{contract_id}/analyse")
def analyse(contract_id: int, body: ByIn, session: Session = Depends(get_session)):
    return guard(svc.analyse, session, body.by, contract_id)


@router.post("/legal/findings/{finding_id}/decision")
def decision(finding_id: int, body: DecisionIn, session: Session = Depends(get_session)):
    return guard(svc.decide, session, body.by, finding_id, body.state, body.note)


@router.get("/legal/contracts/{contract_id}/ai-preview")
def ai_preview(
    contract_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guard(svc.ai_preview, session, settings, contract_id)


@router.post("/legal/contracts/{contract_id}/ai-review")
def ai_review(
    contract_id: int,
    body: ByIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guard(svc.review_ai, session, settings, body.by, contract_id)


@router.get("/legal/contracts/{contract_id}/report.md")
def report_md(contract_id: int, session: Session = Depends(get_session)):
    text = guard(svc.report_markdown, session, contract_id)
    return Response(
        text,
        media_type="text/markdown",
        headers={"content-disposition": f'attachment; filename="contract-{contract_id}-review.md"'},
    )


@router.get("/legal/contracts/{contract_id}/report.xlsx")
def report_xlsx(contract_id: int, session: Session = Depends(get_session)):
    data = guard(svc.report_xlsx, session, contract_id)
    return Response(
        data,
        media_type=XLSX,
        headers={"content-disposition": f'attachment; filename="contract-{contract_id}-review.xlsx"'},
    )


@router.get("/legal/portfolio")
def portfolio(session: Session = Depends(get_session)):
    return svc.portfolio(session)


@router.get("/requests/{request_id}/legal")
def request_legal(request_id: int, session: Session = Depends(get_session)):
    return svc.request_summary(session, request_id)

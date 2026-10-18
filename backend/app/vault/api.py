from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.pipeline.api import guarded
from app.vault import service as svc

router = APIRouter(prefix="/vault", tags=["vault"])


class EntryIn(BaseModel):
    category: str
    name: str
    site_url: str | None = None
    login: str
    password: str
    comments: str | None = None
    supplier_id: int | None = None
    changed_by: str


class EntryPatch(BaseModel):
    category: str | None = None
    name: str | None = None
    site_url: str | None = None
    login: str | None = None
    password: str | None = None
    comments: str | None = None
    changed_by: str


class WhoIn(BaseModel):
    person: str


class RequestIn(BaseModel):
    requested_by: str
    reason: str


class DecisionIn(BaseModel):
    decided_by: str
    approve: bool
    comment: str = ""


@router.post("/open")
def open_vault(body: WhoIn, session: Session = Depends(get_session)):
    guarded(svc.open_vault, session, body.person)
    return {"ok": True}


@router.get("")
def entries(session: Session = Depends(get_session)):
    return {"categories": list(svc.CATEGORIES), "entries": svc.list_entries(session)}


@router.post("")
def add(body: EntryIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    data = body.model_dump(exclude={"changed_by"})
    return guarded(svc.add_entry, session, data, body.changed_by, settings)


@router.patch("/{entry_id}")
def update(
    entry_id: int,
    body: EntryPatch,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    data = body.model_dump(exclude={"changed_by"}, exclude_none=True)
    return guarded(svc.update_entry, session, entry_id, data, body.changed_by, settings)


@router.delete("/{entry_id}")
def delete(entry_id: int, changed_by: str, session: Session = Depends(get_session)):
    guarded(svc.delete_entry, session, entry_id, changed_by)
    return {"ok": True}


@router.post("/{entry_id}/requests")
def request_view(entry_id: int, body: RequestIn, session: Session = Depends(get_session)):
    return guarded(svc.request_view, session, entry_id, body.requested_by, body.reason)


@router.get("/requests")
def requests(status: str = "", session: Session = Depends(get_session)):
    return svc.list_requests(session, status)


@router.post("/requests/{request_id}/decide")
def decide(request_id: int, body: DecisionIn, session: Session = Depends(get_session)):
    return guarded(svc.decide, session, request_id, body.decided_by, body.approve, body.comment)


@router.post("/requests/{request_id}/reveal")
def reveal(
    request_id: int,
    body: WhoIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(svc.reveal, session, request_id, body.person, settings)


@router.get("/log")
def log(limit: int = 100, session: Session = Depends(get_session)):
    return svc.log_rows(session, limit)

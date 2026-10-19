import base64
import binascii

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import CustomerRequest, ExternalTask
from app.pipeline.api import guarded
from app.pipeline.service import PipelineError, _ref
from app.worktasks import config as conf
from app.worktasks import service as svc
from app.worktasks.providers import ProviderError

router = APIRouter(tags=["tasks"])

# Replaced in tests so the Bitrix24 client talks to a scripted portal instead of the internet.
TRANSPORT = None
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ConfigIn(BaseModel):
    changed_by: str
    config: dict


class WebhookIn(BaseModel):
    changed_by: str
    url: str | None = None


class ByIn(BaseModel):
    by: str


class StateIn(BaseModel):
    state: str
    by: str


class ImportIn(BaseModel):
    filename: str
    content_base64: str
    by: str


def _view(session: Session, settings: Settings) -> dict:
    url = conf.webhook(session, settings)
    return {
        "config": conf.load(session).model_dump(),
        "webhook": {"set": bool(url), "hint": ("…" + url.rstrip("/")[-4:]) if url else None},
        "states": list(conf.STATES),
        "stages": list(conf.STAGES),
        "defaults": conf.default_config().model_dump(),
    }


def _provider(session: Session, settings: Settings):
    return svc.provider_for(session, settings, conf.load(session), TRANSPORT)


def _remote(fn):
    try:
        return fn()
    except ProviderError as exc:
        raise PipelineError(str(exc)) from exc


@router.get("/tasks/config")
def read_config(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    return _view(session, settings)


@router.put("/tasks/config")
def save_config(
    body: ConfigIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    guarded(conf.save, session, body.changed_by, body.config)
    return _view(session, settings)


@router.put("/tasks/webhook")
def save_webhook(
    body: WebhookIn, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    guarded(conf.set_webhook, session, settings, body.changed_by, body.url)
    return _view(session, settings)


@router.post("/tasks/test")
def test_connection(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    def run():
        return {"ok": True, "detail": _remote(lambda: _provider(session, settings).ping())}

    return guarded(run)


@router.get("/tasks/directory")
def directory(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    return guarded(lambda: _remote(lambda: _provider(session, settings).directory()))


@router.get("/tasks")
def overview(session: Session = Depends(get_session)):
    """Every request that has tasks, with its overall progress."""
    cfg = conf.load(session)
    ids = list(session.scalars(select(ExternalTask.request_id).distinct().order_by(ExternalTask.request_id)))
    subjects = {
        r.id: r.subject for r in session.scalars(select(CustomerRequest).where(CustomerRequest.id.in_(ids)))
    }
    out = []
    for rid in ids:
        t = svc.tree(session, cfg, rid)
        out.append(
            {
                "request_id": rid,
                "ref": _ref(rid),
                "subject": subjects.get(rid, ""),
                "progress": t["progress"],
                "count": t["count"],
                "app_stage": t["app_stage"],
            }
        )
    total = session.scalar(select(func.count()).select_from(ExternalTask)) or 0
    return {"requests": out, "tasks": total, "provider": cfg.provider}


@router.get("/requests/{request_id}/tasks/plan")
def plan(request_id: int, session: Session = Depends(get_session)):
    return guarded(lambda: svc.plan(session, conf.load(session), request_id))


@router.get("/requests/{request_id}/tasks")
def tree(request_id: int, session: Session = Depends(get_session)):
    return guarded(lambda: svc.tree(session, conf.load(session), request_id))


@router.post("/requests/{request_id}/tasks")
def create(
    request_id: int,
    body: ByIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    return guarded(svc.create_tasks, session, settings, conf.load(session), request_id, body.by, TRANSPORT)


@router.post("/requests/{request_id}/tasks/sync")
def sync_request(
    request_id: int, session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
):
    return guarded(svc.sync, session, settings, conf.load(session), request_id, TRANSPORT)


@router.post("/tasks/sync")
def sync_all(session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    return guarded(svc.sync, session, settings, conf.load(session), None, TRANSPORT)


@router.post("/requests/{request_id}/tasks/demo-advance")
def demo_advance(request_id: int, session: Session = Depends(get_session)):
    return guarded(svc.demo_advance, session, conf.load(session), request_id)


@router.post("/tasks/{task_id}/state")
def set_state(
    task_id: int,
    body: StateIn,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    task = guarded(
        svc.set_state, session, settings, conf.load(session), task_id, body.state, body.by, TRANSPORT
    )
    return {"id": task.id, "state": task.state}


@router.get("/requests/{request_id}/tasks/export.xlsx")
def export_request(request_id: int, session: Session = Depends(get_session)):
    data = guarded(svc.export_xlsx, session, conf.load(session), request_id)
    return Response(
        data,
        media_type=XLSX,
        headers={"content-disposition": f'attachment; filename="{_ref(request_id)}-tasks.xlsx"'},
    )


@router.get("/tasks/export.xlsx")
def export_all(session: Session = Depends(get_session)):
    data = guarded(svc.export_xlsx, session, conf.load(session), None)
    return Response(
        data, media_type=XLSX, headers={"content-disposition": 'attachment; filename="tasks.xlsx"'}
    )


@router.post("/tasks/import")
def import_file(body: ImportIn, session: Session = Depends(get_session)):
    def run():
        if len(body.content_base64) > 7_000_000:
            raise PipelineError("the file is larger than 5 MB")
        try:
            data = base64.b64decode(body.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise PipelineError("the file could not be decoded") from exc
        if not body.filename.lower().endswith((".xlsx", ".xlsm")):
            raise PipelineError("only .xlsx files are read; save the sheet as .xlsx")
        return svc.import_xlsx(session, conf.load(session), data, body.by)

    return guarded(run)

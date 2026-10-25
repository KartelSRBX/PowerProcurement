import base64
import binascii
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.duty import service

router = APIRouter(tags=["duties"])
MAX_CSV_BYTES = 30_000_000


def _guard(fn, *args):
    try:
        return fn(*args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except service.DutyError as exc:
        raise HTTPException(409, str(exc)) from exc


class CsvImportIn(BaseModel):
    content_base64: str
    source: str
    rate_date: date | None = None
    imported_by: str


@router.get("/duties/summary")
def summary(session: Session = Depends(get_session)):
    return service.summary(session)


@router.get("/duties/search")
def search(q: str = "", limit: int = 50, session: Session = Depends(get_session)):
    return service.search(session, q, limit)


@router.get("/duties/{code}")
def one(code: str, origin: str | None = None, session: Session = Depends(get_session)):
    row = _guard(service.get, session, code)
    return service._dump(row) | {"applicable": service.rates_for(row, origin)}


@router.post("/duties/import/csv")
def import_csv(body: CsvImportIn, session: Session = Depends(get_session)):
    def run():
        if len(body.content_base64) > MAX_CSV_BYTES * 4 // 3 + 16:
            raise service.DutyError(f"the file is larger than {MAX_CSV_BYTES // 1_000_000} MB")
        try:
            text = base64.b64decode(body.content_base64, validate=True).decode("utf-8")
        except (binascii.Error, ValueError) as exc:
            raise service.DutyError("the file could not be read as UTF-8 text") from exc
        lines = service.lines_from_csv(text)
        return service.import_lines(session, lines, body.source, body.rate_date, body.imported_by)

    return _guard(run)

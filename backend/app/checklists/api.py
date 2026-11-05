from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.checklists import service
from app.db import get_session
from app.pipeline.api import guarded

router = APIRouter(tags=["checklists"])


class StateIn(BaseModel):
    state: str
    note: str = Field(default="", max_length=300)
    set_by: str


@router.get("/checklists")
def checklists(session: Session = Depends(get_session)):
    """The draft CBAM and Serbian e-invoicing lists, each line with its source, and where the team stands."""
    return service.listing(session)


@router.put("/checklists/{key}")
def set_state(key: str, body: StateIn, session: Session = Depends(get_session)):
    return guarded(service.set_state, session, key, body.state, body.note, body.set_by)

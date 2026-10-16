import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.ai.base import AIResult
from app.config import Settings, get_settings
from app.db import Base, get_session
from app.intake import api
from app.intake.mailbox import InboundEmail
from app.intake.schemas import ParsedRequest, RequestItem
from app.intake.service import confirm_request, intake_email
from app.main import app
from app.models import AuditLog, CustomerRequest


@pytest.fixture
def session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class FixedAdapter:
    def __init__(self, **fields):
        self.calls = 0
        self.fields = {
            "is_request": True,
            "language": "en",
            "category": "electronics",
            "items": [RequestItem(description="resistor", quantity=10)],
            "confidence": 0.9,
            **fields,
        }

    def extract(self, prompt, variables, schema):
        self.calls += 1
        return AIResult(schema(**self.fields), "fixed", prompt.id, prompt.version)


def mail(message_id="<1@x>"):
    return InboundEmail(message_id, "a@b.c", "RFQ", "10 resistors please", datetime(2026, 10, 1, tzinfo=UTC))


SETTINGS = Settings(_env_file=None, ai_confidence_threshold=0.75)


def test_confident_request_is_parsed(session):
    row = intake_email(session, FixedAdapter(), SETTINGS, mail())
    assert row.status == "parsed" and row.parsed["items"][0]["quantity"] == 10
    assert row.prompt_version == "intake/v1"


def test_low_confidence_goes_to_review(session):
    assert intake_email(session, FixedAdapter(confidence=0.4), SETTINGS, mail()).status == "needs_review"


def test_non_request_is_not_treated_as_a_request(session):
    row = intake_email(session, FixedAdapter(is_request=False, items=[]), SETTINGS, mail())
    assert row.status == "not_request"


def test_same_message_is_not_parsed_twice(session):
    adapter = FixedAdapter()
    a = intake_email(session, adapter, SETTINGS, mail())
    b = intake_email(session, adapter, SETTINGS, mail())
    assert a.id == b.id and adapter.calls == 1


def test_confirmation_needs_a_named_person_and_is_audited(session):
    row = intake_email(session, FixedAdapter(confidence=0.4), SETTINGS, mail())
    with pytest.raises(ValueError):
        confirm_request(session, row.id, " ", None)
    fixed = ParsedRequest(
        is_request=True,
        language="en",
        category="electronics",
        items=[RequestItem(description="resistor", quantity=100)],
        confidence=1.0,
    )
    done = confirm_request(session, row.id, "kartel", fixed)
    assert done.status == "confirmed" and done.parsed["items"][0]["quantity"] == 100
    audit = session.scalars(select(AuditLog).where(AuditLog.action == "request.confirmed")).one()
    assert (audit.actor, audit.actor_id) == ("human", "kartel")


def test_api_round_trip(session, monkeypatch):
    monkeypatch.setattr(api, "make_adapter", lambda settings: FixedAdapter())
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    try:
        client = TestClient(app)
        body = {"message_id": "<9@x>", "sender": "a@b.c", "subject": "RFQ", "body": "10 resistors"}
        created = client.post("/requests/intake", json=body).json()
        assert created["status"] == "parsed"
        assert client.get("/requests").json()[0]["id"] == created["id"]
        assert client.post(f"/requests/{created['id']}/confirm", json={"confirmed_by": ""}).status_code == 422
        ok = client.post(f"/requests/{created['id']}/confirm", json={"confirmed_by": "kartel"})
        assert ok.json()["status"] == "confirmed"
        assert client.post("/requests/999/confirm", json={"confirmed_by": "k"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_explains_missing_recording_in_mock_mode(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, ai_provider="mock")
    try:
        r = TestClient(app).post(
            "/requests/intake", json={"message_id": "<m>", "sender": "a", "subject": "s", "body": "b"}
        )
        assert r.status_code == 409 and "no recorded answer" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_intake_against_real_postgres(pg_url):
    engine = create_engine(pg_url)
    mid = f"<pg-{uuid.uuid4()}@x>"  # unique, so other data in the database is never touched
    with Session(engine) as s:
        row = intake_email(s, FixedAdapter(), SETTINGS, mail(mid))
        assert row.status == "parsed"
        assert intake_email(s, FixedAdapter(), SETTINGS, mail(mid)).id == row.id
        s.query(CustomerRequest).filter_by(message_id=mid).delete()
        s.commit()

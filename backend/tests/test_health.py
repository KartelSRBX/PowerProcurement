import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import AuditLog


def test_health_is_up_without_a_database():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_ready_reports_503_when_database_is_down():
    class Broken:
        def execute(self, *_):
            raise RuntimeError("down")

    app.dependency_overrides[get_session] = lambda: Broken()
    try:
        assert TestClient(app).get("/health/ready").status_code == 503
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_ready_and_audit_log_against_real_postgres(pg_url):
    engine = create_engine(pg_url)
    with engine.begin() as c:
        c.execute(text("DELETE FROM audit_log"))
    with Session(engine) as s:
        s.add(AuditLog(actor="system", action="phase0.smoke", payload={"ok": True}))
        s.commit()
    app.dependency_overrides[get_session] = lambda: Session(engine)
    try:
        body = TestClient(app).get("/health/ready").json()
    finally:
        app.dependency_overrides.clear()
    assert body["status"] == "ok" and body["mail_mode"].startswith("demo")
    with Session(engine) as s:
        assert s.query(AuditLog).filter_by(action="phase0.smoke").count() == 1

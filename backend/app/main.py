from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crm.api import router as crm_router
from app.db import get_session
from app.intake.api import router as requests_router
from app.pipeline.api import router as pipeline_router

app = FastAPI(title="PowerProcurement", version="0.1.0")
app.include_router(requests_router)
app.include_router(pipeline_router)
app.include_router(crm_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Says nothing about dependencies."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready(session: Session = Depends(get_session)) -> dict[str, str]:
    """Readiness: the database answers, and which safety-relevant modes are active."""
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means "not ready"
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    s = get_settings()
    return {
        "status": "ok",
        "ai_provider": s.ai_provider,
        "mail_mode": "real" if s.mail_real_send_enabled else "demo (Mailpit)",
    }

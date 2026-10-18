"""National Bank of Serbia middle exchange rates (srednji kurs), fetched from a public JSON mirror.

The URL is a setting (FX_NBS_URL). The default is kurs.resenje.org, which republishes the NBS list daily;
the bank's own list is HTML and its web service needs a registered licence. Rates are RSD per
unit of currency (divided by `parity`); we turn them into units per 1 EUR, which the rest of the app uses."""

import threading
import time
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import FxRate

CODES = ("EUR", "USD")
REFRESH_EVERY = timedelta(hours=6)


class FxError(Exception):
    pass


def _rsd_per_unit(payload: dict, code: str) -> tuple[float, date]:
    try:
        middle = float(payload["exchange_middle"])
        parity = float(payload.get("parity") or 1)
        day = date.fromisoformat(str(payload["date"])[:10])
    except (KeyError, TypeError, ValueError) as exc:
        raise FxError(
            f"unexpected answer for {code}: missing or invalid exchange_middle/parity/date"
        ) from exc
    if middle <= 0 or parity <= 0:
        raise FxError(f"unexpected answer for {code}: non-positive rate")
    return middle / parity, day


def fetch_nbs(settings: Settings, client: httpx.Client | None = None) -> dict:
    """Returns {rate_date, rsd_per_eur, usd_per_eur}. Raises FxError with a plain message."""
    own = client is None
    client = client or httpx.Client(timeout=10, follow_redirects=True)
    try:
        per_rsd: dict[str, float] = {}
        days: list[date] = []
        for code in CODES:
            url = settings.fx_nbs_url.format(code=code.lower())
            try:
                resp = client.get(url)
                resp.raise_for_status()
                rate, day = _rsd_per_unit(resp.json(), code)
            except httpx.HTTPStatusError as exc:
                raise FxError(f"{url} answered {exc.response.status_code}") from exc
            except httpx.HTTPError as exc:
                raise FxError(f"cannot reach {url}: {type(exc).__name__}") from exc
            except ValueError as exc:
                raise FxError(f"{url} did not return JSON") from exc
            per_rsd[code] = rate
            days.append(day)
        return {
            "rate_date": min(days),
            "rsd_per_eur": per_rsd["EUR"],
            "usd_per_eur": per_rsd["EUR"] / per_rsd["USD"],
        }
    finally:
        if own:
            client.close()


def refresh(session: Session, settings: Settings, client: httpx.Client | None = None) -> FxRate:
    got = fetch_nbs(settings, client)
    row = FxRate(source="nbs", **got)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def latest(session: Session) -> FxRate | None:
    return session.scalars(select(FxRate).order_by(FxRate.id.desc()).limit(1)).first()


def is_stale(row: FxRate) -> bool:
    fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - fetched > REFRESH_EVERY


def history(session: Session, n: int = 8) -> list[FxRate]:
    return list(session.scalars(select(FxRate).order_by(FxRate.id.desc()).limit(n)))


def _loop() -> None:  # pragma: no cover - background thread
    from app.runtime.store import apply

    while True:
        try:
            session = next(get_session())
            try:
                settings = get_settings()
                if settings.fx_source == "nbs":
                    last = latest(session)
                    if last is None or is_stale(last):
                        refresh(session, settings)
                        apply(session, settings)
            finally:
                session.close()
        except Exception:  # noqa: BLE001 - keep the last good rates and try again later
            pass
        time.sleep(1800)


def start_refresher() -> None:
    threading.Thread(target=_loop, name="fx-refresh", daemon=True).start()

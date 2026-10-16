import os

import pytest
from sqlalchemy import create_engine, text

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("DATABASE_URL not set to a Postgres instance")
    try:
        with create_engine(url).connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres not reachable")
    return url

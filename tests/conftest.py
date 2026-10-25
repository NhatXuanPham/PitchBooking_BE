import os
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 1. Determine and set TEST_DATABASE_URL BEFORE importing app or settings
_dev_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/pitchbooking",
)
_parsed = urlparse(_dev_db_url)
_test_db_name = os.getenv("TEST_DB_NAME", "pitchbooking_test")
_default_test_url = urlunparse(_parsed._replace(path=f"/{_test_db_name}"))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", _default_test_url)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine, get_db
from app.core.rate_limit import limiter
from app.main import app

# 2. Strict safety check: tests must run against the test database, never dev/prod
assert (
    engine.url.database == _test_db_name
), f"SAFETY ERROR: Engine connected to '{engine.url.database}', expected test database '{_test_db_name}'!"


@pytest_asyncio.fixture
async def async_client():
    limiter.reset()

    async def _override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()



@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


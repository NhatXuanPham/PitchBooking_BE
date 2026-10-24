import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import engine
from app.core.rate_limit import limiter
from app.main import app


@pytest_asyncio.fixture
async def async_client():
    limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()

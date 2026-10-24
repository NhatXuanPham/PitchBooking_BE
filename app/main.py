import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import api_router
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PitchBooking API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

allowed_origins = [settings.FRONTEND_URL] if settings.FRONTEND_URL else ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def check_db(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception:
        # Log details server-side only; never expose connection strings/driver errors
        logger.exception("Database health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "fail", "db": "unavailable"},
        )

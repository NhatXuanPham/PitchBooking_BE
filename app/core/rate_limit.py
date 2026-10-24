from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Keyed by client IP. In-memory storage is per-process: when running multiple workers
# or instances, point RATE_LIMIT_STORAGE_URI at a shared backend (e.g. redis://...).
# Behind a reverse proxy, run uvicorn with --proxy-headers so the real client IP is used.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    enabled=settings.RATE_LIMIT_ENABLED,
)

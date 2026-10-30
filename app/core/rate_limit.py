from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# NOTE: Production Deployment Checklist:
# 1. Reverse Proxy (Nginx / Cloudflare / Docker):
#    `get_remote_address` extracts the immediate socket connection IP. When deployed
#    behind a reverse proxy, ensure Uvicorn is started with proxy headers enabled so
#    it resolves the real client IP via X-Forwarded-For instead of the proxy's IP:
#    uvicorn app.main:app --proxy-headers --forwarded-allow-ips='*'
#
# 2. Multi-Worker / Multi-Container Environments:
#    Local development uses "memory://" (single-process in-memory storage).
#    When scaling to multiple Uvicorn workers (--workers > 1) or distributed containers,
#    configure RATE_LIMIT_STORAGE_URI in .env to a shared Redis instance:
#    RATE_LIMIT_STORAGE_URI=redis://localhost:6379/0

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    enabled=settings.RATE_LIMIT_ENABLED,
)

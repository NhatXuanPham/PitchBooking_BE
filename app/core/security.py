import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

password_hash = PasswordHash.recommended()


def create_token(
    user_id: int | str,
    token_type: str,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)

    if token_type == "access":
        expires_at = now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    elif token_type == "refresh":
        expires_at = now + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    elif token_type == "reset_password":
        expires_at = now + timedelta(
            minutes=settings.RESET_PASSWORD_TOKEN_EXPIRE_MINUTES
        )
    else:
        raise ValueError(f"Invalid token_type: {token_type}")

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
    }

    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    return token, expires_at


def decode_token(
    token: str,
    token_type: str = "access",
) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )

        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Expected {token_type} token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_access_token(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
) -> dict:
    token = bearer_token or request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(
        token,
        token_type="access",
    )


def _cookie_kwargs(path: str = "/") -> dict:
    secure = settings.BACKEND_URL.startswith("https://")
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "none" if secure else "lax",
        "path": path,
    }


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """Set HttpOnly cookies for access_token and refresh_token."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **_cookie_kwargs(path="/"),
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        **_cookie_kwargs(path="/"),
    )


def delete_auth_cookies(response: Response) -> None:
    """Clear HttpOnly authentication cookies."""
    response.delete_cookie(key="access_token", **_cookie_kwargs(path="/"))
    response.delete_cookie(key="refresh_token", **_cookie_kwargs(path="/"))


def verify_refresh_token(
    token: str,
) -> dict:
    return decode_token(
        token,
        token_type="refresh",
    )


def verify_reset_password_token(
    token: str,
) -> dict:
    return decode_token(
        token,
        token_type="reset_password",
    )


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically secure random N-digit numeric OTP"""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(code: str) -> str:
    """Compute HMAC-SHA-256 hash of an OTP using secret key"""
    secret = settings.OTP_SECRET_KEY or settings.SECRET_KEY
    return hmac.new(
        secret.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_hash(plain_code: str, hashed_code: str) -> bool:
    """Constant-time verification of an OTP against its HMAC-SHA-256 hash"""
    computed = hash_otp(plain_code)
    return hmac.compare_digest(computed, hashed_code)


def hash_token(token: str) -> str:
    """
    SHA-256 hex digest of a token (e.g. a refresh token) for storage at rest.
    Tokens are high-entropy JWTs, so an unsalted hash is sufficient and still allows lookup.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
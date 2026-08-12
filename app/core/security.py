import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import settings


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/login"
)

password_hash = PasswordHash.recommended()


def create_token(
    user_id: uuid.UUID,
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
                status_code=401,
                detail=f"Expected {token_type} token",
            )

        return payload

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )


def verify_access_token(
    token: str = Depends(oauth2_scheme),
) -> dict:
    return decode_token(
        token,
        token_type="access",
    )


def verify_refresh_token(
    token: str = Depends(oauth2_scheme),
) -> dict:
    return decode_token(
        token,
        token_type="refresh",
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
"""
End-to-end auth flow tests against the configured database.

Emails are never actually sent (email_service is patched) and OTP generation is made
deterministic so the tests can complete verification / password reset.
Every test uses a unique email/username and deletes its user afterwards.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_token
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import auth_service as auth_service_module
from app.services.email_service import email_service

FIXED_OTP = "246810"
PASSWORD = "Sup3rSecret!pass"


@pytest.fixture(autouse=True)
def _no_email_and_fixed_otp(monkeypatch):
    monkeypatch.setattr(email_service, "send_registration_otp_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_password_reset_otp_email", AsyncMock())
    monkeypatch.setattr(auth_service_module, "generate_otp", lambda: FIXED_OTP)


@pytest_asyncio.fixture
async def new_identity():
    suffix = uuid.uuid4().hex[:10]
    identity = {"email": f"flow_{suffix}@example.com", "username": f"flow_{suffix}"}
    yield identity
    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == identity["email"]))
        await session.commit()


async def _register_and_verify(client: AsyncClient, identity: dict) -> dict:
    resp = await client.post(
        "/api/v1/auth/send-otp",
        json={"email": identity["email"], "purpose": "REGISTER"},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/register",
        json={**identity, "otp": FIXED_OTP, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["tokens"]


async def _login(client: AsyncClient, username: str, password: str = PASSWORD):
    return await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )


@pytest.mark.asyncio
async def test_full_flow_register_verify_login_refresh_reuse(async_client, new_identity):
    # Step 1: Send OTP
    resp = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": new_identity["email"], "purpose": "REGISTER"},
    )
    assert resp.status_code == 200, resp.text
    email_service.send_registration_otp_email.assert_called_once()

    # Verify pending user record in database
    async with AsyncSessionLocal() as session:
        pending_user = (
            await session.execute(select(User).where(User.email == new_identity["email"]))
        ).scalar_one()
        assert pending_user.username.startswith(new_identity["email"].split("@")[0])
        assert pending_user.is_active is True
        assert pending_user.is_email_verified is False

    # Login before completing registration -> generic 401 (no account status leak)
    unverified_login_resp = await _login(async_client, new_identity["email"])
    assert unverified_login_resp.status_code == 401
    assert unverified_login_resp.json()["detail"] == "Email or password is incorrect"

    # Step 2: Register with wrong OTP -> 400
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={**new_identity, "otp": "999999", "password": PASSWORD},
    )
    assert resp.status_code == 400

    # Step 3: Register with correct OTP -> 201 and auto-login tokens
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={**new_identity, "otp": FIXED_OTP, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    tokens = resp.json()["tokens"]
    assert tokens["access_token"]

    # Verify user record is now activated and updated with real username
    async with AsyncSessionLocal() as session:
        active_user = (
            await session.execute(select(User).where(User.email == new_identity["email"]))
        ).scalar_one()
        assert active_user.username == new_identity["username"]
        assert active_user.is_active is True
        assert active_user.is_email_verified is True

    # Login (by email, different case) and call a protected endpoint
    resp = await _login(async_client, new_identity["email"].upper())
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    me = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == new_identity["email"]

    # Refresh rotates the token pair
    old_refresh = tokens["refresh_token"]
    resp = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200, resp.text
    new_refresh = resp.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reusing the rotated token is rejected (401), while the newly issued token remains valid
    resp = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401
    resp = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_refresh_tokens_are_stored_hashed(async_client, new_identity):
    tokens = await _register_and_verify(async_client, new_identity)
    raw = tokens["refresh_token"]

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
            )
        ).scalar_one()
        assert row.token_hash != raw
        assert len(row.token_hash) == 64


@pytest.mark.asyncio
async def test_email_is_normalized_to_lowercase(async_client, new_identity):
    mixed_case = new_identity["email"].replace("flow_", "FLOW_").replace("example", "Example")
    await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": mixed_case, "purpose": "REGISTER"},
    )
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"username": new_identity["username"], "email": mixed_case, "otp": FIXED_OTP, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text

    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == new_identity["email"]))
        ).scalar_one()
        assert user.email == new_identity["email"]


@pytest.mark.asyncio
async def test_wrong_otp_counts_attempts(async_client, new_identity):
    await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": new_identity["email"], "purpose": "REGISTER"},
    )
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={**new_identity, "otp": "000000", "password": PASSWORD},
    )
    assert resp.status_code == 400
    assert "attempts remaining" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(async_client, new_identity):
    tokens = await _register_and_verify(async_client, new_identity)
    resp = await async_client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    resp = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_and_reset_password(async_client, new_identity):
    old_tokens = await _register_and_verify(async_client, new_identity)

    resp = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": new_identity["email"], "purpose": "RESET_PASSWORD"},
    )
    assert resp.status_code == 200
    email_service.send_password_reset_otp_email.assert_called_once()

    new_password = "An0ther!Password"
    resp = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"email": new_identity["email"], "otp": FIXED_OTP, "new_password": new_password},
    )
    assert resp.status_code == 200, resp.text

    # Old sessions are revoked, old password no longer works, new one does
    resp = await async_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}
    )
    assert resp.status_code == 401
    assert (await _login(async_client, new_identity["username"])).status_code == 401
    assert (await _login(async_client, new_identity["username"], new_password)).status_code == 200


@pytest.mark.asyncio
async def test_login_is_rate_limited(async_client):
    # Default RATE_LIMIT_LOGIN is 5/minute per IP
    statuses = []
    for _ in range(6):
        resp = await _login(async_client, "nobody_rate_limit_test", "wrong-password")
        statuses.append(resp.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


@pytest.mark.asyncio
async def test_google_exchange_requires_matching_state(async_client):
    # No state cookie at all
    resp = await async_client.post(
        "/api/v1/auth/google/exchange", json={"code": "abc", "state": "forged"}
    )
    assert resp.status_code == 400

    # Cookie present but state mismatch
    async_client.cookies.set("google_oauth_state", "real-state", path="/api/v1/auth/google")
    resp = await async_client.post(
        "/api/v1/auth/google/exchange", json={"code": "abc", "state": "forged"}
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_old_refreshtoken_path_removed(async_client):
    resp = await async_client.post("/api/v1/auth/refreshtoken", json={"refresh_token": "x"})
    assert resp.status_code == 404



@pytest.mark.asyncio
async def test_unified_registration_and_deprecated_endpoints_removed(async_client, new_identity):
    # Verify deprecated endpoints return 404
    resp = await async_client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": new_identity["email"], "otp": FIXED_OTP},
    )
    assert resp.status_code == 404

    resp = await async_client.post(
        "/api/v1/auth/register/complete",
        json={"registration_token": "token", "username": "user", "password": PASSWORD},
    )
    assert resp.status_code == 404

    # Step 1: Send OTP for email
    resp = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": new_identity["email"], "purpose": "REGISTER", "resend": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_already_sent"] is False

    # Step 2: Register directly with email, otp, username, password
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": new_identity["email"],
            "otp": FIXED_OTP,
            "username": new_identity["username"],
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["tokens"]["access_token"]

    # Verify user can login and access /me
    resp = await _login(async_client, new_identity["username"])
    assert resp.status_code == 200
    tokens = resp.json()
    me = await async_client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == new_identity["username"]
    assert me.json()["email"] == new_identity["email"]


@pytest.mark.asyncio
async def test_send_otp_flow(async_client, new_identity):
    email = new_identity["email"]

    # 1. First send: resend=False -> sends OTP
    resp = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": email, "purpose": "REGISTER", "resend": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_already_sent"] is False
    assert data["email"] == email
    email_service.send_registration_otp_email.assert_called_once()

    # 2. Second send: resend=False, OTP still valid -> reports already sent & valid, no new email
    email_service.send_registration_otp_email.reset_mock()
    resp2 = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": email, "purpose": "REGISTER", "resend": False},
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["is_already_sent"] is True
    assert data2["expires_in_seconds"] > 0
    email_service.send_registration_otp_email.assert_not_called()

    # 3. Third send: resend=True while in cooldown -> 429 error
    resp3 = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": email, "purpose": "REGISTER", "resend": True},
    )
    assert resp3.status_code == 429

    # 4. Fourth send: even with resend=False, if OTP attempts are exhausted during cooldown -> 429 error
    # Simulate 5 failed attempts to lock the current OTP
    for _ in range(5):
        await async_client.post(
            "/api/v1/auth/register",
            json={"username": f"user_{email.split('@')[0]}", "email": email, "otp": "000000", "password": "Password123!"},
        )
    resp4 = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": email, "purpose": "REGISTER", "resend": False},
    )
    assert resp4.status_code == 429



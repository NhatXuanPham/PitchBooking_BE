import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services import auth_service as auth_service_module
from app.services.email_service import email_service

FIXED_OTP = "246810"
PASSWORD = "Sup3rSecret!pass"


@pytest.fixture(autouse=True)
def _mock_email_and_otp(monkeypatch):
    monkeypatch.setattr(email_service, "send_registration_otp_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_password_reset_otp_email", AsyncMock())
    monkeypatch.setattr(auth_service_module, "generate_otp", lambda: FIXED_OTP)


@pytest_asyncio.fixture
async def authenticated_user(async_client: AsyncClient):
    suffix = uuid.uuid4().hex[:10]
    identity = {
        "email": f"user_{suffix}@example.com",
        "username": f"user_{suffix}",
        "password": PASSWORD,
    }

    # Register
    reg_resp = await async_client.post("/api/v1/auth/register", json=identity)
    assert reg_resp.status_code == 201

    # Verify email
    verify_resp = await async_client.post(
        "/api/v1/auth/verify-email",
        json={"email": identity["email"], "otp": FIXED_OTP},
    )
    assert verify_resp.status_code == 200
    tokens = verify_resp.json()["tokens"]
    token = tokens["access_token"]

    yield {"identity": identity, "token": token, "auth_headers": {"Authorization": f"Bearer {token}"}}

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == identity["email"]))
        await session.commit()


@pytest.mark.asyncio
async def test_get_me_initial_profile(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    response = await async_client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == authenticated_user["identity"]["email"]
    assert data["username"] == authenticated_user["identity"]["username"]
    assert data["full_name"] is None
    assert data["phone_number"] is None
    assert data["address"] is None
    assert data["interests"] is None


@pytest.mark.asyncio
async def test_update_me_all_fields(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    update_payload = {
        "full_name": "Nguyễn Văn A",
        "phone_number": "0912345678",
        "address": "123 Đường Số 1, Quận 1, TP. HCM",
        "avatar_url": "https://example.com/avatar.jpg",
        "date_of_birth": "1995-10-25",
        "gender": "male",
        "bio": "Đam mê bóng đá sân 7 và cầu lông",
        "interests": ["Bóng đá", "Cầu lông", "Tiền đạo"],
    }
    response = await async_client.patch("/api/v1/users/me", json=update_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == update_payload["full_name"]
    assert data["phone_number"] == update_payload["phone_number"]
    assert data["address"] == update_payload["address"]
    assert data["avatar_url"] == update_payload["avatar_url"]
    assert data["date_of_birth"] == update_payload["date_of_birth"]
    assert data["gender"] == update_payload["gender"]
    assert data["bio"] == update_payload["bio"]
    assert data["interests"] == update_payload["interests"]

    # Verify persistence via GET /me
    get_resp = await async_client.get("/api/v1/users/me", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["full_name"] == "Nguyễn Văn A"
    assert get_resp.json()["phone_number"] == "0912345678"


@pytest.mark.asyncio
async def test_update_me_alias_hobbies(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    update_payload = {
        "hobbies": ["Tennis", "Bơi lội"],
    }
    response = await async_client.patch("/api/v1/users/me", json=update_payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["interests"] == ["Tennis", "Bơi lội"]


@pytest.mark.asyncio
async def test_partial_update_keeps_existing_fields(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]

    # Step 1: Set full_name and phone_number
    await async_client.patch(
        "/api/v1/users/me",
        json={"full_name": "Tran Van B", "phone_number": "0987654321"},
        headers=headers,
    )

    # Step 2: Update only bio
    resp = await async_client.patch(
        "/api/v1/users/me",
        json={"bio": "Hậu vệ thòng"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Tran Van B"
    assert data["phone_number"] == "0987654321"
    assert data["bio"] == "Hậu vệ thòng"


@pytest.mark.asyncio
async def test_update_invalid_phone_number(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    response = await async_client.patch(
        "/api/v1/users/me",
        json={"phone_number": "not-a-phone"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_user_by_id(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    me_resp = await async_client.get("/api/v1/users/me", headers=headers)
    user_id = me_resp.json()["id"]

    # Fetch user profile by ID
    profile_resp = await async_client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert profile_resp.status_code == 200
    assert profile_resp.json()["id"] == user_id
    assert profile_resp.json()["username"] == authenticated_user["identity"]["username"]


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(async_client: AsyncClient, authenticated_user):
    headers = authenticated_user["auth_headers"]
    response = await async_client.get("/api/v1/users/99999999", headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_user_endpoints(async_client: AsyncClient):
    resp_get = await async_client.get("/api/v1/users/me")
    assert resp_get.status_code == 401

    resp_patch = await async_client.patch("/api/v1/users/me", json={"full_name": "Test"})
    assert resp_patch.status_code == 401

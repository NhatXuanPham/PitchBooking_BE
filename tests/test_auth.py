import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_validation_short_password(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "otp": "123456",
            "password": "123",  # Less than 8 chars
        },
    )
    assert response.status_code == 422  # Validation error from Pydantic


@pytest.mark.asyncio
async def test_register_validation_invalid_email(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "not-an-email",
            "otp": "123456",
            "password": "valid_password_123",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_swagger_docs(async_client: AsyncClient):
    response = await async_client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text

    openapi_resp = await async_client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    paths = openapi_resp.json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/verify-email" not in paths
    assert "/api/v1/auth/register/verify-otp" not in paths
    assert "/api/v1/auth/register/complete" not in paths
    assert "/api/v1/auth/forgot-password" not in paths
    assert "/api/v1/auth/send-otp" in paths


@pytest.mark.asyncio
async def test_register_validation_username_with_at_sign(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "username": "someone@example.com",  # '@' is not allowed in usernames
            "email": "test@example.com",
            "otp": "123456",
            "password": "valid_password_123",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_forgot_password_endpoint_removed(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_otp_reset_password_unknown_email_not_revealed(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/send-otp",
        json={"email": "nonexistent_pitch_user@example.com", "purpose": "RESET_PASSWORD"},
    )
    assert response.status_code == 200
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_resend_otp_endpoint_removed(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/resend-otp",
        json={"email": "nonexistent_pitch_user@example.com", "purpose": "REGISTER"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_verify_email_endpoint_removed(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/verify-email",
        json={"email": "nonexistent_pitch_user@example.com", "otp": "123456"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reset_password_unknown_email(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "nonexistent_pitch_user@example.com",
            "otp": "123456",
            "new_password": "NewValidPassword123!",
        },
    )
    # Same error as an invalid OTP so the email's existence is not revealed
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_missing_otp(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "someone@example.com",
            "new_password": "NewValidPassword123!",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reset_password_short_password(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": "someone@example.com",
            "otp": "123456",
            "new_password": "123",
        },
    )
    assert response.status_code == 422

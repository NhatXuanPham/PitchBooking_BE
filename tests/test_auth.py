import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_validation_short_password(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
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
            "password": "valid_password_123",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_swagger_docs(async_client: AsyncClient):
    response = await async_client.get("/docs")
    assert response.status_code == 200
    assert "Swagger UI" in response.text

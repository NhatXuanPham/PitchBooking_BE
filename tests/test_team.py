import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models.enum import TeamRole
from app.models.team import Team
from app.models.user import User
from app.services import auth_service as auth_service_module
from app.services.email_service import email_service

FIXED_OTP = "135790"
PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def _patch_email_and_otp(monkeypatch):
    monkeypatch.setattr(email_service, "send_registration_otp_email", AsyncMock())
    monkeypatch.setattr(email_service, "send_password_reset_otp_email", AsyncMock())
    monkeypatch.setattr(auth_service_module, "generate_otp", lambda: FIXED_OTP)


async def _create_user(client: AsyncClient, prefix: str = "teamuser") -> dict:
    suffix = uuid.uuid4().hex[:8]
    data = {
        "username": f"{prefix}_{suffix}",
        "email": f"{prefix}_{suffix}@example.com",
        "password": PASSWORD,
    }
    await client.post(
        "/api/v1/auth/send-otp",
        json={"email": data["email"], "purpose": "REGISTER"},
    )
    resp = await client.post("/api/v1/auth/register", json={**data, "otp": FIXED_OTP})
    assert resp.status_code == 201, resp.text
    tokens = resp.json()["tokens"]

    # Fetch user info
    me_resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    user_info = me_resp.json()

    return {
        "user_id": user_info["id"],
        "username": data["username"],
        "email": data["email"],
        "token": tokens["access_token"],
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


@pytest.mark.asyncio
async def test_get_positions(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/teams/positions")
    assert resp.status_code == 200, resp.text
    positions = resp.json()
    assert len(positions) >= 4
    codes = [p["code"] for p in positions]
    assert "GK" in codes
    assert "ST" in codes
    assert "CM" in codes


    # Test filter by PITCH_5
    resp_5 = await async_client.get("/api/v1/teams/positions?pitch_type=PITCH_5")
    assert resp_5.status_code == 200
    pos_5 = resp_5.json()
    codes_5 = [p["code"] for p in pos_5]
    assert "FIXO" in codes_5
    assert "PIVOT" in codes_5



@pytest.mark.asyncio
async def test_create_team_and_leader_role(async_client: AsyncClient):
    user = await _create_user(async_client, "creator")

    # Get positions to select from
    pos_resp = await async_client.get("/api/v1/teams/positions")
    positions = pos_resp.json()
    pos_ids = [p["id"] for p in positions[:2]]

    # Create team
    team_data = {
        "name": f"FC Barcelona {uuid.uuid4().hex[:6]}",
        "description": "Dream Team",
        "my_position_ids": pos_ids,
    }
    resp = await async_client.post("/api/v1/teams/", json=team_data, headers=user["headers"])
    assert resp.status_code == 201, resp.text
    team = resp.json()
    team_id = team["id"]
    assert team["name"] == team_data["name"]
    assert team["created_by_id"] == user["user_id"]
    assert team["members_count"] == 1

    # Get team detail
    detail_resp = await async_client.get(f"/api/v1/teams/{team_id}", headers=user["headers"])
    assert detail_resp.status_code == 200, detail_resp.text
    detail = detail_resp.json()
    assert detail["my_role"] == TeamRole.LEADER
    assert len(detail["members"]) == 1

    creator_member = detail["members"][0]
    assert creator_member["user_id"] == user["user_id"]
    assert creator_member["role"] == TeamRole.LEADER
    assert len(creator_member["positions"]) == len(pos_ids)

    # Cleanup
    await async_client.delete(f"/api/v1/teams/{team_id}", headers=user["headers"])


@pytest.mark.asyncio
async def test_member_with_multiple_positions_and_roles(async_client: AsyncClient):
    leader = await _create_user(async_client, "leader")
    player1 = await _create_user(async_client, "player1")

    pos_resp = await async_client.get("/api/v1/teams/positions")
    positions = {p["code"]: p["id"] for p in pos_resp.json()}

    # Create team
    team_resp = await async_client.post(
        "/api/v1/teams/",
        json={"name": f"Hanoi FC {uuid.uuid4().hex[:6]}"},
        headers=leader["headers"],
    )
    team_id = team_resp.json()["id"]

    # Leader adds player1 with multiple titles (e.g. GK and FW)
    add_resp = await async_client.post(
        f"/api/v1/teams/{team_id}/members",
        json={
            "user_id": player1["user_id"],
            "role": TeamRole.MEMBER,
            "position_ids": [positions["GK"], positions["ST"]],
        },
        headers=leader["headers"],
    )
    assert add_resp.status_code == 201, add_resp.text
    member_data = add_resp.json()
    assert member_data["user_id"] == player1["user_id"]
    assert member_data["role"] == TeamRole.MEMBER
    member_positions = [p["code"] for p in member_data["positions"]]
    assert "GK" in member_positions
    assert "ST" in member_positions
    member_id = member_data["id"]

    # Player1 updates their own positions to include CM
    update_pos_resp = await async_client.put(
        f"/api/v1/teams/{team_id}/members/{member_id}/positions",
        json={"position_ids": [positions["CM"], positions["ST"]]},
        headers=player1["headers"],
    )
    assert update_pos_resp.status_code == 200, update_pos_resp.text
    updated_member = update_pos_resp.json()
    updated_codes = [p["code"] for p in updated_member["positions"]]
    assert "CM" in updated_codes
    assert "GK" not in updated_codes


    # Leader promotes player1 to VICE_LEADER
    role_resp = await async_client.patch(
        f"/api/v1/teams/{team_id}/members/{member_id}/role",
        json={"role": TeamRole.VICE_LEADER},
        headers=leader["headers"],
    )
    assert role_resp.status_code == 200, role_resp.text
    assert role_resp.json()["role"] == TeamRole.VICE_LEADER

    # Vice leader adds player2
    player2 = await _create_user(async_client, "player2")
    add_p2_resp = await async_client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"identifier": player2["username"], "role": TeamRole.MEMBER},
        headers=player1["headers"],
    )
    assert add_p2_resp.status_code == 201, add_p2_resp.text

    # Vice leader cannot promote anyone or change roles
    p2_id = add_p2_resp.json()["id"]
    forbidden_resp = await async_client.patch(
        f"/api/v1/teams/{team_id}/members/{p2_id}/role",
        json={"role": TeamRole.VICE_LEADER},
        headers=player1["headers"],
    )
    assert forbidden_resp.status_code == 403

    # Leader promotes player2 to TREASURER
    treasurer_resp = await async_client.patch(
        f"/api/v1/teams/{team_id}/members/{p2_id}/role",
        json={"role": TeamRole.TREASURER},
        headers=leader["headers"],
    )
    assert treasurer_resp.status_code == 200
    assert treasurer_resp.json()["role"] == TeamRole.TREASURER

    # Vice leader cannot kick TREASURER
    cannot_kick_resp = await async_client.delete(
        f"/api/v1/teams/{team_id}/members/{p2_id}",
        headers=player1["headers"],
    )
    assert cannot_kick_resp.status_code == 403


    # Cleanup
    await async_client.delete(f"/api/v1/teams/{team_id}", headers=leader["headers"])


@pytest.mark.asyncio
async def test_transfer_leadership(async_client: AsyncClient):
    leader = await _create_user(async_client, "lead1")
    player = await _create_user(async_client, "lead2")

    team_resp = await async_client.post(
        "/api/v1/teams/",
        json={"name": f"Transfer FC {uuid.uuid4().hex[:6]}"},
        headers=leader["headers"],
    )
    team_id = team_resp.json()["id"]

    add_resp = await async_client.post(
        f"/api/v1/teams/{team_id}/members",
        json={"user_id": player["user_id"]},
        headers=leader["headers"],
    )
    player_member_id = add_resp.json()["id"]

    # Leader transfers leadership to player
    transfer_resp = await async_client.patch(
        f"/api/v1/teams/{team_id}/members/{player_member_id}/role",
        json={"role": TeamRole.LEADER},
        headers=leader["headers"],
    )
    assert transfer_resp.status_code == 200, transfer_resp.text
    assert transfer_resp.json()["role"] == TeamRole.LEADER

    # Check team detail: now player is LEADER and original leader is VICE_LEADER
    detail_resp = await async_client.get(f"/api/v1/teams/{team_id}", headers=player["headers"])
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["my_role"] == TeamRole.LEADER

    roles = {m["user_id"]: m["role"] for m in detail["members"]}
    assert roles[player["user_id"]] == TeamRole.LEADER
    assert roles[leader["user_id"]] == TeamRole.VICE_LEADER

    # Cleanup: new leader deletes team
    del_resp = await async_client.delete(f"/api/v1/teams/{team_id}", headers=player["headers"])
    assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_user_can_join_multiple_teams(async_client: AsyncClient):
    user = await _create_user(async_client, "multiteam")
    other_lead = await _create_user(async_client, "otherlead")

    # User creates Team 1 (as Leader)
    team1_resp = await async_client.post(
        "/api/v1/teams/",
        json={"name": f"User Team 1 {uuid.uuid4().hex[:6]}"},
        headers=user["headers"],
    )
    t1_id = team1_resp.json()["id"]

    # Other user creates Team 2, and adds user as Member
    team2_resp = await async_client.post(
        "/api/v1/teams/",
        json={"name": f"Other Team 2 {uuid.uuid4().hex[:6]}"},
        headers=other_lead["headers"],
    )
    t2_id = team2_resp.json()["id"]

    await async_client.post(
        f"/api/v1/teams/{t2_id}/members",
        json={"user_id": user["user_id"], "role": TeamRole.MEMBER},
        headers=other_lead["headers"],
    )

    # Check /my-teams for user
    my_teams_resp = await async_client.get("/api/v1/teams/my-teams", headers=user["headers"])
    assert my_teams_resp.status_code == 200
    my_teams = my_teams_resp.json()
    my_team_ids = [t["id"] for t in my_teams]
    assert t1_id in my_team_ids
    assert t2_id in my_team_ids

    # Cleanup
    await async_client.delete(f"/api/v1/teams/{t1_id}", headers=user["headers"])
    await async_client.delete(f"/api/v1/teams/{t2_id}", headers=other_lead["headers"])

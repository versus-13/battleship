import copy
import uuid

from .conftest import ALL_SHOTS, SHIPS


async def test_player_lifecycle_and_name(client, player):
    r = await client.get("/api/players/me", headers=player["headers"])
    assert r.status_code == 200 and r.json()["name"] is None and r.json()["stats"]["games"] == 0

    r = await client.put("/api/players/me/name", json={"name": "  Капитан   Немо "}, headers=player["headers"])
    assert r.status_code == 200 and r.json()["name"] == "Капитан Немо"

    r = await client.put("/api/players/me/name", json={"name": "Вася"}, headers=player["headers"])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "rate_limited"

    r = await client.get("/api/players/me")
    assert r.status_code == 401


async def test_name_moderation(client, player):
    r = await client.put("/api/players/me/name", json={"name": "xyй"}, headers=player["headers"])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "rejected_profanity"
    r = await client.put("/api/players/me/name", json={"name": "x"}, headers=player["headers"])
    assert r.json()["detail"]["code"] == "too_short"


def game_payload(gid=None, **override):
    body = {
        "client_game_id": gid or str(uuid.uuid4()),
        "mode": "h2m", "client": "web", "client_version": "0.1.0",
        "logs": [
            {"attacker": {"kind": "player"}, "defender": {"kind": "model_board"},
             "ships": copy.deepcopy(SHIPS), "shots": list(ALL_SHOTS), "fleet_cleared": True, "won": True},
            {"attacker": {"kind": "model", "version": "int8-test"}, "defender": {"kind": "player"},
             "ships": copy.deepcopy(SHIPS), "shots": ALL_SHOTS[:7], "fleet_cleared": False, "won": False},
        ],
    }
    body.update(override)
    return body


async def test_post_games_accepts_and_stats(client, player):
    r = await client.post("/api/games", json=game_payload(), headers=player["headers"])
    assert r.status_code == 201, r.text
    assert len(r.json()["accepted"]) == 2 and r.json()["rejected"] == []

    r = await client.get("/api/players/me", headers=player["headers"])
    st = r.json()["stats"]
    assert st["games"] == 1 and st["wins"] == 1 and st["avg_shots"] == 20 and st["h2m_games"] == 1


async def test_post_games_partial_reject_and_duplicate(client, player):
    body = game_payload()
    body["logs"][1]["shots"] = [70, 60]          # 60 is auto-revealed after sinking 70
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.status_code == 201
    assert len(r.json()["accepted"]) == 1
    assert r.json()["rejected"] == [{"index": 1, "code": "illegal_shot", "detail": None}]

    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert [x["code"] for x in r.json()["rejected"]] == ["duplicate", "illegal_shot"]


async def test_post_games_bad_placement_and_cleared_mismatch(client, player):
    body = game_payload()
    body["logs"][0]["ships"][0] = [0, 1, 2, 3, 4]
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.status_code == 422

    body = game_payload()
    body["logs"][0]["fleet_cleared"] = False
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.json()["rejected"][0]["code"] == "cleared_mismatch"


async def test_leaderboard_ignores_h2m(client, player):
    await client.post("/api/games", json=game_payload(), headers=player["headers"])
    r = await client.get("/api/leaderboard?min_games=1")
    assert r.status_code == 200 and r.json() == []


async def test_model_and_health(client):
    r = await client.get("/api/model")
    assert r.json()["input_shape"] == [1, 8, 10, 10]
    r = await client.get("/healthz")
    assert r.json()["ok"] is True


async def test_post_games_think_ms_and_client_info(client, player):
    body = game_payload(client_info={"placement": "manual", "screen": [1440, 900], "touch": False,
                                     "user_agent": "секрет", "platform": "MacIntel"})
    body["logs"][0]["think_ms"] = [1500] * 20
    body["logs"][0]["started_at"] = 1_800_000_000.5
    body["logs"][1]["think_ms"] = [5, -3, 999_999_999, 8, 9, 10, 11]
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.status_code == 201, r.text
    assert len(r.json()["accepted"]) == 2

    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import GameLog
    async with SessionLocal() as s:
        rows = (await s.scalars(select(GameLog).order_by(GameLog.id))).all()
    assert rows[0].think_ms == [1500] * 20
    assert rows[0].started_at.timestamp() == 1_800_000_000.5
    assert rows[0].client_info == {"placement": "manual", "screen": [1440, 900], "touch": False, "platform": "MacIntel"}
    assert rows[1].think_ms == [5, 0, 600_000, 8, 9, 10, 11]      # clipped to [0, 10 min]

    body = game_payload()
    body["logs"][0]["think_ms"] = [1, 2, 3]
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.status_code == 422

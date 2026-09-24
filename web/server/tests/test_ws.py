"""A human-vs-human match over WebSocket: two clients to game_over, reconnect, forfeit."""
import asyncio
import copy
import time

import pytest
import pytest_asyncio
from sqlalchemy import text
from starlette.testclient import TestClient

from app.db import engine
from app.main import app

from .conftest import SHIPS


@pytest_asyncio.fixture
async def tc():
    # TestClient runs its own event loop; pool connections from the test loop cannot be used there
    await engine.dispose()
    with TestClient(app) as client:
        client.sockets = []
        try:
            yield client
        finally:
            for ws in client.sockets:
                try:
                    ws.__exit__(None, None, None)
                except Exception:
                    pass
    await engine.dispose()


def new_player(tc):
    body = tc.post("/api/players").json()
    return {"id": body["player_id"], "secret": body["secret"],
            "headers": {"Authorization": f"Bearer {body['secret']}"}}


def recv_until(ws, t, limit=50):
    """Reads messages until type t arrives; returns (message, everything read)."""
    seen = []
    for _ in range(limit):
        try:
            msg = ws.receive_json()
        except Exception as e:
            raise AssertionError(f"сокет закрылся, ожидали {t}: {[m['t'] for m in seen]}: {e!r}")
        seen.append(msg)
        if msg["t"] == t:
            return msg, seen
    raise AssertionError(f"не дождались {t}: {[m['t'] for m in seen]}")


def close_ws(tc, ws):
    tc.sockets.remove(ws)
    ws.__exit__(None, None, None)


def open_ws(tc, match_id, player):
    ws = tc.websocket_connect(f"/ws/matches/{match_id}")
    ws.__enter__()
    tc.sockets.append(ws)
    ws.send_json({"t": "hello", "token": player["secret"]})
    state = ws.receive_json()
    assert state["t"] == "state"
    return ws, state


def setup_match(tc):
    a, b = new_player(tc), new_player(tc)
    tc.put("/api/players/me/name", json={"name": "Алиса"}, headers=a["headers"])
    room = tc.post("/api/rooms", headers=a["headers"]).json()
    info = tc.get(f"/api/rooms/{room['code']}").json()
    assert info["status"] == "waiting" and info["host_name"] == "Алиса"
    ws_a, st_a = open_ws(tc, room["match_id"], a)
    assert st_a["phase"] == "waiting" and st_a["opponent"] is None

    joined = tc.post(f"/api/rooms/{room['code']}/join", headers=b["headers"]).json()
    assert joined["match_id"] == room["match_id"]
    msg, _ = recv_until(ws_a, "opponent_joined")
    ws_b, st_b = open_ws(tc, room["match_id"], b)
    assert st_b["phase"] == "placing" and st_b["opponent"]["name"] == "Алиса"
    return a, b, ws_a, ws_b, room


def place_both(ws_a, ws_b):
    ws_a.send_json({"t": "place", "ships": copy.deepcopy(SHIPS), "mode": "manual"})
    recv_until(ws_a, "placed")
    recv_until(ws_b, "opponent_ready")
    ws_b.send_json({"t": "place", "ships": copy.deepcopy(SHIPS), "mode": "manual"})
    recv_until(ws_b, "placed")
    start_a, _ = recv_until(ws_a, "start")
    start_b, _ = recv_until(ws_b, "start")
    assert start_a["your_turn"] != start_b["your_turn"]
    return start_a["your_turn"]


def test_full_match(tc):
    a, b, ws_a, ws_b, room = setup_match(tc)

    ws_a.send_json({"t": "place", "ships": [[0, 1, 2, 3, 4]] + copy.deepcopy(SHIPS)[1:]})
    err, _ = recv_until(ws_a, "error")
    assert err["code"] == "bad_placement"

    a_first = place_both(ws_a, ws_b)
    shooter, other = (ws_a, ws_b) if a_first else (ws_b, ws_a)
    shooter_p, other_p = (a, b) if a_first else (b, a)

    other.send_json({"t": "shoot", "cell": 0})
    err, _ = recv_until(other, "error")
    assert err["code"] == "not_your_turn"

    shooter.send_json({"t": "shoot", "cell": 99})       # miss — the turn passes
    res, _ = recv_until(shooter, "shot_result")
    assert res["result"] == 0 and res["your_turn"] is False
    opp_shot, _ = recv_until(other, "opponent_shot")
    assert opp_shot["cell"] == 99 and opp_shot["your_turn"] is True

    shooter, other = other, shooter
    shooter_p, other_p = other_p, shooter_p
    cells = [c for s in SHIPS for c in s]
    for i, c in enumerate(cells):
        shooter.send_json({"t": "shoot", "cell": c})
        res, _ = recv_until(shooter, "shot_result")
        assert res["result"] >= 1 and (res["your_turn"] or i == len(cells) - 1)
        if i == 3:
            assert res["result"] == 2
            assert res["sunk_cells"] == [0, 1, 2, 3] and set(res["revealed"]) == {4, 10, 11, 12, 13, 14}
            shooter.send_json({"t": "shoot", "cell": 4})        # already opened by the auto-perimeter
            err, _ = recv_until(shooter, "error")
            assert err["code"] == "illegal_shot"

    over_s, _ = recv_until(shooter, "game_over")
    over_o, _ = recv_until(other, "game_over")
    assert over_s["you_won"] is True and over_o["you_won"] is False and over_s["reason"] == "fleet_sunk"
    assert over_o["enemy_ships"] == [sorted(s) for s in sorted(SHIPS, key=lambda s: (-len(s), s[0]))]

    snap = tc.get(f"/api/matches/{room['match_id']}", headers=shooter_p["headers"]).json()
    assert snap["phase"] == "finished" and snap["you_won"] is True

    time.sleep(0.2)
    rows = tc.get("/api/leaderboard?min_games=1").json()
    assert len(rows) == 2 and rows[0]["player_id"] == shooter_p["id"] and rows[0]["wins"] == 1
    st = tc.get(f"/api/players/{shooter_p['id']}/stats").json()
    assert st["h2h_games"] == 1 and st["h2h_wins"] == 1 and st["avg_shots"] == 20

    import asyncio
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import GameLog

    async def rows():
        async with SessionLocal() as s:
            return (await s.scalars(select(GameLog).order_by(GameLog.id))).all()
    logs = tc.portal.call(rows)
    by_attacker = {str(r.attacker_player): r for r in logs}
    win = by_attacker[shooter_p["id"]]
    assert len(win.think_ms) == win.n_shots == 20 and all(0 <= t < 60_000 for t in win.think_ms)
    assert win.started_at is not None
    assert {by_attacker[a["id"]].client_info["placement"] for a in (a, b)} == {"manual"}


def test_reconnect_restores_state(tc):
    a, b, ws_a, ws_b, room = setup_match(tc)
    a_first = place_both(ws_a, ws_b)
    shooter = ws_a if a_first else ws_b
    shooter.send_json({"t": "shoot", "cell": 0})
    recv_until(shooter, "shot_result")
    recv_until(ws_b if a_first else ws_a, "opponent_shot")

    close_ws(tc, ws_b)
    left, _ = recv_until(ws_a, "opponent_left")
    assert left["grace_s"] >= 1
    ws_b2, st = open_ws(tc, room["match_id"], b)
    assert st["phase"] == "playing"
    if a_first:
        assert st["you"]["hits"] == [0]
    else:
        assert st["enemy"]["cells"] == {"0": "hit"}
    recv_until(ws_a, "opponent_back")


def test_disconnect_forfeit(tc):
    a, b, ws_a, ws_b, room = setup_match(tc)
    place_both(ws_a, ws_b)
    close_ws(tc, ws_b)
    recv_until(ws_a, "opponent_left")
    over, _ = recv_until(ws_a, "game_over")          # BS_DISCONNECT_GRACE_S=1
    assert over["you_won"] is True and over["reason"] == "disconnect"


def test_move_timeout_forfeit(tc):
    a, b, ws_a, ws_b, room = setup_match(tc)
    a_first = place_both(ws_a, ws_b)
    waiter = ws_b if a_first else ws_a
    over, _ = recv_until(waiter, "game_over")        # BS_MOVE_S=2
    assert over["you_won"] is True and over["reason"] == "move_timeout"


def test_queue_matches_two_players(tc):
    a, b = new_player(tc), new_player(tc)
    r1 = tc.post("/api/queue", headers=a["headers"]).json()
    assert r1["status"] == "queued"
    r2 = tc.post("/api/queue", headers=b["headers"]).json()
    assert r2["status"] == "matched"
    r3 = tc.post("/api/queue", headers=a["headers"]).json()
    assert r3["status"] == "matched" and r3["match_id"] == r2["match_id"]
    cur = tc.get("/api/matches/current", headers=a["headers"]).json()
    assert cur["match_id"] == r2["match_id"] and cur["phase"] == "placing"
    assert tc.post("/api/rooms", headers=a["headers"]).status_code == 409

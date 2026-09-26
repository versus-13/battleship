"""A server restart in the middle of an H2H match: the match is saved, restored and played on."""
import time

from sqlalchemy import func, select
from starlette.testclient import TestClient

from app.db import SessionLocal, engine
from app.main import app
from app.models import GameLog, LiveMatch

from .conftest import ALL_SHOTS
from .test_ws import open_ws, place_both, recv_until, setup_match


def client():
    c = TestClient(app)
    c.__enter__()
    c.sockets = []
    return c


def stop(c):
    """Like SIGTERM: the sockets drop first (uvicorn sends 1012), then the lifespan shutdown."""
    for ws in c.sockets:
        try:
            ws.__exit__(None, None, None)
        except Exception:
            pass
    time.sleep(0.2)
    c.__exit__(None, None, None)


async def live_rows():
    async with SessionLocal() as s:
        return (await s.scalars(select(LiveMatch))).all()


async def test_match_survives_restart():
    await engine.dispose()
    c = client()
    a, b, ws_a, ws_b, room = setup_match(c)
    a_first = place_both(ws_a, ws_b)
    shooter, other = (ws_a, ws_b) if a_first else (ws_b, ws_a)
    shooter_p, other_p = (a, b) if a_first else (b, a)
    shooter.send_json({"t": "shoot", "cell": 99})        # a miss: the turn passes to `other`
    recv_until(shooter, "shot_result")
    recv_until(other, "opponent_shot")
    stop(c)

    await engine.dispose()
    rows = await live_rows()
    assert [str(r.id) for r in rows] == [room["match_id"]]
    assert rows[0].state["status"] == "playing"
    await engine.dispose()                                # the pool belongs to the test loop — drop it

    c = client()
    try:
        ws_o, st_o = open_ws(c, room["match_id"], other_p)
        assert st_o["phase"] == "playing" and st_o["your_turn"] is True and st_o["you"]["revealed"] == [99]
        ws_s, st_s = open_ws(c, room["match_id"], shooter_p)
        assert st_s["your_turn"] is False and st_s["enemy"]["cells"] == {"99": "miss"}
        for c_ in ALL_SHOTS:                               # the match goes on to the end
            ws_o.send_json({"t": "shoot", "cell": c_})
            recv_until(ws_o, "shot_result")
        over, _ = recv_until(ws_o, "game_over")
        assert over["you_won"] is True and over["reason"] == "fleet_sunk"
        time.sleep(0.3)

        async def check():
            async with SessionLocal() as s:
                return (await s.scalar(select(func.count()).select_from(LiveMatch)),
                        await s.scalar(select(func.count()).select_from(GameLog)))
        assert c.portal.call(check) == (0, 2)            # the logs are written, the live row is gone
    finally:
        stop(c)


async def test_checkpoint_without_shutdown():
    await engine.dispose()
    c = client()
    try:
        a, b, ws_a, ws_b, room = setup_match(c)
        a_first = place_both(ws_a, ws_b)
        shooter = ws_a if a_first else ws_b
        shooter.send_json({"t": "shoot", "cell": 0})
        recv_until(shooter, "shot_result")
        time.sleep(1.5)                                   # BS checkpoint_s = 1 s

        async def state():
            async with SessionLocal() as s:
                row = await s.get(LiveMatch, __import__("uuid").UUID(room["match_id"]))
                return row.state if row else None
        st = c.portal.call(state)
        assert st is not None and 0 in [x for v in st["shots"].values() for x in v]
    finally:
        stop(c)

"""Match time rules without sockets and the DB: auto-moves, the reconnect budget, solo."""
import asyncio
import copy
import uuid

import pytest

from app.config import settings
from app.h2h import FINISHED, Match

from .conftest import ALL_SHOTS, SHIPS


class FakeWS:
    def __init__(self):
        self.msgs = []

    async def send_json(self, m):
        self.msgs.append(m)

    async def close(self, code=1000, reason=""):
        pass

    def of(self, t):
        return [m for m in self.msgs if m["t"] == t]


@pytest.fixture
def fast(monkeypatch):
    for k, v in {"move_s": 0.3, "reconnect_budget_s": 1.0, "disconnect_after_budget_s": 30,
                 "idle_moves_limit": 100, "solo_idle_s": 30}.items():
        monkeypatch.setattr(settings, k, v)


async def started(a_turn=True):
    saved = []

    async def on_finish(m):
        saved.append(m)

    a, b = uuid.uuid4(), uuid.uuid4()
    m = Match("room", a, "ABCDEF", on_finish)
    assert m.join(b, None, "bbbb")
    wa, wb = FakeWS(), FakeWS()
    await m.connect(a, wa, None, "aaaa")
    await m.connect(b, wb, None, "bbbb")
    await m.place(a, copy.deepcopy(SHIPS))
    await m.place(b, copy.deepcopy(SHIPS))
    m.turn = a if a_turn else b                 # determinism instead of the coin toss
    m._arm_move()
    return m, a, b, wa, wb, saved


async def test_manual_shot_resets_the_streak(fast):
    m, a, b, wa, wb, _ = await started()
    await asyncio.sleep(0.45)
    assert len(m.auto_moves[a]) == 1 and m.shots[a] and m.auto_streak[a] == 1
    m.turn = a
    m._arm_move()
    cell = next(i for i in range(100) if not m.boards[b].known[i])
    await m.shoot(a, cell)
    assert m.auto_streak[a] == 0 and wa.of("shot_result")[-1]["auto"] is False
    m._disarm_all()


async def test_idle_limit_ends_the_match(fast, monkeypatch):
    monkeypatch.setattr(settings, "idle_moves_limit", 1)
    m, a, b, wa, wb, saved = await started()
    await asyncio.sleep(0.45)
    assert m.status == FINISHED and m.winner == b and m.end_reason == "idle"


async def test_move_timer_waits_while_reconnecting(fast):
    m, a, b, wa, wb, _ = await started()
    await m.disconnect(a, wa)
    assert m.deadline_ts is None and m._move_left is not None
    snap = wb.of("state")[-1]
    assert snap["opponent"]["connected"] is False and snap["opponent"]["reconnect_deadline_ts"] is not None
    await asyncio.sleep(0.6)                    # longer than a move: no auto-shot while the budget lasts
    assert m.shots[a] == []
    wa2 = FakeWS()
    await m.connect(a, wa2, None, "aaaa")
    assert 0.3 < m.budget_left[a] < 0.45        # the budget is per match, not per disconnect
    assert m.deadline_ts is not None and wb.of("opponent_back")
    await asyncio.sleep(0.45)
    assert len(m.auto_moves[a]) == 1            # back online — the timer runs again


async def test_spent_budget_resumes_auto_moves(fast):
    m, a, b, wa, wb, _ = await started()
    m.budget_left[a] = 0.2
    await m.disconnect(a, wa)
    await asyncio.sleep(0.15)
    assert m.shots[a] == []
    await asyncio.sleep(0.5)                    # budget spent + the rest of the move
    assert m.auto_moves[a] and m.status != FINISHED
    assert wb.of("state")[-1]["opponent"]["reconnect_deadline_ts"] is None
    m._disarm_all()


async def test_never_connected_player_spends_the_budget(fast, monkeypatch):
    monkeypatch.setattr(settings, "disconnect_after_budget_s", 0.1)
    saved = []

    async def on_finish(mm):
        saved.append(mm)

    a, b = uuid.uuid4(), uuid.uuid4()
    m = Match("queue", a, None, on_finish)
    m.join(b, None, "bbbb")
    wa = FakeWS()
    await m.connect(a, wa, None, "aaaa")        # b never opens the socket
    await asyncio.sleep(1.3)
    assert m.status == FINISHED and m.winner == a and m.end_reason == "disconnect" and saved


async def test_resign_gives_the_winner_a_solo(fast):
    m, a, b, wa, wb, saved = await started()
    await m.leave(b)
    assert m.status == FINISHED and m.end_reason == "resigned" and m.solo == a and not saved
    assert wa.of("game_over")[-1]["solo"] is True and wa.of("game_over")[-1]["enemy_ships"] is None
    assert m.snapshot(a)["your_turn"] is True and m.snapshot(a)["enemy_ships"] is None
    assert await m.shoot(b, 0) == "wrong_phase"
    for c in ALL_SHOTS:
        assert await m.shoot(a, c) is None
    assert m.solo is None and saved and m.boards[b].done
    _, logs = m.db_rows()
    by = {l.attacker_player: l for l in logs}
    assert by[a].fleet_cleared and by[a].won is True and by[b].won is False


async def test_no_solo_after_a_normal_win(fast):
    m, a, b, wa, wb, saved = await started()
    m._disarm()
    for c in ALL_SHOTS:
        m.turn = a
        await m.shoot(a, c)
    assert m.end_reason == "fleet_sunk" and m.solo is None and saved

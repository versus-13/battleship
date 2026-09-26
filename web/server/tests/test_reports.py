"""Reports on the opponent: bound to a match, one per match, the name threshold, files for review."""
import uuid

import pytest

from app.config import settings
from app.matchmaking import registry

from .test_ws import new_player, open_ws, recv_until, tc  # noqa: F401  (tc is a fixture)


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "reports_dir", str(tmp_path))
    return tmp_path


def named(tc, name):
    p = new_player(tc)
    assert tc.put("/api/players/me/name", json={"name": name}, headers=p["headers"]).status_code == 200
    return p


def match(tc, host, guest):
    """A room of host joined by guest (placement phase: they have seen each other's names)."""
    room = tc.post("/api/rooms", headers=host["headers"]).json()
    assert tc.post(f"/api/rooms/{room['code']}/join", headers=guest["headers"]).status_code == 200
    return room["match_id"]


def end(tc, match_id, player):
    ws, _ = open_ws(tc, match_id, player)
    ws.send_json({"t": "leave"})
    recv_until(ws, "game_over")


def report(tc, match_id, player, reason):
    r = tc.post(f"/api/matches/{match_id}/report", json={"reason": reason}, headers=player["headers"])
    assert r.status_code == 204 and r.content == b""        # the reporter learns nothing else
    return r


def count(tc):
    from sqlalchemy import func, select
    from app.db import SessionLocal
    from app.models import Report

    async def q():
        async with SessionLocal() as s:
            return await s.scalar(select(func.count()).select_from(Report))
    return tc.portal.call(q)


def test_one_report_per_match_and_only_participants(tc, reports_dir):
    a, b, stranger = named(tc, "Алиса"), named(tc, "Боб"), named(tc, "Чужой")
    mid = match(tc, a, b)
    report(tc, mid, b, "stalling")
    report(tc, mid, b, "cheating")                 # the second one from b is ignored silently
    report(tc, mid, stranger, "name")              # did not play — ignored
    report(tc, str(uuid.uuid4()), b, "name")        # no such match
    assert count(tc) == 1 and list(reports_dir.iterdir()) == []   # stalling: DB only
    assert tc.post(f"/api/matches/{mid}/report", json={"reason": "spam"}, headers=a["headers"]).status_code == 422


def test_report_after_the_match_left_memory(tc, reports_dir):
    a, b = named(tc, "Алиса"), named(tc, "Боб")
    mid = match(tc, a, b)
    end(tc, mid, a)
    registry.matches.pop(uuid.UUID(mid))           # only the h2h_matches row is left
    report(tc, mid, b, "bug")
    files = list(reports_dir.iterdir())
    assert count(tc) == 1 and len(files) == 1 and "_bug_" in files[0].name
    text = files[0].read_text()
    assert mid in text and "Алиса#" in text and "Боб#" in text and "--match " + mid in text


def test_cheating_goes_to_a_file_every_time(tc, reports_dir):
    suspect = named(tc, "Шулер")
    for i in range(2):
        other = named(tc, f"Сосед {'аб'[i]}")
        mid = match(tc, other, suspect)
        report(tc, mid, other, "cheating")
        end(tc, mid, other)
    files = sorted(reports_dir.iterdir())
    assert len(files) == 2 and all("_cheating_" in f.name for f in files)
    assert any("всего жалоб на читерство на этого игрока: 2 (от 2 разных игроков)" in f.read_text() for f in files)


def test_name_hidden_after_threshold_of_different_players(tc, reports_dir):
    villain = named(tc, "Злодей")
    reasons = ["name", "impersonation", "name"]    # impersonation counts towards the same threshold
    for i, reason in enumerate(reasons):
        me = tc.get("/api/players/me", headers=villain["headers"]).json()
        assert me["name"] == "Злодей" and me["name_hidden"] is False
        reporter = named(tc, f"Судья {'абв'[i]}")
        mid = match(tc, reporter, villain)
        report(tc, mid, reporter, reason)
        end(tc, mid, reporter)
    me = tc.get("/api/players/me", headers=villain["headers"]).json()
    assert me["name"] is None and me["name_hidden"] is True
    assert list(reports_dir.iterdir()) == []

    # the hidden name cannot come back (case does not matter); a new one can, right away
    r = tc.put("/api/players/me/name", json={"name": "злодей"}, headers=villain["headers"])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "name_hidden"
    assert tc.put("/api/players/me/name", json={"name": "Герой"}, headers=villain["headers"]).status_code == 200
    me = tc.get("/api/players/me", headers=villain["headers"]).json()
    assert me["name"] == "Герой" and me["name_hidden"] is False

    # reports on the old name do not count against the new one
    reporter = named(tc, "Судья г")
    mid = match(tc, reporter, villain)
    report(tc, mid, reporter, "name")
    assert tc.get("/api/players/me", headers=villain["headers"]).json()["name"] == "Герой"


def test_two_reports_from_one_player_do_not_hide_a_name(tc, reports_dir):
    victim, grudge = named(tc, "Победитель"), named(tc, "Обиженный")
    for _ in range(3):
        mid = match(tc, grudge, victim)
        report(tc, mid, grudge, "name")
        end(tc, mid, grudge)
    assert tc.get("/api/players/me", headers=victim["headers"]).json()["name"] == "Победитель"

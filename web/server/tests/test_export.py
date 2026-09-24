"""The JSONL export is readable by the original telemetry.GameLog from model/ (numpy, no torch)."""
import copy
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import GameLog
from scripts.export_logs import row_to_gamelog

from .conftest import ALL_SHOTS, SHIPS

MODEL_DIR = Path(__file__).resolve().parents[3] / "model"


async def test_export_row_matches_gamelog_format(client, player):
    body = {
        "client_game_id": "11111111-2222-3333-4444-555555555555", "mode": "h2m", "client": "web",
        "client_info": {"placement": "random"},
        "logs": [{"attacker": {"kind": "player"}, "defender": {"kind": "model_board"},
                  "ships": copy.deepcopy(SHIPS), "shots": list(ALL_SHOTS), "fleet_cleared": True, "won": True,
                  "think_ms": list(range(20)), "started_at": 1_800_000_000.0}],
    }
    r = await client.post("/api/games", json=body, headers=player["headers"])
    assert r.status_code == 201, r.text
    async with SessionLocal() as s:
        row = (await s.scalars(select(GameLog))).one()
    d = row_to_gamelog(row)
    assert d["shooter"].startswith("human:") and d["placer"] == "generator:client"
    assert d["placement"][0] == [4, 0, 0, 1] and d["placement"][3] == [2, 5, 0, 1]
    assert d["outcome"] == "finished" and d["think_ms"] == list(range(20))
    row.fleet_cleared, row.won = False, False
    assert row_to_gamelog(row)["outcome"] == "lost"
    row.won = None
    assert row_to_gamelog(row)["outcome"] == "abandoned"
    assert d["client"]["placement"] == "random" and d["client"]["mode"] == "h2m"
    line = json.dumps(d)

    sys.path.insert(0, str(MODEL_DIR))
    pytest.importorskip("numpy")
    from battleship.telemetry import GameLog as GL, replay, validate_placement, rules_from_dict
    log = GL.from_json(line)
    assert validate_placement(log.placement, rules_from_dict(log.rules)) == (True, "ok")
    steps = list(replay(log))               # replay yields a live Game — by the end it has been shot through
    assert len(steps) == 20 and steps[-1][0].done and steps[-1][0].n_shots == 20

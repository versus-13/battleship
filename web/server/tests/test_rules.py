"""Byte-for-byte equivalence of rules.py with model/battleship/game.py via fixtures."""
import json
from pathlib import Path

import pytest

from app.rules import Board, IllegalShot, PlacementError, replay, validate_placement

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "engine.json"


@pytest.fixture(scope="module")
def fx():
    return json.loads(FIXTURES.read_text())


def mask_hex(m: bytearray) -> str:
    return f"{int(''.join('1' if v else '0' for v in m), 2):025x}"


def test_fixtures_replay_matches_game_py(fx):
    assert fx["rules"]["size"] == 10
    for g in fx["games"]:
        board = Board(validate_placement(g["ships"]))
        for step in g["steps"]:
            out = board.shoot(step["s"])
            assert out.result == step["r"]
            assert mask_hex(board.known) == step["k"]
            assert mask_hex(board.hit) == step["h"]
            assert mask_hex(board.sunk) == step["z"]
            assert [board.alive[s] for s in fx["rules"]["ship_sizes"]] == step["a"]
        assert board.n_shots == g["n_shots"]
        assert board.done == g["done"]


def test_invalid_placements(fx):
    for bad in fx["invalid_placements"]:
        with pytest.raises(PlacementError):
            validate_placement(bad["ships"])
    canon = validate_placement(fx["valid_placement"])
    assert [len(s) for s in canon] == [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]


def test_canonical_order_is_stable(fx):
    ships = fx["valid_placement"]
    shuffled = list(reversed(ships))
    assert validate_placement(shuffled) == validate_placement(ships)


def test_sunk_reveals_perimeter_and_revealed_is_new_cells_only():
    ships = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]
    b = Board(validate_placement(ships))
    assert b.shoot(11).result == 0            # miss, cell 11 is opened
    b.shoot(0); b.shoot(1); b.shoot(2)
    out = b.shoot(3)
    assert out.result == 2
    assert out.sunk_cells == [0, 1, 2, 3]
    assert 11 not in out.revealed             # was already opened
    assert set(out.revealed) == {4, 10, 12, 13, 14}
    assert b.n_shots == 5


def test_illegal_shot_on_revealed_cell():
    ships = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]
    with pytest.raises(IllegalShot):
        replay(ships, [70, 60])                # 60 is auto-revealed after sinking 70
    with pytest.raises(IllegalShot):
        replay(ships, [5, 5])
    with pytest.raises(IllegalShot):
        replay(ships, [100])


def test_full_clear():
    ships = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]
    b = replay(ships, [c for s in ships for c in s])
    assert b.done and b.n_shots == 20
    assert all(v == 0 for v in b.alive.values())

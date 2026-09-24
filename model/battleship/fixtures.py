"""
Fixtures for cross-checking the engines (the numpy-free Python server, the TS client)
against game.py.

    python -m battleship.fixtures --out ../web/fixtures/engine.json

Random games: half of the shots by the heuristic, half random. For every step —
the result and the known/hit/sunk masks after the shot (hex, 100 bits), plus a set
of deliberately invalid placements to test validate_placement.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from .agents import HuntTargetAgent, RandomAgent
from .game import Game, Rules
from .telemetry import placement_from_ships, validate_placement


def mask_hex(m: np.ndarray) -> str:
    bits = "".join("1" if v else "0" for v in m.ravel())
    return f"{int(bits, 2):025x}"


def game_ships(game: Game) -> list:
    n = game.rules.size
    return [sorted(r * n + c for r, c in s.cells) for s in game.ships]


INVALID = [
    {"why": "касание углом", "ships": [[0, 1, 2, 3], [14, 15, 16], [30, 31, 32], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]},
    {"why": "не на прямой", "ships": [[0, 1, 2, 13], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]},
    {"why": "лишняя клетка", "ships": [[0, 1, 2, 3, 4], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]},
    {"why": "состав флота", "ships": [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57, 58], [70], [72], [74], [76]]},
    {"why": "вне поля", "ships": [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [100]]},
    {"why": "пересечение", "ships": [[0, 1, 2, 3], [30, 31, 32], [32, 33, 34], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]},
    {"why": "девять кораблей", "ships": [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74]]},
]
VALID = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]


def _valid_by_original(ships, rules: Rules) -> bool:
    """The original validate_placement works on [size,r,c,h]; invalid cell lists
    (not in a line, out of the board) never reach it — the adapter rejects them first."""
    n = rules.size
    for cells in ships:
        cells = sorted(cells)
        if any(not (0 <= x < n * n) for x in cells):
            return False
        rows, cols = [x // n for x in cells], [x % n for x in cells]
        straight_h = len(set(rows)) == 1 and cols == list(range(cols[0], cols[0] + len(cells)))
        straight_v = len(set(cols)) == 1 and rows == list(range(rows[0], rows[0] + len(cells)))
        if not (straight_h or straight_v):
            return False
    ok, _ = validate_placement(placement_from_ships(ships, n), rules)
    return ok


def make_fixtures(n_games: int, seed: int, rules: Rules = Rules()) -> dict:
    rng = np.random.default_rng(seed)
    hunt, rand = HuntTargetAgent(rng), RandomAgent(rng)
    games = []
    for _ in range(n_games):
        game = Game(rules, rng)
        steps = []
        stop_at = int(rng.integers(5, 101)) if rng.random() < 0.3 else 10_000
        while not game.done and len(steps) < stop_at:
            agent = hunt if rng.random() < 0.5 else rand
            r, c = agent.act(game)
            res = game.shoot(r, c)
            steps.append({
                "s": r * rules.size + c,
                "r": res,
                "k": mask_hex(game.known),
                "h": mask_hex(game.hit),
                "z": mask_hex(game.sunk),
                "a": [game.alive[s] for s in rules.ship_sizes],
            })
        games.append({"ships": game_ships(game), "steps": steps, "n_shots": game.n_shots, "done": game.done})

    for b in INVALID:
        assert not _valid_by_original(b["ships"], rules), f"fixture must be invalid: {b['why']}"
    assert _valid_by_original(VALID, rules)

    return {
        "rules": {"size": rules.size, "fleet": list(rules.fleet), "ship_sizes": list(rules.ship_sizes)},
        "mask_encoding": "hex, 100 бит, бит 0 (старший) = клетка 0",
        "games": games,
        "invalid_placements": INVALID,
        "valid_placement": VALID,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../web/fixtures/engine.json")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    fx = make_fixtures(args.games, args.seed)
    with open(args.out, "w") as f:
        json.dump(fx, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: партий {len(fx['games'])}, шагов {sum(len(g['steps']) for g in fx['games'])}")


if __name__ == "__main__":
    main()

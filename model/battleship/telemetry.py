"""
Telemetry: a compact game log + exact replay.

Key idea — log the seed, not the states. The ship placement and the order of
shots fully determine the game: any intermediate state is restored by replay.
A game is ~80 bytes instead of a megabyte of tensors, and a full training
dataset can still be built from the log.

The logging unit is ONE attacker against ONE board. A human-vs-human match is
two logs (each player shoots at the opponent's board). This way human and
model land in one table and compare directly.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Iterator, Tuple

import numpy as np

from .game import Game, Rules, Ship, ship_cells
from .selfplay import Dataset

LOG_VERSION = 1


# --------------------------------------------------------------------------- #
#  Format
# --------------------------------------------------------------------------- #
@dataclass
class GameLog:
    """One attack of one player on one board."""
    game_id: str
    rules: Dict[str, Any]
    placement: List[List[int]]      # [[size, r, c, horizontal], ...]
    shots: List[int]                # cell indices 0..99 in shooting order
    shooter: str                    # 'human:ab12' | 'model:net-v3' | 'heuristic:placement-count'
    placer: str                     # who placed the ships
    outcome: str = "finished"       # finished | abandoned
    match_id: Optional[str] = None  # links the two logs of one match
    started_at: Optional[float] = None
    think_ms: Optional[List[int]] = None   # time per move, ms
    client: Dict[str, Any] = field(default_factory=dict)
    version: int = LOG_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @staticmethod
    def from_json(s: str) -> "GameLog":
        return GameLog(**json.loads(s))

    @property
    def n_shots(self) -> int:
        return len(self.shots)


def rules_to_dict(rules: Rules) -> Dict[str, Any]:
    return {
        "size": rules.size,
        "fleet": [list(x) for x in rules.fleet],
        "diagonal_touch_forbidden": rules.diagonal_touch_forbidden,
        "auto_reveal_around_sunk": rules.auto_reveal_around_sunk,
    }


def rules_from_dict(d: Dict[str, Any]) -> Rules:
    return Rules(
        size=d["size"],
        fleet=tuple(tuple(x) for x in d["fleet"]),
        diagonal_touch_forbidden=d["diagonal_touch_forbidden"],
        auto_reveal_around_sunk=d["auto_reveal_around_sunk"],
    )


# --------------------------------------------------------------------------- #
#  Board <-> compact placement
# --------------------------------------------------------------------------- #
def placement_from_game(game: Game) -> List[List[int]]:
    out = []
    for s in game.ships:
        (r0, c0) = s.cells[0]
        horizontal = 1 if (s.size == 1 or s.cells[1][0] == r0) else 0
        out.append([s.size, r0, c0, horizontal])
    return out


def game_from_placement(placement, rules: Rules) -> Game:
    """Restore the board from the compact record."""
    n = rules.size
    grid = np.zeros((n, n), dtype=np.int16)
    ships: List[Ship] = []
    for i, (size, r, c, horizontal) in enumerate(placement, start=1):
        cells = ship_cells(r, c, size, bool(horizontal))
        for (rr, cc) in cells:
            grid[rr, cc] = i
        ships.append(Ship(i, size, cells))
    return Game(rules, grid=grid, ships=ships)


def validate_placement(placement, rules: Rules) -> Tuple[bool, str]:
    """Check that the placement is legal — mandatory for data coming from a client."""
    n = rules.size
    grid = np.zeros((n, n), dtype=np.int16)
    want = {}
    for s, c in rules.fleet:
        want[s] = want.get(s, 0) + c
    got: Dict[int, int] = {}
    for i, item in enumerate(placement, start=1):
        if len(item) != 4:
            return False, "запись корабля должна быть [size, r, c, horizontal]"
        size, r, c, horizontal = item
        got[size] = got.get(size, 0) + 1
        cells = ship_cells(r, c, size, bool(horizontal))
        for (rr, cc) in cells:
            if not (0 <= rr < n and 0 <= cc < n):
                return False, f"корабль {i} выходит за поле"
        for (rr, cc) in cells:
            r0, r1 = max(0, rr - 1), min(n, rr + 2)
            c0, c1 = max(0, cc - 1), min(n, cc + 2)
            if rules.diagonal_touch_forbidden:
                if grid[r0:r1, c0:c1].any():
                    return False, f"корабль {i} касается другого"
            else:
                if grid[rr, cc]:
                    return False, f"корабль {i} накладывается на другой"
        for (rr, cc) in cells:
            grid[rr, cc] = i
    if got != want:
        return False, f"состав флота не совпадает: прислано {got}, ожидалось {want}"
    return True, "ok"


# --------------------------------------------------------------------------- #
#  Replay
# --------------------------------------------------------------------------- #
def replay(log: GameLog) -> Iterator[Tuple[Game, int]]:
    """
    Walk through the game again. At every step yield the state BEFORE the shot
    and the shot itself. The state is a live Game object; do not modify it.
    """
    rules = rules_from_dict(log.rules)
    game = game_from_placement(log.placement, rules)
    n = rules.size
    for idx in log.shots:
        r, c = idx // n, idx % n
        if game.known[r, c]:
            # a shot at an already opened cell: a broken log, no point going further
            return
        yield game, idx
        game.shoot(r, c)


def log_to_dataset(log: GameLog, keep_prob: float = 1.0,
                   rng: Optional[np.random.Generator] = None) -> Optional[Dataset]:
    """Turn a log into training samples — the same format as self-play."""
    rng = rng or np.random.default_rng()
    obs, tgt, msk = [], [], []
    truth = None
    for game, _ in replay(log):
        if truth is None:
            truth = game.occupancy()
        if keep_prob >= 1.0 or rng.random() < keep_prob:
            obs.append(game.observation())
            tgt.append(truth)
            msk.append(game.unknown.astype(np.float32))
    if not obs:
        return None
    return Dataset(np.stack(obs), np.stack(tgt), np.stack(msk))


def logs_to_dataset(logs: List[GameLog], keep_prob: float = 1.0,
                    rng: Optional[np.random.Generator] = None) -> Optional[Dataset]:
    parts = [d for d in (log_to_dataset(l, keep_prob, rng) for l in logs) if d is not None]
    return Dataset.concat(parts) if parts else None


# --------------------------------------------------------------------------- #
#  Recording during a game
# --------------------------------------------------------------------------- #
class Recorder:
    """Accumulates shots as the game goes and returns a finished GameLog."""

    def __init__(self, game: Game, shooter: str, placer: str,
                 match_id: Optional[str] = None, client: Optional[dict] = None):
        self.game = game
        self.shooter = shooter
        self.placer = placer
        self.match_id = match_id
        self.client = client or {}
        self.game_id = uuid.uuid4().hex[:16]
        self.started_at = time.time()
        self.shots: List[int] = []
        self.think_ms: List[int] = []
        self._last = time.time()
        self._placement = placement_from_game(game)
        self._rules = rules_to_dict(game.rules)

    def record(self, r: int, c: int):
        n = self.game.rules.size
        self.shots.append(r * n + c)
        now = time.time()
        self.think_ms.append(int((now - self._last) * 1000))
        self._last = now

    def finish(self, outcome: str = "finished") -> GameLog:
        return GameLog(
            game_id=self.game_id,
            rules=self._rules,
            placement=self._placement,
            shots=self.shots,
            shooter=self.shooter,
            placer=self.placer,
            outcome=outcome,
            match_id=self.match_id,
            started_at=self.started_at,
            think_ms=self.think_ms,
            client=self.client,
        )


# --------------------------------------------------------------------------- #
#  Adapters to the web client/server format: a ship = a list of cell indices
# --------------------------------------------------------------------------- #
def placement_from_ships(ships: List[List[int]], n: int = 10) -> List[List[int]]:
    """[[idx, ...] × 10] (idx = r*n + c) -> [[size, r, c, horizontal], ...]."""
    out = []
    for cells in ships:
        cells = sorted(int(x) for x in cells)
        r0, c0 = cells[0] // n, cells[0] % n
        horizontal = 1 if (len(cells) == 1 or cells[1] // n == r0) else 0
        out.append([len(cells), r0, c0, horizontal])
    return out


def ships_from_placement(placement: List[List[int]], n: int = 10) -> List[List[int]]:
    """The reverse: [[size, r, c, horizontal], ...] -> [[idx, ...], ...]."""
    return [[rr * n + cc for (rr, cc) in ship_cells(r, c, size, bool(h))]
            for (size, r, c, h) in placement]

"""
Battleship rules without numpy — a mirror of model/battleship/game.py.

Cells are indices 0..99, idx = r*10 + c. A placement is a list of ships, each
a list of indices. Shot semantics repeat Game.shoot: a shot at an already
opened cell is an error, a sink automatically opens the perimeter (those cells
do not count as shots). Equivalence with game.py is verified by the test on
web/fixtures/engine.json.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

N = 10
FLEET = ((4, 1), (3, 2), (2, 3), (1, 4))
SHIP_SIZES = (4, 3, 2, 1)
N_SHIPS = sum(c for _, c in FLEET)
TOTAL_CELLS = sum(s * c for s, c in FLEET)
MISS, HIT, SUNK = 0, 1, 2
EXTRA_TURN_ON_HIT = True


class PlacementError(ValueError):
    pass


class IllegalShot(ValueError):
    pass


def neighbours(idx: int) -> List[int]:
    """The cell and its 3×3 neighbourhood within the board."""
    r, c = divmod(idx, N)
    out = []
    for rr in range(max(0, r - 1), min(N, r + 2)):
        for cc in range(max(0, c - 1), min(N, c + 2)):
            out.append(rr * N + cc)
    return out


def validate_placement(ships: Sequence[Sequence[int]]) -> List[List[int]]:
    """Returns the canonical form: ships by size descending, then by first cell;
    cells inside are sorted. Raises PlacementError."""
    if len(ships) != N_SHIPS:
        raise PlacementError(f"кораблей {len(ships)}, ожидается {N_SHIPS}")
    canon: List[List[int]] = []
    seen: set[int] = set()
    for cells in ships:
        try:
            cells = sorted(int(x) for x in cells)
        except (TypeError, ValueError):
            raise PlacementError("клетка не число")
        if not cells or any(not (0 <= x < N * N) for x in cells):
            raise PlacementError("клетка вне поля")
        if len(set(cells)) != len(cells):
            raise PlacementError("повтор клетки внутри корабля")
        rows = [x // N for x in cells]
        cols = [x % N for x in cells]
        straight_h = len(set(rows)) == 1 and cols == list(range(cols[0], cols[0] + len(cells)))
        straight_v = len(set(cols)) == 1 and rows == list(range(rows[0], rows[0] + len(cells)))
        if not (straight_h or straight_v):
            raise PlacementError("корабль не на прямой")
        if seen & set(cells):
            raise PlacementError("корабли пересекаются")
        seen |= set(cells)
        canon.append(cells)
    if Counter(len(s) for s in canon) != Counter({s: c for s, c in FLEET}):
        raise PlacementError("неверный состав флота")
    for i in range(len(canon)):
        for j in range(i + 1, len(canon)):
            for a in canon[i]:
                for b in canon[j]:
                    if abs(a // N - b // N) <= 1 and abs(a % N - b % N) <= 1:
                        raise PlacementError("корабли соприкасаются")
    canon.sort(key=lambda s: (-len(s), s[0]))
    return canon


@dataclass
class ShotOutcome:
    result: int
    sunk_cells: List[int] = field(default_factory=list)
    revealed: List[int] = field(default_factory=list)   # auto-revealed perimeter (new cells only)


class Board:
    """One board under fire. Keeps only what the referee needs."""

    def __init__(self, ships: Sequence[Sequence[int]]):
        self.ships: List[List[int]] = [list(s) for s in ships]
        self.grid = [0] * (N * N)            # 0 — water, otherwise ship number (1..10)
        for sid, cells in enumerate(self.ships, start=1):
            for x in cells:
                self.grid[x] = sid
        self.hits_per_ship = [0] * (len(self.ships) + 1)
        self.known = bytearray(N * N)
        self.hit = bytearray(N * N)
        self.sunk = bytearray(N * N)
        self.n_shots = 0
        self.alive = {s: c for s, c in FLEET}

    @property
    def done(self) -> bool:
        return all(v == 0 for v in self.alive.values())

    def shoot(self, idx: int) -> ShotOutcome:
        if not (0 <= idx < N * N):
            raise IllegalShot(f"клетка {idx} вне поля")
        if self.known[idx]:
            raise IllegalShot(f"клетка {idx} уже открыта")
        self.n_shots += 1
        self.known[idx] = 1
        sid = self.grid[idx]
        if sid == 0:
            return ShotOutcome(MISS)
        self.hit[idx] = 1
        self.hits_per_ship[sid] += 1
        cells = self.ships[sid - 1]
        if self.hits_per_ship[sid] < len(cells):
            return ShotOutcome(HIT)
        self.alive[len(cells)] -= 1
        revealed = []
        for x in cells:
            self.sunk[x] = 1
        for x in cells:
            for nb in neighbours(x):
                if not self.known[nb]:
                    self.known[nb] = 1
                    revealed.append(nb)
        return ShotOutcome(SUNK, sorted(cells), sorted(revealed))

    # ---- visible state ----
    def enemy_view(self) -> dict:
        """What the attacker sees: miss / hit / sunk for the opened cells."""
        cells = {}
        for i in range(N * N):
            if not self.known[i]:
                continue
            cells[i] = "sunk" if self.sunk[i] else ("hit" if self.hit[i] else "miss")
        return cells

    def owner_view(self) -> dict:
        """What the board owner sees: own ships and where they were hit."""
        return {
            "ships": self.ships,
            "hits": [i for i in range(N * N) if self.hit[i]],
            "revealed": [i for i in range(N * N) if self.known[i] and not self.hit[i]],
        }


def replay(ships: Sequence[Sequence[int]], shots: Iterable[int]) -> Board:
    """Replays a log. Raises IllegalShot if the sequence is illegal."""
    board = Board(ships)
    for idx in shots:
        board.shoot(int(idx))
    return board

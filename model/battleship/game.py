"""
Rules and environment of Battleship (single-player version: how many shots
does the agent need to uncover the opponent's board).

The whole board is stored as numpy arrays so that observation encoding is
dirt cheap — data generation is bottlenecked exactly there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

import numpy as np

# (ship size, count)
RUSSIAN_FLEET = ((4, 1), (3, 2), (2, 3), (1, 4))   # 20 cells, Russian classic
CLASSIC_FLEET = ((5, 1), (4, 1), (3, 2), (2, 1))   # 17 cells, Hasbro


@dataclass(frozen=True)
class Rules:
    size: int = 10
    fleet: Tuple[Tuple[int, int], ...] = RUSSIAN_FLEET
    # ships cannot touch, not even diagonally
    diagonal_touch_forbidden: bool = True
    # after a sink, automatically open the surrounding cells (they are guaranteed empty)
    auto_reveal_around_sunk: bool = True

    @property
    def ship_sizes(self) -> Tuple[int, ...]:
        """Unique ship sizes, largest first."""
        return tuple(sorted({s for s, _ in self.fleet}, reverse=True))

    @property
    def total_ship_cells(self) -> int:
        return sum(s * c for s, c in self.fleet)

    @property
    def n_ships(self) -> int:
        return sum(c for _, c in self.fleet)

    @property
    def obs_channels(self) -> int:
        # 4 spatial planes + one scalar per ship size
        return 4 + len(self.ship_sizes)


@dataclass
class Ship:
    sid: int
    size: int
    cells: List[Tuple[int, int]]
    hits: int = 0

    @property
    def sunk(self) -> bool:
        return self.hits >= self.size


# --------------------------------------------------------------------------- #
#  Placement
# --------------------------------------------------------------------------- #
def _fits(grid: np.ndarray, cells, rules: Rules) -> bool:
    n = rules.size
    for (r, c) in cells:
        if not (0 <= r < n and 0 <= c < n):
            return False
    if rules.diagonal_touch_forbidden:
        for (r, c) in cells:
            r0, r1 = max(0, r - 1), min(n, r + 2)
            c0, c1 = max(0, c - 1), min(n, c + 2)
            if grid[r0:r1, c0:c1].any():
                return False
    else:
        for (r, c) in cells:
            if grid[r, c]:
                return False
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n and grid[rr, cc]:
                    return False
    return True


def ship_cells(r: int, c: int, size: int, horizontal: bool):
    if horizontal:
        return [(r, c + i) for i in range(size)]
    return [(r + i, c) for i in range(size)]


def random_placement(rules: Rules, rng: np.random.Generator):
    """
    Greedy sequential placement (big ships first) with restart.

    IMPORTANT: this is NOT a uniform sample from the set of all legal placements.
    The net will learn exactly this prior. If the opponent places differently,
    there will be a distribution shift. See README, "what is honestly broken".
    """
    n = rules.size
    while True:
        grid = np.zeros((n, n), dtype=np.int16)
        ships: List[Ship] = []
        sid = 0
        ok = True
        for size, count in rules.fleet:
            for _ in range(count):
                sid += 1
                placed = False
                for _try in range(300):
                    horizontal = bool(rng.integers(2)) or size == 1
                    if horizontal:
                        r = int(rng.integers(0, n))
                        c = int(rng.integers(0, n - size + 1))
                    else:
                        r = int(rng.integers(0, n - size + 1))
                        c = int(rng.integers(0, n))
                    cells = ship_cells(r, c, size, horizontal)
                    if _fits(grid, cells, rules):
                        for (rr, cc) in cells:
                            grid[rr, cc] = sid
                        ships.append(Ship(sid, size, cells))
                        placed = True
                        break
                if not placed:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return grid, ships


# --------------------------------------------------------------------------- #
#  Environment
# --------------------------------------------------------------------------- #
class Game:
    """One game. The agent shoots until the whole fleet is sunk."""

    MISS, HIT, SUNK = 0, 1, 2

    def __init__(self, rules: Rules = Rules(), rng: Optional[np.random.Generator] = None,
                 grid=None, ships=None):
        self.rules = rules
        self.rng = rng if rng is not None else np.random.default_rng()
        if grid is None:
            grid, ships = random_placement(rules, self.rng)
        self.grid = grid
        self.ships = ships
        self._by_id: Dict[int, Ship] = {s.sid: s for s in ships}

        n = rules.size
        self.known = np.zeros((n, n), dtype=bool)   # cell revealed (by a shot or automatically)
        self.hit = np.zeros((n, n), dtype=bool)     # hit
        self.sunk = np.zeros((n, n), dtype=bool)    # cell of a sunk ship
        self.n_shots = 0
        self.alive: Dict[int, int] = {}             # size -> how many are left
        for s, c in rules.fleet:
            self.alive[s] = self.alive.get(s, 0) + c

    # ---- state ----
    @property
    def done(self) -> bool:
        return all(v == 0 for v in self.alive.values())

    @property
    def unknown(self) -> np.ndarray:
        return ~self.known

    @property
    def open_hits(self) -> np.ndarray:
        """Hits on ships not yet sunk — the main source of information."""
        return self.hit & ~self.sunk

    def legal_moves(self) -> np.ndarray:
        return np.argwhere(self.unknown)

    # ---- dynamics ----
    def _reveal(self, r: int, c: int):
        self.known[r, c] = True

    def shoot(self, r: int, c: int) -> int:
        if self.known[r, c]:
            raise ValueError(f"cell ({r},{c}) is already revealed")
        self.n_shots += 1
        self._reveal(r, c)
        sid = int(self.grid[r, c])
        if sid == 0:
            return Game.MISS

        self.hit[r, c] = True
        ship = self._by_id[sid]
        ship.hits += 1
        if not ship.sunk:
            return Game.HIT

        self.alive[ship.size] -= 1
        n = self.rules.size
        for (rr, cc) in ship.cells:
            self.sunk[rr, cc] = True
        if self.rules.auto_reveal_around_sunk:
            for (rr, cc) in ship.cells:
                r0, r1 = max(0, rr - 1), min(n, rr + 2)
                c0, c1 = max(0, cc - 1), min(n, cc + 2)
                self.known[r0:r1, c0:c1] = True
        return Game.SUNK

    # ---- encoding for the net ----
    def observation(self) -> np.ndarray:
        """(C, n, n) float32. Everything the agent honestly knows."""
        n = self.rules.size
        ch = []
        ch.append(self.unknown)                 # 0: not shot yet
        ch.append(self.known & ~self.hit)       # 1: miss (or auto-revealed empty cell)
        ch.append(self.open_hits)               # 2: hit but not sunk
        ch.append(self.sunk)                    # 3: sunk
        obs = np.stack(ch).astype(np.float32)

        # scalar planes: the fraction of remaining ships of each size
        init = {s: c for s, c in self.rules.fleet}
        extra = []
        for s in self.rules.ship_sizes:
            extra.append(np.full((n, n), self.alive[s] / init[s], dtype=np.float32))
        return np.concatenate([obs, np.stack(extra)], axis=0)

    def occupancy(self) -> np.ndarray:
        """The true ship map (n, n) float32 — the training target."""
        return (self.grid > 0).astype(np.float32)

    def render(self) -> str:
        n = self.rules.size
        out = ["   " + " ".join(f"{c}" for c in range(n))]
        for r in range(n):
            row = []
            for c in range(n):
                if self.sunk[r, c]:
                    row.append("#")
                elif self.hit[r, c]:
                    row.append("X")
                elif self.known[r, c]:
                    row.append("·")
                else:
                    row.append("?")
            out.append(f"{r:2} " + " ".join(row))
        out.append(f"выстрелов: {self.n_shots}  осталось кораблей: {self.alive}")
        return "\n".join(out)

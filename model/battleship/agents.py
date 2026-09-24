"""
Non-trivial baselines — without them there is nothing to compare the net to.

An Agent is just an object with a method act(game) -> (r, c).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from .game import Game, Rules, ship_cells


class Agent:
    name = "agent"

    def act(self, game: Game) -> Tuple[int, int]:
        raise NotImplementedError

    def reset(self):
        pass


class RandomAgent(Agent):
    name = "random"

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else np.random.default_rng()

    def act(self, game: Game):
        moves = game.legal_moves()
        i = int(self.rng.integers(len(moves)))
        return int(moves[i][0]), int(moves[i][1])


class HuntTargetAgent(Agent):
    """
    The classic: while there are no wounded ships, shoot on a lattice with
    stride = the smallest ship alive; once we hit, finish it off by extending the line.
    """
    name = "hunt/target"

    def __init__(self, rng=None):
        self.rng = rng if rng is not None else np.random.default_rng()

    def act(self, game: Game):
        n = game.rules.size
        unknown = game.unknown
        open_hits = game.open_hits

        if open_hits.any():
            scores = np.full((n, n), -1.0)
            for (r, c) in np.argwhere(open_hits):
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if not (0 <= rr < n and 0 <= cc < n) or not unknown[rr, cc]:
                        continue
                    s = 1.0
                    # extending an already found line is much better
                    pr, pc = r - dr, c - dc
                    if 0 <= pr < n and 0 <= pc < n and open_hits[pr, pc]:
                        s += 10.0
                    scores[rr, cc] = max(scores[rr, cc], s)
            if (scores >= 0).any():
                return self._argmax_random(scores, scores >= 0)

        stride = min(s for s, k in game.alive.items() if k > 0)
        rows, cols = np.indices((n, n))
        parity = ((rows + cols) % stride == 0) & unknown
        if parity.any():
            return self._argmax_random(np.zeros((n, n)), parity)
        return self._argmax_random(np.zeros((n, n)), unknown)

    def _argmax_random(self, scores, mask):
        best = scores[mask].max()
        cand = np.argwhere(mask & (scores >= best - 1e-9))
        i = int(self.rng.integers(len(cand)))
        return int(cand[i][0]), int(cand[i][1])


# --------------------------------------------------------------------------- #
#  Placement counting — a strong classical baseline and a "teacher" for the net
# --------------------------------------------------------------------------- #
class PlacementIndex:
    """Precomputed masks of all positions of every ship size."""

    _cache: Dict[tuple, "PlacementIndex"] = {}

    def __init__(self, rules: Rules):
        n = rules.size
        self.rules = rules
        self.masks: Dict[int, np.ndarray] = {}
        self.neigh: Dict[int, np.ndarray] = {}
        for size in rules.ship_sizes:
            ms = []
            for horizontal in (True, False):
                if size == 1 and not horizontal:
                    continue
                rmax = n if horizontal else n - size + 1
                cmax = n - size + 1 if horizontal else n
                for r in range(rmax):
                    for c in range(cmax):
                        m = np.zeros((n, n), dtype=bool)
                        for (rr, cc) in ship_cells(r, c, size, horizontal):
                            m[rr, cc] = True
                        ms.append(m)
            M = np.stack(ms)                       # (P, n, n)
            self.masks[size] = M
            self.neigh[size] = _dilate(M)          # (P, n, n), includes the cells themselves

    @classmethod
    def get(cls, rules: Rules) -> "PlacementIndex":
        key = (rules.size, rules.fleet, rules.diagonal_touch_forbidden)
        if key not in cls._cache:
            cls._cache[key] = cls(rules)
        return cls._cache[key]


def _dilate(M: np.ndarray) -> np.ndarray:
    """Dilate the mask to the 8 neighbours (Chebyshev neighbourhood of radius 1)."""
    out = M.copy()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            out |= np.roll(np.roll(M, dr, axis=1), dc, axis=2) & _shift_valid(M.shape, dr, dc)
    return out


def _shift_valid(shape, dr, dc):
    n = shape[1]
    v = np.ones((n, n), dtype=bool)
    if dr == 1:
        v[0, :] = False
    elif dr == -1:
        v[-1, :] = False
    if dc == 1:
        v[:, 0] = False
    elif dc == -1:
        v[:, -1] = False
    return v


def placement_heatmap(game: Game, hit_bonus: float = 30.0) -> np.ndarray:
    """
    For each cell — the weighted number of legal placements of the remaining
    ships that cover it. An approximation of the posterior probability: ships
    are counted independently (which they are not), but it is fast.
    """
    idx = PlacementIndex.get(game.rules)
    n = game.rules.size
    forbidden = (game.known & ~game.hit) | game.sunk      # a ship cannot go here
    ship_known = game.hit | game.sunk                     # known ship cells
    open_hits = game.open_hits

    heat = np.zeros((n, n), dtype=np.float64)
    for size, left in game.alive.items():
        if left <= 0:
            continue
        M = idx.masks[size]
        N = idx.neigh[size]
        ok = ~(M & forbidden).any(axis=(1, 2))
        # the "ships do not touch" rule: any known ship cell next to a placement
        # must belong to that placement itself
        ok &= ~((N & ship_known & ~M).any(axis=(1, 2)))
        if not ok.any():
            continue
        covered = (M & open_hits).sum(axis=(1, 2))
        w = left * (hit_bonus ** covered)
        w = np.where(ok, w, 0.0)
        heat += np.tensordot(w, M.astype(np.float64), axes=(0, 0))
    return heat


class ProbabilityAgent(Agent):
    name = "placement-count"

    def __init__(self, rng=None, hit_bonus: float = 30.0):
        self.rng = rng if rng is not None else np.random.default_rng()
        self.hit_bonus = hit_bonus

    def act(self, game: Game):
        heat = placement_heatmap(game, self.hit_bonus)
        heat = np.where(game.unknown, heat, -1.0)
        best = heat.max()
        if best <= 0:  # degenerate case — shoot anywhere
            cand = game.legal_moves()
        else:
            cand = np.argwhere(heat >= best - 1e-9)
        i = int(self.rng.integers(len(cand)))
        return int(cand[i][0]), int(cand[i][1])


class EpsilonMix(Agent):
    """A mixture of policies to collect diverse states for the dataset."""
    name = "mix"

    def __init__(self, agents: List[Agent], probs: List[float], rng=None):
        self.agents = agents
        self.probs = np.array(probs, dtype=np.float64)
        self.probs /= self.probs.sum()
        self.rng = rng if rng is not None else np.random.default_rng()

    def act(self, game: Game):
        i = int(self.rng.choice(len(self.agents), p=self.probs))
        return self.agents[i].act(game)

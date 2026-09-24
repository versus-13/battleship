"""
Dataset generation and quality measurement.

Key idea: labelled data is free. We place the ships ourselves, so for any
state we know the right answer — the full fleet map. We train the net to
predict it from a partial observation; the loss is computed only over cells
not yet opened (there is nothing to learn from the opened ones).

Second point: the distribution of states depends on who played. A net trained
on the states of a random agent will never see the positions that arise for a
strong player. So we collect data with the policy currently in use
(a DAgger-like scheme) plus some noise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .game import Game, Rules
from .agents import Agent, RandomAgent, HuntTargetAgent, ProbabilityAgent


@dataclass
class Dataset:
    obs: np.ndarray      # (N, C, n, n) float32
    target: np.ndarray   # (N, n, n)   float32 — the true ship map
    mask: np.ndarray     # (N, n, n)   float32 — where to compute the loss (unopened cells)

    def __len__(self):
        return len(self.obs)

    @staticmethod
    def concat(parts: List["Dataset"]) -> "Dataset":
        return Dataset(
            np.concatenate([p.obs for p in parts]),
            np.concatenate([p.target for p in parts]),
            np.concatenate([p.mask for p in parts]),
        )


def play_game(rules: Rules, agent: Agent, rng: np.random.Generator,
              collect: bool = False, keep_prob: float = 1.0):
    """One game. Returns (number of shots, list of samples)."""
    game = Game(rules, rng)
    truth = game.occupancy()
    samples = []
    guard = rules.size * rules.size + 5
    while not game.done and guard > 0:
        guard -= 1
        if collect and (keep_prob >= 1.0 or rng.random() < keep_prob):
            samples.append((game.observation(), truth, game.unknown.astype(np.float32)))
        r, c = agent.act(game)
        game.shoot(r, c)
    return game.n_shots, samples


def generate(rules: Rules, agent: Agent, n_games: int, rng: np.random.Generator,
             keep_prob: float = 0.35, progress: bool = False) -> "tuple[Dataset, float]":
    obs, tgt, msk = [], [], []
    shots = []
    for i in range(n_games):
        s, samples = play_game(rules, agent, rng, collect=True, keep_prob=keep_prob)
        shots.append(s)
        for o, t, m in samples:
            obs.append(o)
            tgt.append(t)
            msk.append(m)
        if progress and (i + 1) % max(1, n_games // 10) == 0:
            print(f"  партий {i+1}/{n_games}, состояний {len(obs)}", flush=True)
    ds = Dataset(np.stack(obs), np.stack(tgt), np.stack(msk))
    return ds, float(np.mean(shots))


def evaluate(rules: Rules, agent: Agent, n_games: int, rng: np.random.Generator) -> dict:
    shots = [play_game(rules, agent, rng)[0] for _ in range(n_games)]
    shots = np.array(shots, dtype=np.float64)
    return {
        "agent": getattr(agent, "name", type(agent).__name__),
        "games": n_games,
        "mean": float(shots.mean()),
        "std": float(shots.std()),
        "median": float(np.median(shots)),
        "p90": float(np.percentile(shots, 90)),
        "best": int(shots.min()),
        "worst": int(shots.max()),
    }


def baseline_table(rules: Optional[Rules] = None, n_games: int = 200, seed: int = 0) -> List[dict]:
    rules = rules or Rules()
    rng = np.random.default_rng(seed)
    rows = []
    for agent in (RandomAgent(rng), HuntTargetAgent(rng), ProbabilityAgent(rng)):
        rows.append(evaluate(rules, agent, n_games, rng))
    return rows


def print_table(rows: List[dict]):
    head = f"{'агент':<18}{'ср. выстрелов':>15}{'медиана':>10}{'p90':>8}{'σ':>8}"
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{r['agent']:<18}{r['mean']:>15.2f}{r['median']:>10.1f}"
              f"{r['p90']:>8.1f}{r['std']:>8.2f}")
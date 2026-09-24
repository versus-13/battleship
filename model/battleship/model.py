"""
The net: fully convolutional, no downsampling.

The task is formulated not as "where to shoot" but as
    p(ship in the cell | everything I see)
for each of the 100 cells. This is a dense signal: one game gives ~50 images
with 100 labels each, and the labels are free — we generated the board
ourselves. The policy then follows trivially: argmax over unopened cells.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .game import Game, Rules
from .agents import Agent


class GlobalContext(nn.Module):
    """
    Cheaply pass global information: average over the board, run through an
    MLP, add back to every cell. Without this the net struggles to "count" how
    many ship cells are still unfound.
    """

    def __init__(self, ch: int):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(ch, ch), nn.ReLU(inplace=True), nn.Linear(ch, ch))

    def forward(self, x):
        g = x.mean(dim=(2, 3))
        g = self.fc(g)
        return x + g[:, :, None, None]


class ResBlock(nn.Module):
    def __init__(self, ch: int, use_global: bool = True):
        super().__init__()
        self.c1 = nn.Conv2d(ch, ch, 3, padding=1, bias=False)
        self.b1 = nn.BatchNorm2d(ch)
        self.c2 = nn.Conv2d(ch, ch, 3, padding=1, bias=False)
        self.b2 = nn.BatchNorm2d(ch)
        self.g = GlobalContext(ch) if use_global else nn.Identity()

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)), inplace=True)
        y = self.b2(self.c2(y))
        y = self.g(y)
        return F.relu(x + y, inplace=True)


class BattleshipNet(nn.Module):
    def __init__(self, in_ch: int, width: int = 64, blocks: int = 6, use_global: bool = True):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_ch, width, 3, padding=1, bias=False),
            nn.BatchNorm2d(width),
            nn.ReLU(inplace=True),
        )
        self.body = nn.Sequential(*[ResBlock(width, use_global) for _ in range(blocks)])
        self.head = nn.Conv2d(width, 1, 1)

    def forward(self, x):
        """(B, C, n, n) -> logits (B, n, n)"""
        x = self.stem(x)
        x = self.body(x)
        return self.head(x).squeeze(1)


# --------------------------------------------------------------------------- #
#  Board symmetries: the dihedral group D4, 8 transforms. Free augmentation.
# --------------------------------------------------------------------------- #
def dihedral(x: np.ndarray, k: int) -> np.ndarray:
    """k in 0..7. Works on (..., n, n)."""
    if k >= 4:
        x = np.flip(x, axis=-1)
    return np.rot90(x, k % 4, axes=(-2, -1))


def dihedral_inv(x: np.ndarray, k: int) -> np.ndarray:
    x = np.rot90(x, -(k % 4), axes=(-2, -1))
    if k >= 4:
        x = np.flip(x, axis=-1)
    return x


# --------------------------------------------------------------------------- #
class NeuralAgent(Agent):
    name = "neural"

    def __init__(self, net: BattleshipNet, device="cpu", rng=None,
                 temperature: float = 0.0, epsilon: float = 0.0, tta: bool = False):
        self.net = net
        self.device = device
        self.rng = rng if rng is not None else np.random.default_rng()
        self.temperature = temperature   # 0 = greedy
        self.epsilon = epsilon           # fraction of random moves
        self.tta = tta                   # average over the 8 symmetries

    @torch.no_grad()
    def probs(self, game: Game) -> np.ndarray:
        obs = game.observation()
        self.net.eval()
        if self.tta:
            batch = np.stack([np.ascontiguousarray(dihedral(obs, k)) for k in range(8)])
            t = torch.from_numpy(batch).to(self.device)
            logits = self.net(t).cpu().numpy()
            p = 1.0 / (1.0 + np.exp(-logits))
            p = np.mean([dihedral_inv(p[k], k) for k in range(8)], axis=0)
            return p
        t = torch.from_numpy(obs[None]).to(self.device)
        logit = self.net(t)[0].cpu().numpy()
        return 1.0 / (1.0 + np.exp(-logit))

    def act(self, game: Game):
        moves = game.legal_moves()
        if self.epsilon > 0 and self.rng.random() < self.epsilon:
            i = int(self.rng.integers(len(moves)))
            return int(moves[i][0]), int(moves[i][1])

        p = self.probs(game)
        p = np.where(game.unknown, p, -1.0)
        if self.temperature <= 0:
            best = p.max()
            cand = np.argwhere(p >= best - 1e-9)
            i = int(self.rng.integers(len(cand)))
            return int(cand[i][0]), int(cand[i][1])

        flat = p.flatten()
        mask = flat >= 0
        logits = np.where(mask, flat, -np.inf) / max(self.temperature, 1e-6)
        logits -= logits.max()
        w = np.exp(logits)
        w /= w.sum()
        i = int(self.rng.choice(len(w), p=w))
        return i // game.rules.size, i % game.rules.size

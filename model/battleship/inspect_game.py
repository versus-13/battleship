"""
See with your own eyes what the net thinks. Prints the game step by step:
the net's probability map on the left, the truth on the right.

    python -m battleship.inspect_game --ckpt net.pt --step        # advance on Enter
    python -m battleship.inspect_game --ckpt net.pt --compare     # next to the heuristic
"""
from __future__ import annotations

import argparse

import numpy as np
import torch

from .game import Game, Rules
from .agents import placement_heatmap, ProbabilityAgent
from .model import BattleshipNet, NeuralAgent

SHADES = " .:-=+*#%@"


def heat_str(p: np.ndarray, game: Game, mark=None) -> list:
    n = game.rules.size
    rows = ["    " + " ".join(f"{c}" for c in range(n))]
    for r in range(n):
        cells = []
        for c in range(n):
            if not game.unknown[r, c]:
                cells.append("#" if game.sunk[r, c] else ("X" if game.hit[r, c] else "·"))
            else:
                v = float(np.clip(p[r, c], 0, 1))
                ch = SHADES[min(len(SHADES) - 1, int(v * len(SHADES)))]
                cells.append(ch)
        line = f"{r:2}  " + " ".join(cells)
        if mark is not None and mark[0] == r:
            line += f"   <- ход в столбец {mark[1]}"
        rows.append(line)
    return rows


def truth_str(game: Game) -> list:
    n = game.rules.size
    rows = ["    " + " ".join(f"{c}" for c in range(n))]
    for r in range(n):
        rows.append(f"{r:2}  " + " ".join("O" if game.grid[r, c] else "." for c in range(n)))
    return rows


def side_by_side(a, b, gap="     |     "):
    out = []
    for i in range(max(len(a), len(b))):
        left = a[i] if i < len(a) else " " * len(a[0])
        right = b[i] if i < len(b) else ""
        out.append(f"{left:<32}{gap}{right}")
    return "\n".join(out)


def load(ckpt, device="cpu"):
    blob = torch.load(ckpt, map_location=device, weights_only=False)
    rules = blob["rules"]
    net = BattleshipNet(rules.obs_channels, blob["width"], blob["blocks"], blob["use_global"])
    net.load_state_dict(blob["state_dict"])
    net.to(device).eval()
    return net, rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default="net.pt")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--step", action="store_true", help="пауза на каждом ходу")
    ap.add_argument("--compare", action="store_true", help="показывать и эвристику")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    net, rules = load(args.ckpt, args.device)
    rng = np.random.default_rng(args.seed)
    agent = NeuralAgent(net, args.device, rng)
    game = Game(rules, rng)

    t = truth_str(game)
    step = 0
    while not game.done:
        p = agent.probs(game)
        r, c = agent.act(game)
        step += 1
        left = heat_str(p, game, mark=(r, c))
        print(f"\n=== ход {step}, выстрелов {game.n_shots} ===")
        print(f"{'сеть: p(корабль)':<32}     |     истина")
        print(side_by_side(left, t))
        if args.compare:
            h = placement_heatmap(game)
            h = h / max(h.max(), 1e-9)
            print("\nэвристика (нормированная):")
            print("\n".join(heat_str(h, game)))
        res = game.shoot(r, c)
        print(f"выстрел ({r},{c}) -> {['мимо','ранен','убит'][res]}")
        if args.step:
            if input("Enter — дальше, q — выход: ").strip().lower() == "q":
                return
    print(f"\nготово за {game.n_shots} выстрелов")


if __name__ == "__main__":
    main()

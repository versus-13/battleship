"""
Summary of game logs: move comparison with the model, split by phase,
the "shots to clear" table, placement statistics.

    python -m battleship.analyze --logs logs.jsonl --ckpt battleship/net.pt
    python -m battleship.analyze --logs /dev/null --stub-heuristic 40 --ckpt battleship/net.pt

Logs are JSONL in GameLog format (see web/server/scripts/export_logs.py).
--stub-heuristic N adds N heuristic games recorded via Recorder — to check the
metric against the table in CLAUDE.md and to see the "zero level".
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Dict, List

import numpy as np

from .agents import HuntTargetAgent
from .analysis import compare_moves, games_table, placement_stats, print_summary, split_by_phase
from .game import Game, Rules
from .telemetry import GameLog, Recorder


def read_logs(path: str) -> List[GameLog]:
    logs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                logs.append(GameLog.from_json(line))
    return logs


def stub_heuristic_logs(n: int, seed: int, rules: Rules = Rules()) -> List[GameLog]:
    rng = np.random.default_rng(seed)
    agent = HuntTargetAgent(rng)
    out = []
    for _ in range(n):
        game = Game(rules, rng)
        rec = Recorder(game, shooter="heuristic:hunt-target", placer="generator:random_placement")
        while not game.done:
            r, c = agent.act(game)
            rec.record(r, c)
            game.shoot(r, c)
        out.append(rec.finish())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", required=True, help="JSONL with GameLog records")
    ap.add_argument("--ckpt", default="battleship/net.pt")
    ap.add_argument("--stub-heuristic", type=int, default=0, metavar="N")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--max-games", type=int, default=0, help="cap the number of logs per comparison (0 = all)")
    args = ap.parse_args()

    logs = read_logs(args.logs)
    if args.stub_heuristic:
        logs += stub_heuristic_logs(args.stub_heuristic, args.seed)
    if not logs:
        print("логов нет")
        return
    print(f"логов: {len(logs)}")

    print_summary("\nвыстрелов до зачистки (только доигранные), по типу стрелка:", games_table(logs))
    print_summary("\nрасстановки, по типу расставлявшего:", placement_stats(logs))

    import torch  # noqa: F401  — imported only here so the tables above work without it
    from .inspect_game import load
    from .model import NeuralAgent

    net, _ = load(args.ckpt)
    model = NeuralAgent(net, tta=args.tta)

    by_kind: Dict[str, list] = defaultdict(list)
    for log in logs:
        kind = log.shooter.split(":")[0]
        if kind == "model":
            continue
        if args.max_games and len(by_kind[kind]) >= args.max_games:
            continue
        by_kind[kind].append(log)

    for kind, group in by_kind.items():
        rows = []
        for log in group:
            rows.extend(compare_moves(log, model.probs))
        print(f"\n=== {kind}: {len(group)} партий, {len(rows)} ходов против модели ===")
        for phase, summary in split_by_phase(rows).items():
            print_summary(f"  [{phase}]", summary)


if __name__ == "__main__":
    main()

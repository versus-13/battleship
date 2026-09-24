"""
Log analysis.

The main tool is counterfactual comparison. For every human move we ask the
model: what would YOU play from THIS SAME position? Both see the same
information on the same board, so the comparison is fair and not polluted by
luck in placement.

This yields ~55 comparisons per game instead of one. To catch a 1-shot
difference in means you need thousands of games; per move, dozens suffice.
"""
from __future__ import annotations

from collections import defaultdict
from typing import List, Dict, Any, Optional, Callable

import numpy as np

from .game import Game
from .telemetry import GameLog, replay


def _shot_result(game: Game, idx: int) -> str:
    n = game.rules.size
    r, c = idx // n, idx % n
    return "hit" if game.grid[r, c] else "miss"


def compare_moves(log: GameLog, prob_fn: Callable[[Game], np.ndarray]) -> List[Dict[str, Any]]:
    """
    prob_fn(game) -> probability map (n, n).
    Returns a comparison record for every move.
    """
    out = []
    for ply, (game, idx) in enumerate(replay(log)):
        n = game.rules.size
        r, c = idx // n, idx % n
        p = np.asarray(prob_fn(game), dtype=np.float64)
        p_masked = np.where(game.unknown, p, -1.0)

        p_best = float(p_masked.max())
        p_chosen = float(p_masked[r, c])
        best_cells = np.argwhere(p_masked >= p_best - 1e-9)
        # rank of the chosen cell among the available ones (0 = the model would pick it first)
        avail = p_masked[game.unknown]
        rank = int((avail > p_chosen + 1e-9).sum())

        out.append({
            "ply": ply,
            "shots_so_far": game.n_shots,
            "cell": idx,
            "result": _shot_result(game, idx),
            "p_model_at_choice": p_chosen,
            "p_model_best": p_best,
            "regret": p_best - p_chosen,          # how much probability was lost
            "rank": rank,                          # 0 = matches the model's choice
            "agreed": rank == 0,
            "n_unknown": int(game.unknown.sum()),
            "open_hits": int(game.open_hits.sum()),
            "model_would_pick": int(best_cells[0][0] * n + best_cells[0][1]),
            # would the model have hit, shooting instead of the human from this position
            "model_would_hit": bool(game.grid[best_cells[0][0], best_cells[0][1]]),
        })
    return out


def summarize_moves(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    reg = np.array([r["regret"] for r in rows])
    rank = np.array([r["rank"] for r in rows])
    agreed = np.array([r["agreed"] for r in rows])
    hit = np.array([r["result"] == "hit" for r in rows])
    mhit = np.array([r["model_would_hit"] for r in rows])
    return {
        "moves": len(rows),
        "agreement": float(agreed.mean()),
        "mean_regret": float(reg.mean()),
        "median_rank": float(np.median(rank)),
        "hit_rate_shooter": float(hit.mean()),
        "hit_rate_model": float(mhit.mean()),
        # positive = the model would hit more often from the same positions
        "hit_rate_delta": float(mhit.mean() - hit.mean()),
    }


def split_by_phase(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Where exactly the human and the model diverge. 'Hunt' and 'target' are
    different skills, averaging them together is meaningless.
    """
    buckets = defaultdict(list)
    for r in rows:
        phase = "добивание" if r["open_hits"] > 0 else "поиск"
        buckets[phase].append(r)
    return {k: summarize_moves(v) for k, v in buckets.items()}


def games_table(logs: List[GameLog]) -> Dict[str, Dict[str, Any]]:
    """
    Per-game summary by 'who shot'. The metric is the same as in offline
    measurements: how many shots it took to clear the board.
    """
    by = defaultdict(list)
    for l in logs:
        if l.outcome != "finished":
            continue
        kind = l.shooter.split(":")[0]
        by[kind].append(l.n_shots)
    out = {}
    for k, v in by.items():
        a = np.array(v, dtype=np.float64)
        out[k] = {
            "games": len(a),
            "mean": float(a.mean()),
            "sem": float(a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else float("nan"),
            "median": float(np.median(a)),
            "best": int(a.min()),
            "worst": int(a.max()),
        }
    return out


def placement_stats(logs: List[GameLog]) -> Dict[str, Any]:
    """
    How much human placements differ from our generator. Directly answers the
    README question about the prior shift.
    """
    by = defaultdict(lambda: {"edge": [], "corner_dist": [], "horizontal": []})
    for l in logs:
        n = l.rules["size"]
        kind = l.placer.split(":")[0]
        for (size, r, c, horiz) in l.placement:
            cells = [(r, c + i) for i in range(size)] if horiz else [(r + i, c) for i in range(size)]
            edge = sum(1 for (rr, cc) in cells if rr in (0, n - 1) or cc in (0, n - 1))
            by[kind]["edge"].append(edge / size)
            by[kind]["corner_dist"].append(
                float(np.mean([min(rr, n - 1 - rr) + min(cc, n - 1 - cc) for (rr, cc) in cells]))
            )
            if size > 1:
                by[kind]["horizontal"].append(float(horiz))
    out = {}
    for k, v in by.items():
        out[k] = {
            "ships": len(v["edge"]),
            "доля_клеток_у_края": float(np.mean(v["edge"])),
            "среднее_расстояние_до_края": float(np.mean(v["corner_dist"])),
            "доля_горизонтальных": float(np.mean(v["horizontal"])) if v["horizontal"] else float("nan"),
        }
    return out


def print_summary(title: str, d: Dict[str, Any]):
    print(title)
    for k, v in d.items():
        if isinstance(v, dict):
            inner = "  ".join(f"{kk}={vv:.3f}" if isinstance(vv, float) else f"{kk}={vv}"
                              for kk, vv in v.items())
            print(f"  {k:<12} {inner}")
        else:
            print(f"  {k:<12} {v:.4f}" if isinstance(v, float) else f"  {k:<12} {v}")

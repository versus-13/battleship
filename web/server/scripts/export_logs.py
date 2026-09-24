"""
Export of game logs to JSONL in the model/battleship/telemetry.GameLog format —
read directly by `python -m battleship.analyze` and `telemetry.logs_to_dataset()`.

    python -m scripts.export_logs --out logs.jsonl [--mode h2h] [--attacker player] [--all]

By default only games played to the end (fleet_cleared). --all adds unfinished ones:
useless for the shots metric but valuable as a source of human placements.
"""
import argparse
import asyncio
import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import GameLog
from app.rules import FLEET, N

# a mirror of telemetry.rules_to_dict(Rules()) — the server does not import model/
RULES_RU = {
    "size": N,
    "fleet": [list(x) for x in FLEET],
    "diagonal_touch_forbidden": True,
    "auto_reveal_around_sunk": True,
}


def placement_from_ships(ships, n=N):
    """[[idx, ...] × 10] -> [[size, r, c, horizontal], ...] — as in telemetry.py."""
    out = []
    for cells in ships:
        cells = sorted(int(x) for x in cells)
        r0, c0 = cells[0] // n, cells[0] % n
        horizontal = 1 if (len(cells) == 1 or cells[1] // n == r0) else 0
        out.append([len(cells), r0, c0, horizontal])
    return out


def tag(pid) -> str:
    return pid.hex[:4]


def row_to_gamelog(row: GameLog) -> dict:
    if row.attacker_kind == "player":
        shooter = f"human:{tag(row.attacker_player)}"
    else:
        shooter = row.attacker_label                      # model:<ver> | heuristic:<name>
    placer = f"human:{tag(row.defender_player)}" if row.defender_player else "generator:client"
    client = dict(row.client_info or {})
    client.update({"client": row.client, "client_version": row.client_version, "mode": row.mode})
    return {
        "game_id": str(row.id),
        "rules": row.rules or RULES_RU,
        "placement": placement_from_ships(row.ships),
        "shots": list(row.shots),
        "shooter": shooter,
        "placer": placer,
        # finished — the board was cleared (the "shots to clear" metric applies);
        # lost — played to the end but the opponent cleared first; abandoned — not finished
        "outcome": "finished" if row.fleet_cleared else ("lost" if row.won is not None else "abandoned"),
        "match_id": str(row.match_id) if row.match_id else None,
        "started_at": row.started_at.timestamp() if row.started_at else row.created_at.timestamp(),
        "think_ms": list(row.think_ms) if row.think_ms is not None else None,
        "client": client,
        "version": 1,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["h2m", "h2h"])
    ap.add_argument("--attacker", choices=["player", "model", "heuristic"])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    q = select(GameLog).order_by(GameLog.id)
    if not args.all:
        q = q.where(GameLog.fleet_cleared)
    if args.mode:
        q = q.where(GameLog.mode == args.mode)
    if args.attacker:
        q = q.where(GameLog.attacker_kind == args.attacker)

    n = 0
    async with SessionLocal() as session:
        rows = (await session.scalars(q)).all()
    with open(args.out, "w") as f:
        for row in rows:
            f.write(json.dumps(row_to_gamelog(row), ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    print(f"{args.out}: {n} логов")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import player_tag
from ..db import get_session
from ..models import GameLog, Player
from ..schemas import LeaderboardRow, Stats

router = APIRouter(prefix="/api", tags=["stats"])


async def player_stats(session: AsyncSession, pid: uuid.UUID) -> Stats:
    finished = GameLog.won.isnot(None)
    q = select(
        func.count().filter(finished),
        func.count().filter(GameLog.won.is_(True)),
        func.avg(GameLog.n_shots).filter(GameLog.fleet_cleared),
        func.min(GameLog.n_shots).filter(GameLog.fleet_cleared),
        func.count().filter(finished, GameLog.mode == "h2h"),
        func.count().filter(finished, GameLog.mode == "h2m"),
        func.count().filter(GameLog.won.is_(True), GameLog.mode == "h2h"),
    ).where(GameLog.attacker_player == pid, GameLog.attacker_kind == "player")
    games, wins, avg_shots, best, h2h, h2m, h2h_wins = (await session.execute(q)).one()
    return Stats(
        games=games, wins=wins,
        win_rate=round(wins / games, 3) if games else None,
        avg_shots=round(float(avg_shots), 2) if avg_shots is not None else None,
        best_shots=best, h2h_games=h2h, h2m_games=h2m, h2h_wins=h2h_wins,
    )


@router.get("/leaderboard", response_model=list[LeaderboardRow])
async def leaderboard(
    min_games: int = Query(default=5, ge=1, le=1000),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """
    Human-vs-human games only: the server is the referee there, no cheating.
    Two independent numbers: the match record (a match left early is a loss) and skill —
    mean shots over cleared boards only, which the opponent's behaviour cannot spoil.
    """
    games = func.count()
    wins = func.sum(case((GameLog.won.is_(True), 1), else_=0)).cast(Integer)
    avg_shots = func.avg(GameLog.n_shots).filter(GameLog.fleet_cleared)
    q = (
        select(GameLog.attacker_player, Player.name, games, wins, avg_shots)
        .join(Player, Player.id == GameLog.attacker_player)
        .where(GameLog.mode == "h2h", GameLog.attacker_kind == "player", GameLog.won.isnot(None))
        .group_by(GameLog.attacker_player, Player.name)
        .having(games >= min_games)
        .order_by((wins * 1.0 / games).desc(), avg_shots.asc().nulls_last())
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    return [
        LeaderboardRow(
            player_id=pid, name=name, tag=player_tag(pid), games=g, wins=w,
            win_rate=round(w / g, 3), avg_shots=round(float(a), 2) if a is not None else None,
        )
        for pid, name, g, w, a in rows
    ]

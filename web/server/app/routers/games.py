from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_player
from ..config import settings
from ..db import get_session
from ..models import GameLog, Player
from ..rules import IllegalShot, TOTAL_CELLS, replay
from ..schemas import GameLogIn, GamesIn, GamesOut, RejectedLog

router = APIRouter(prefix="/api/games", tags=["games"])

_recent: dict[uuid.UUID, deque] = defaultdict(deque)


def _rate_limited(pid: uuid.UUID) -> bool:
    now = time.monotonic()
    q = _recent[pid]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= settings.games_per_hour:
        return True
    q.append(now)
    return False


def attacker_label(log: GameLogIn) -> str:
    if log.attacker.kind == "player":
        return "player"
    return f"{log.attacker.kind}:{log.attacker.version or 'unknown'}"


def check_log(log: GameLogIn) -> str | None:
    """Rejection code or None. The placement was already checked by the pydantic validator."""
    try:
        board = replay(log.ships, log.shots)
    except IllegalShot:
        return "illegal_shot"
    if board.done != log.fleet_cleared:
        return "cleared_mismatch"
    return None


@router.post("", response_model=GamesOut, status_code=status.HTTP_201_CREATED)
async def post_games(
    body: GamesIn,
    player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    """Logs of a human-vs-model game. One or two logs: the human on the model's board and/or
    the model on the human's board. Each is verified by replay; rejecting one does not block the other."""
    if _rate_limited(player.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "слишком много партий за час")

    accepted, rejected = [], []
    for i, log in enumerate(body.logs):
        label = attacker_label(log)
        dup = await session.scalar(
            select(GameLog.id).where(GameLog.client_game_id == body.client_game_id,
                                     GameLog.attacker_label == label)
        )
        if dup is not None:
            rejected.append(RejectedLog(index=i, code="duplicate"))
            continue
        code = check_log(log)
        if code:
            rejected.append(RejectedLog(index=i, code=code))
            continue
        is_player_attacking = log.attacker.kind == "player"
        row = GameLog(
            client_game_id=body.client_game_id,
            mode=body.mode,
            attacker_kind=log.attacker.kind,
            attacker_player=player.id if is_player_attacking else None,
            attacker_label=label,
            defender_player=None if is_player_attacking else player.id,
            ships=log.ships,
            shots=log.shots,
            n_shots=len(log.shots),
            fleet_cleared=log.fleet_cleared,
            won=log.won,
            client=body.client,
            client_version=body.client_version,
            think_ms=log.think_ms,
            started_at=datetime.fromtimestamp(log.started_at, tz=timezone.utc) if log.started_at else None,
            client_info=body.client_info,
        )
        session.add(row)
        await session.flush()
        accepted.append(row.id)
    await session.commit()
    return GamesOut(accepted=accepted, rejected=rejected)

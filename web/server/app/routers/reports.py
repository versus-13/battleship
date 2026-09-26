"""
Reports on the opponent of an H2H match.

A report is always bound to a match: the reporter must have played it, the reported
player is the opponent (the server decides, not the client), one report per match per
reporter. The answer is always 204 — the reporter learns nothing beyond "thanks".

* name / impersonation — name_report_threshold different players reporting the current
  name hide it (the player is asked for a new one); reports on an old name do not touch
  a new one.
* stalling — stored only: the move timer already punishes it, the logs hold the facts.
* cheating / bug — stored and written as a text file into reports_dir for manual review.
"""
from __future__ import annotations

import logging
import os
import statistics
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_player, player_tag
from ..config import settings
from ..db import get_session
from ..h2h import Match
from ..matchmaking import registry
from ..models import GameLog, Match as MatchRow, Player, Report
from ..schemas import ReportIn

log = logging.getLogger("reports")

router = APIRouter(prefix="/api", tags=["reports"])

NAME_REASONS = ("name", "impersonation")
FILE_REASONS = ("cheating", "bug")


async def name_hidden_by_reports(session: AsyncSession, pid: uuid.UUID, name: str) -> bool:
    """Has this name of this player already reached the report threshold?"""
    n = await session.scalar(
        select(func.count(func.distinct(Report.reporter))).where(
            Report.reported == pid, Report.reason.in_(NAME_REASONS),
            func.lower(Report.reported_name) == name.lower(),
        )
    )
    return (n or 0) >= settings.name_report_threshold


@router.post("/matches/{match_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report(
    match_id: uuid.UUID,
    body: ReportIn,
    player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    done = Response(status_code=status.HTTP_204_NO_CONTENT)
    live = registry.get(match_id)
    row = None
    if live is not None:
        players = list(live.players)
    else:
        row = await session.get(MatchRow, match_id)
        players = [p for p in (row.player_a, row.player_b) if p] if row else []
    if player.id not in players or len(players) != 2:
        return done
    reported_id = next(p for p in players if p != player.id)
    reported = await session.get(Player, reported_id)
    if reported is None:
        return done

    inserted = await session.scalar(
        insert(Report)
        .values(match_id=match_id, reporter=player.id, reported=reported_id,
                reason=body.reason, reported_name=reported.name)
        .on_conflict_do_nothing(constraint="uq_report_match_reporter")
        .returning(Report.id)
    )
    if inserted is None:                 # already reported this match — silently
        await session.commit()
        return done

    if body.reason in NAME_REASONS and reported.name and await name_hidden_by_reports(session, reported_id, reported.name):
        hide_name(reported)
    await session.commit()

    if body.reason in FILE_REASONS:
        try:
            await write_file(session, body.reason, match_id, player, reported, live, row)
        except Exception:
            log.exception("не удалось записать жалобу по матчу %s", match_id)
    return done


def hide_name(p: Player):
    log.info("имя игрока %s скрыто по жалобам", player_tag(p.id))
    p.name = None
    p.name_hidden_at = datetime.now(timezone.utc)
    p.name_set_at = None                 # the cooldown must not block choosing a new name
    for m in registry.matches.values():  # opponents in memory see the placeholder too
        if m.has(p.id):
            m.names[p.id] = (None, player_tag(p.id))


def _who(p: Player) -> str:
    return f"{p.name or '(без имени)'}#{player_tag(p.id)}  id={p.id}"


async def _moves(session: AsyncSession, match_id: uuid.UUID, pid: uuid.UUID, live: Optional[Match]):
    """The reported player's shots, think times and auto-moves in this match."""
    if live is not None and pid in live.shots:
        return live.shots[pid], live.think_ms.get(pid, []), live.auto_moves.get(pid, [])
    gl = await session.scalar(select(GameLog).where(GameLog.match_id == match_id, GameLog.attacker_player == pid))
    if gl is None:
        return None
    return list(gl.shots), list(gl.think_ms or []), list((gl.client_info or {}).get("auto_moves", []))


async def write_file(session: AsyncSession, reason: str, match_id: uuid.UUID, reporter: Player,
                     reported: Player, live: Optional[Match], row: Optional[MatchRow]):
    now = datetime.now(timezone.utc)
    kind = live.kind if live else row.kind if row else "?"
    phase = live.status if live else row.status if row else "?"
    end_reason = (live.end_reason if live else row.end_reason if row else None) or "—"
    title = {"cheating": "Подозрение на читерство", "bug": "Что-то сломалось в игре"}[reason]
    lines: List[str] = [
        f"{title}",
        f"время:        {now:%Y-%m-%d %H:%M:%S} UTC",
        f"матч:         {match_id}  ({kind}, фаза {phase}, итог {end_reason})",
        f"пожаловался:  {_who(reporter)}",
        f"на кого:      {_who(reported)}",
    ]
    if reason == "cheating":
        total, distinct = (await session.execute(
            select(func.count(), func.count(func.distinct(Report.reporter)))
            .where(Report.reported == reported.id, Report.reason == "cheating")
        )).one()
        lines.append(f"всего жалоб на читерство на этого игрока: {total} (от {distinct} разных игроков)")
    moves = await _moves(session, match_id, reported.id, live)
    if moves is not None:
        shots, think, auto = moves
        lines.append(f"выстрелов у него в матче: {len(shots)}, из них автоходов: {len(auto)}")
        if think:
            lines.append(f"время на ход, мс: медиана {int(statistics.median(think))}, минимум {min(think)}")
    lines += [
        "",
        "проверить:",
        f"  cd web/server && python -m scripts.export_logs --out m.jsonl --all --match {match_id}",
        "  cd model && python -m battleship.analyze --logs ../web/server/m.jsonl --ckpt battleship/net.pt",
        "(логи матча появляются в БД, когда матч закончен)",
    ]
    folder = Path(settings.reports_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y%m%d-%H%M%S}_{reason}_{match_id.hex[:8]}_{player_tag(reporter.id)}.txt"
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)

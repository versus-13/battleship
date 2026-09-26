from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_player, hash_secret, new_secret, player_tag
from ..config import settings
from ..db import get_session
from ..models import NameReject, Player
from ..moderation import clean_name, moderator
from ..schemas import NameIn, NameOut, PlayerCreated, PlayerOut, Stats
from .reports import name_hidden_by_reports
from .stats import player_stats

router = APIRouter(prefix="/api/players", tags=["players"])


@router.post("", response_model=PlayerCreated, status_code=status.HTTP_201_CREATED)
async def create_player(session: AsyncSession = Depends(get_session)):
    """A new identity: the server issues the id and secret, the client keeps them in localStorage."""
    secret = new_secret()
    player = Player(secret_hash=hash_secret(secret))
    session.add(player)
    await session.commit()
    return PlayerCreated(player_id=player.id, secret=secret)


@router.get("/me", response_model=PlayerOut)
async def me(player: Player = Depends(get_current_player), session: AsyncSession = Depends(get_session)):
    return PlayerOut(
        player_id=player.id, name=player.name, tag=player_tag(player.id),
        created_at=player.created_at, stats=await player_stats(session, player.id),
        name_hidden=player.name is None and player.name_hidden_at is not None,
    )


@router.put("/me/name", response_model=NameOut)
async def set_name(
    body: NameIn,
    player: Player = Depends(get_current_player),
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    if player.name_set_at and now - player.name_set_at < timedelta(seconds=settings.name_change_cooldown_s):
        raise HTTPException(422, {"code": "rate_limited"})
    name = clean_name(body.name)
    verdict = moderator.check(name)
    if not verdict.ok:
        session.add(NameReject(reason=verdict.code))
        await session.commit()
        raise HTTPException(422, {"code": verdict.code})
    if await name_hidden_by_reports(session, player.id, name):
        raise HTTPException(422, {"code": "name_hidden"})
    player.name = name
    player.name_hidden_at = None
    player.name_set_at = now
    await session.commit()
    return NameOut(name=name, tag=player_tag(player.id))


@router.delete("/me/name", status_code=status.HTTP_204_NO_CONTENT)
async def clear_name(player: Player = Depends(get_current_player), session: AsyncSession = Depends(get_session)):
    player.name = None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(player_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return PlayerOut(player_id=player.id, name=player.name, tag=player_tag(player.id),
                     stats=await player_stats(session, player.id))


@router.get("/{player_id}/stats", response_model=Stats)
async def get_stats(player_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    if await session.get(Player, player_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return await player_stats(session, player_id)

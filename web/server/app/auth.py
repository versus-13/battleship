from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import Player


def hash_secret(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def player_tag(pid: uuid.UUID) -> str:
    return pid.hex[:4]


async def player_by_secret(session: AsyncSession, secret: str) -> Player | None:
    return await session.scalar(select(Player).where(Player.secret_hash == hash_secret(secret)))


async def get_current_player(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Player:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "нужен Bearer-токен")
    player = await player_by_secret(session, authorization[7:].strip())
    if player is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "токен не найден")
    player.last_seen = datetime.now(timezone.utc)
    await session.commit()
    return player

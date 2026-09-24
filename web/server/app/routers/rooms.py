from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_player, player_tag
from ..db import get_session
from ..matchmaking import registry
from ..models import Player
from ..schemas import QueueOut, RoomCreated, RoomInfo, RoomJoined

router = APIRouter(prefix="/api", tags=["rooms"])


def ws_url(match_id: uuid.UUID) -> str:
    return f"/ws/matches/{match_id}"


@router.post("/rooms", response_model=RoomCreated, status_code=status.HTTP_201_CREATED)
async def create_room(player: Player = Depends(get_current_player)):
    current = registry.active_for(player.id)
    if current is not None and current.kind == "room" and current.status == "waiting":
        return RoomCreated(match_id=current.id, code=current.code, ws_url=ws_url(current.id))
    if current is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "already_in_match", "match_id": str(current.id)})
    m = registry.create_room(player.id, player.name, player_tag(player.id))
    return RoomCreated(match_id=m.id, code=m.code, ws_url=ws_url(m.id))


@router.get("/rooms/{code}", response_model=RoomInfo)
async def room_info(code: str, session: AsyncSession = Depends(get_session)):
    mid = registry.by_code.get(code.upper())
    m = registry.get(mid) if mid else None
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    host = m.players[0]
    name, tag = m.names.get(host, (None, player_tag(host)))
    return RoomInfo(match_id=m.id, code=m.code, status=m.status, host_name=name, host_tag=tag)


@router.post("/rooms/{code}/join", response_model=RoomJoined)
async def join_room(code: str, player: Player = Depends(get_current_player)):
    current = registry.active_for(player.id)
    if current is not None and current.code == code.upper():
        return RoomJoined(match_id=current.id, ws_url=ws_url(current.id))
    if current is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "already_in_match", "match_id": str(current.id)})
    m = registry.join_room(code, player.id, player.name, player_tag(player.id))
    if m is None:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "room_unavailable"})
    await m.announce_join(player.id)
    return RoomJoined(match_id=m.id, ws_url=ws_url(m.id))


@router.post("/queue", response_model=QueueOut)
async def queue(player: Player = Depends(get_current_player)):
    m = registry.enqueue(player.id, player.name, player_tag(player.id))
    if m is None:
        return QueueOut(status="queued")
    return QueueOut(status="matched", match_id=m.id, ws_url=ws_url(m.id))


@router.delete("/queue", status_code=status.HTTP_204_NO_CONTENT)
async def leave_queue(player: Player = Depends(get_current_player)):
    registry.leave_queue(player.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/matches/current")
async def current_match(player: Player = Depends(get_current_player)):
    m = registry.active_for(player.id)
    if m is None:
        return {"match_id": None}
    return {"match_id": str(m.id), "ws_url": ws_url(m.id), "phase": m.status, "code": m.code}


@router.get("/matches/{match_id}")
async def match_state(match_id: uuid.UUID, player: Player = Depends(get_current_player)):
    m = registry.get(match_id)
    if m is None or not m.has(player.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return m.snapshot(player.id)



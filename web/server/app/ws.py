from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .auth import player_by_secret, player_tag
from .db import SessionLocal
from .matchmaking import registry

router = APIRouter()

HELLO_TIMEOUT_S = 10


async def _error(ws: WebSocket, code: str, msg: str = ""):
    try:
        await ws.send_json({"t": "error", "code": code, "msg": msg})
    except Exception:
        pass


@router.websocket("/ws/matches/{match_id}")
async def match_socket(ws: WebSocket, match_id: uuid.UUID):
    await ws.accept()
    match = registry.get(match_id)
    if match is None:
        await _error(ws, "no_match")
        await ws.close(code=4004)
        return
    try:
        hello = await asyncio.wait_for(ws.receive_json(), HELLO_TIMEOUT_S)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        await ws.close(code=4001)
        return
    if not isinstance(hello, dict) or hello.get("t") != "hello" or not isinstance(hello.get("token"), str):
        await _error(ws, "hello_expected")
        await ws.close(code=4001)
        return
    async with SessionLocal() as session:
        player = await player_by_secret(session, hello["token"])
    if player is None:
        await _error(ws, "unauthorized")
        await ws.close(code=4003)
        return
    if not match.has(player.id):
        await _error(ws, "not_in_match")
        await ws.close(code=4003)
        return

    pid = player.id
    await match.connect(pid, ws, player.name, player_tag(pid))
    try:
        while True:
            try:
                msg = await ws.receive_json()
            except ValueError:
                await _error(ws, "bad_json")
                continue
            if not isinstance(msg, dict):
                await _error(ws, "bad_message")
                continue
            t = msg.get("t")
            if t == "ping":
                await ws.send_json({"t": "pong"})
            elif t == "place":
                err = await match.place(pid, msg.get("ships"), msg.get("mode"))
                if err:
                    await _error(ws, err)
            elif t == "shoot":
                err = await match.shoot(pid, msg.get("cell"))
                if err:
                    await _error(ws, err)
            elif t == "leave":
                await match.leave(pid)
            elif t == "state":
                await ws.send_json(match.snapshot(pid))
            else:
                await _error(ws, "unknown_type", str(t))
    except WebSocketDisconnect:
        pass
    finally:
        await match.disconnect(pid, ws)

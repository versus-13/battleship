"""
A human-vs-human match. The server is the sole referee: it holds both boards,
validates shots, tracks whose turn it is and writes the logs to the DB at the end.
Lives in the memory of a single process (uvicorn --workers 1).
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import WebSocket

from .config import settings
from .models import GameLog, Match as MatchRow
from .rules import EXTRA_TURN_ON_HIT, Board, IllegalShot, PlacementError, validate_placement

log = logging.getLogger("h2h")

WAITING, PLACING, PLAYING, FINISHED, ABANDONED = "waiting", "placing", "playing", "finished", "abandoned"


class Match:
    def __init__(self, kind: str, host: uuid.UUID, code: Optional[str],
                 on_finish: Callable[["Match"], Awaitable[None]]):
        self.id = uuid.uuid4()
        self.kind = kind
        self.code = code
        self.players: List[uuid.UUID] = [host]
        self.names: Dict[uuid.UUID, tuple[Optional[str], str]] = {}
        self.status = WAITING
        self.boards: Dict[uuid.UUID, Board] = {}        # the player's board (the opponent shoots at it)
        self.shots: Dict[uuid.UUID, List[int]] = {}     # the player's shots
        self.think_ms: Dict[uuid.UUID, List[int]] = {}  # time per shot
        self.placement_mode: Dict[uuid.UUID, str] = {}  # random | manual
        self._turn_since: float = 0.0                    # when the current turn became available
        self.sockets: Dict[uuid.UUID, Optional[WebSocket]] = {host: None}
        self.turn: Optional[uuid.UUID] = None
        self.winner: Optional[uuid.UUID] = None
        self.end_reason: Optional[str] = None
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.deadline_ts: Optional[float] = None
        self._timer: Optional[asyncio.Task] = None
        self._dc_timers: Dict[uuid.UUID, asyncio.Task] = {}
        self._on_finish = on_finish
        self._arm(settings.room_wait_s, self._expire_waiting)

    # ---- helpers ----
    @property
    def active(self) -> bool:
        return self.status in (WAITING, PLACING, PLAYING)

    def opponent(self, pid: uuid.UUID) -> Optional[uuid.UUID]:
        for p in self.players:
            if p != pid:
                return p
        return None

    def has(self, pid: uuid.UUID) -> bool:
        return pid in self.players

    def _arm(self, seconds: float, cb: Callable[[], Awaitable[None]]):
        self._disarm()
        self.deadline_ts = time.time() + seconds

        async def fire():
            await asyncio.sleep(seconds)
            try:
                await cb()
            except Exception:
                log.exception("таймер матча %s", self.id)

        self._timer = asyncio.create_task(fire())

    @staticmethod
    def _cancel(task: Optional[asyncio.Task]):
        # a timer may finish the match itself — never cancel the current task
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _disarm(self):
        self._cancel(self._timer)
        self._timer = None
        self.deadline_ts = None

    def _disarm_all(self):
        self._disarm()
        for t in self._dc_timers.values():
            self._cancel(t)
        self._dc_timers.clear()

    async def _send(self, pid: uuid.UUID, msg: dict):
        ws = self.sockets.get(pid)
        if ws is None:
            return
        try:
            await ws.send_json(msg)
        except Exception:
            pass

    async def _broadcast(self, msg: dict):
        for p in self.players:
            await self._send(p, msg)

    # ---- snapshot ----
    def snapshot(self, pid: uuid.UUID) -> dict:
        opp = self.opponent(pid)
        mine = self.boards.get(pid)
        theirs = self.boards.get(opp) if opp else None
        you: Dict[str, Any] = {"placed": mine is not None}
        if mine is not None:
            you.update(mine.owner_view())
        enemy: Dict[str, Any] = {"placed": theirs is not None, "cells": {}, "alive": None}
        if theirs is not None:
            enemy["cells"] = {str(k): v for k, v in theirs.enemy_view().items()}
            enemy["alive"] = {str(k): v for k, v in theirs.alive.items()}
        opponent = None
        if opp is not None:
            name, tag = self.names.get(opp, (None, opp.hex[:4]))
            opponent = {"name": name, "tag": tag, "connected": self.sockets.get(opp) is not None,
                        "placed": theirs is not None}
        snap = {
            "t": "state",
            "match_id": str(self.id),
            "code": self.code,
            "phase": self.status,
            "you": you,
            "enemy": enemy,
            "your_turn": self.status == PLAYING and self.turn == pid,
            "opponent": opponent,
            "deadline_ts": self.deadline_ts,
            "winner": str(self.winner) if self.winner else None,
            "you_won": (self.winner == pid) if self.winner else None,
            "end_reason": self.end_reason,
            "enemy_ships": theirs.ships if (theirs is not None and not self.active) else None,
        }
        return snap

    # ---- events ----
    def join(self, pid: uuid.UUID, name: Optional[str], tag: str) -> bool:
        """The second player joins. False if not allowed."""
        self.names[pid] = (name, tag)
        if pid in self.players:
            return True
        if len(self.players) >= 2 or self.status != WAITING:
            return False
        self.players.append(pid)
        self.sockets[pid] = None
        self.status = PLACING
        self._arm(settings.placing_s, self._expire_placing)
        return True

    async def announce_join(self, pid: uuid.UUID):
        opp = self.opponent(pid)
        if opp is not None:
            name, tag = self.names.get(pid, (None, pid.hex[:4]))
            await self._send(opp, {"t": "opponent_joined", "name": name, "tag": tag})
            await self._send(opp, self.snapshot(opp))

    async def connect(self, pid: uuid.UUID, ws: WebSocket, name: Optional[str], tag: str):
        self.names[pid] = (name, tag)
        old = self.sockets.get(pid)
        was_disconnected = old is None
        self.sockets[pid] = ws
        if old is not None and old is not ws:
            try:
                await old.close(code=4000, reason="replaced")
            except Exception:
                pass
        self._cancel(self._dc_timers.pop(pid, None))
        if self.status == WAITING and was_disconnected:
            self._arm(settings.room_wait_s, self._expire_waiting)
        await self._send(pid, self.snapshot(pid))
        opp = self.opponent(pid)
        if opp is not None and was_disconnected:
            await self._send(opp, {"t": "opponent_back"})
            await self._send(opp, self.snapshot(opp))

    async def disconnect(self, pid: uuid.UUID, ws: WebSocket):
        if self.sockets.get(pid) is not ws:
            return
        self.sockets[pid] = None
        if not self.active:
            return
        if self.status == WAITING:
            self._arm(settings.disconnect_grace_s, self._expire_waiting)
            return

        async def fire():
            await asyncio.sleep(settings.disconnect_grace_s)
            self._dc_timers.pop(pid, None)
            if self.sockets.get(pid) is None:
                await self._forfeit(pid, "disconnect")

        self._cancel(self._dc_timers.pop(pid, None))
        self._dc_timers[pid] = asyncio.create_task(fire())
        opp = self.opponent(pid)
        if opp is not None:
            await self._send(opp, {"t": "opponent_left", "grace_s": settings.disconnect_grace_s})

    async def place(self, pid: uuid.UUID, ships, mode: Any = None) -> Optional[str]:
        if self.status != PLACING:
            return "wrong_phase"
        if pid in self.boards:
            return "already_placed"
        try:
            canon = validate_placement(ships)
        except (PlacementError, TypeError, ValueError):
            return "bad_placement"
        self.boards[pid] = Board(canon)
        self.shots[pid] = []
        self.think_ms[pid] = []
        self.placement_mode[pid] = mode if mode in ("random", "manual") else "unknown"
        await self._send(pid, {"t": "placed"})
        opp = self.opponent(pid)
        if opp is not None:
            await self._send(opp, {"t": "opponent_ready"})
        if len(self.boards) == 2:
            await self._start()
        return None

    async def _start(self):
        self.status = PLAYING
        self.started_at = datetime.now(timezone.utc)
        self.turn = random.choice(self.players)
        self._turn_since = time.time()
        self._arm(settings.move_s, self._expire_move)
        for p in self.players:
            await self._send(p, {"t": "start", "your_turn": self.turn == p, "deadline_ts": self.deadline_ts})

    async def shoot(self, pid: uuid.UUID, cell) -> Optional[str]:
        if self.status != PLAYING:
            return "wrong_phase"
        if self.turn != pid:
            return "not_your_turn"
        opp = self.opponent(pid)
        try:
            outcome = self.boards[opp].shoot(int(cell))
        except (IllegalShot, TypeError, ValueError):
            return "illegal_shot"
        self.shots[pid].append(int(cell))
        now = time.time()
        self.think_ms[pid].append(int((now - self._turn_since) * 1000))
        self._turn_since = now
        board = self.boards[opp]
        if board.done:
            payload = {"cell": cell, "result": outcome.result, "sunk_cells": outcome.sunk_cells,
                       "revealed": outcome.revealed, "your_turn": False, "alive": board.alive}
            await self._send(pid, {"t": "shot_result", **payload})
            await self._send(opp, {"t": "opponent_shot", **payload})
            await self._finish(pid, "fleet_sunk")
            return None
        if not (EXTRA_TURN_ON_HIT and outcome.result > 0):
            self.turn = opp
        self._arm(settings.move_s, self._expire_move)
        base = {"cell": cell, "result": outcome.result, "sunk_cells": outcome.sunk_cells,
                "revealed": outcome.revealed, "alive": board.alive, "deadline_ts": self.deadline_ts}
        await self._send(pid, {"t": "shot_result", **base, "your_turn": self.turn == pid})
        await self._send(opp, {"t": "opponent_shot", **base, "your_turn": self.turn == opp})
        return None

    async def leave(self, pid: uuid.UUID):
        if not self.active:
            return
        if self.status == WAITING or self.opponent(pid) is None:
            await self._abandon("abandoned")
            return
        await self._forfeit(pid, "forfeit")

    # ---- finishing ----
    async def _expire_waiting(self):
        if self.status == WAITING:
            await self._abandon("abandoned")

    async def _expire_placing(self):
        if self.status == PLACING:
            await self._abandon("abandoned")

    async def _expire_move(self):
        if self.status == PLAYING and self.turn is not None:
            await self._forfeit(self.turn, "move_timeout")

    async def _forfeit(self, loser: uuid.UUID, reason: str):
        if not self.active:
            return
        winner = self.opponent(loser)
        if winner is None or self.status == WAITING:
            await self._abandon("abandoned")
            return
        await self._finish(winner, reason)

    async def _abandon(self, reason: str):
        self._disarm_all()
        self.status = ABANDONED
        self.end_reason = reason
        self.finished_at = datetime.now(timezone.utc)
        await self._broadcast({"t": "game_over", "winner": None, "you_won": None, "reason": reason, "enemy_ships": None})
        await self._on_finish(self)

    async def _finish(self, winner: uuid.UUID, reason: str):
        self._disarm_all()
        self.status = FINISHED
        self.winner = winner
        self.end_reason = reason
        self.finished_at = datetime.now(timezone.utc)
        for p in self.players:
            opp = self.opponent(p)
            theirs = self.boards.get(opp) if opp else None
            await self._send(p, {
                "t": "game_over", "winner": str(winner), "you_won": p == winner, "reason": reason,
                "enemy_ships": theirs.ships if theirs else None,
            })
        await self._on_finish(self)

    # ---- DB rows ----
    def db_rows(self) -> tuple[MatchRow, List[GameLog]]:
        row = MatchRow(
            id=self.id, code=self.code, kind=self.kind,
            player_a=self.players[0], player_b=self.players[1] if len(self.players) > 1 else None,
            status=self.status, winner=self.winner, end_reason=self.end_reason,
            created_at=self.created_at, started_at=self.started_at, finished_at=self.finished_at,
        )
        logs: List[GameLog] = []
        if self.status == FINISHED and len(self.boards) == 2:
            for p in self.players:
                opp = self.opponent(p)
                board = self.boards[opp]
                logs.append(GameLog(
                    client_game_id=uuid.uuid5(self.id, str(p)), mode="h2h", match_id=self.id,
                    attacker_kind="player", attacker_player=p, attacker_label="player",
                    defender_player=opp, ships=board.ships, shots=self.shots[p],
                    n_shots=len(self.shots[p]), fleet_cleared=board.done,
                    won=(p == self.winner), client="server",
                    think_ms=self.think_ms[p], started_at=self.started_at,
                    client_info={"placement": self.placement_mode.get(p, "unknown")},
                ))
        return row, logs

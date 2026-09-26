"""
A human-vs-human match. The server is the sole referee: it holds both boards,
validates shots, tracks whose turn it is and writes the logs to the DB at the end.
Lives in the memory of a single process (uvicorn --workers 1).

Time rules (all clocks are here, the client only displays them):
* move timer (move_s): when it runs out, a random shot is made for the player —
  no forfeit, the idle player simply plays worse. idle_moves_limit auto-moves in a
  row end the match: the player is gone.
* reconnect budget (reconnect_budget_s) per player per match, spent while offline.
  While it lasts, the offline player's move timer waits. Once it is spent, auto-moves
  go on as usual, and disconnect_after_budget_s more offline ends the match.
* a match left early (resigned / idle / disconnect) is a loss for the leaver; the
  winner may finish clearing the static board ("solo") so their shots-to-clear counts.
  The logs are written when the solo ends.

Restart: to_state() / from_state() carry an unfinished match through a server restart
(matchmaking checkpoints it into live_matches). Clocks are stored as remaining time, not
deadlines, so the downtime costs nobody anything; for restart_grace_s after the restore
offline time is free too — the clients reconnect as after a network glitch.
A new field of Match must be added to to_state/from_state (bump STATE_VERSION if the old
state cannot be read any more).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import WebSocket

from .config import settings
from .models import GameLog, Match as MatchRow
from .rules import EXTRA_TURN_ON_HIT, N, Board, IllegalShot, PlacementError, validate_placement

log = logging.getLogger("h2h")

WAITING, PLACING, PLAYING, FINISHED, ABANDONED = "waiting", "placing", "playing", "finished", "abandoned"
# end reasons: fleet_sunk | resigned | idle | disconnect | abandoned
LEFT_EARLY = ("resigned", "idle", "disconnect")
STATE_VERSION = 1


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s) if s else None


class Match:
    def __init__(self, kind: str, host: uuid.UUID, code: Optional[str],
                 on_finish: Callable[["Match"], Awaitable[None]]):
        self.id = uuid.uuid4()
        self.kind = kind
        self.code = code
        self.players: List[uuid.UUID] = []
        self.names: Dict[uuid.UUID, tuple[Optional[str], str]] = {}
        self.status = WAITING
        self.boards: Dict[uuid.UUID, Board] = {}        # the player's board (the opponent shoots at it)
        self.shots: Dict[uuid.UUID, List[int]] = {}     # the player's shots
        self.think_ms: Dict[uuid.UUID, List[int]] = {}  # time per shot
        self.placement_mode: Dict[uuid.UUID, str] = {}  # random | manual
        self.auto_moves: Dict[uuid.UUID, List[int]] = {}  # indices into shots made by the move timer
        self.auto_streak: Dict[uuid.UUID, int] = {}
        self.budget_left: Dict[uuid.UUID, float] = {}   # reconnect budget, s (as of the last reconnect)
        self.offline_since: Dict[uuid.UUID, float] = {}  # only while the offline clock runs
        self._turn_since: float = 0.0                    # when the current turn became available
        self._move_left: Optional[float] = None          # the move timer is paused with this much left
        self.sockets: Dict[uuid.UUID, Optional[WebSocket]] = {}
        self.turn: Optional[uuid.UUID] = None
        self.winner: Optional[uuid.UUID] = None
        self.end_reason: Optional[str] = None
        self.solo: Optional[uuid.UUID] = None            # the winner finishing the board
        self.created_at = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.deadline_ts: Optional[float] = None
        self._timer: Optional[asyncio.Task] = None
        self._dc_timers: Dict[uuid.UUID, asyncio.Task] = {}
        self._saved = False
        self.restored_until: Optional[float] = None       # the restart grace window
        self._grace: Optional[asyncio.Task] = None
        self.persisted_hash: Optional[str] = None         # content last written to live_matches
        self._on_finish = on_finish
        self._add_player(host)
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

    def _add_player(self, pid: uuid.UUID):
        self.players.append(pid)
        self.sockets[pid] = None
        self.auto_streak[pid] = 0
        self.auto_moves[pid] = []
        self.budget_left[pid] = float(settings.reconnect_budget_s)

    def _later(self, seconds: float, cb: Callable[[], Awaitable[None]]) -> asyncio.Task:
        async def fire():
            await asyncio.sleep(seconds)
            try:
                await cb()
            except Exception:
                log.exception("таймер матча %s", self.id)

        return asyncio.create_task(fire())

    def _arm(self, seconds: float, cb: Callable[[], Awaitable[None]]):
        self._disarm()
        self.deadline_ts = time.time() + seconds
        self._timer = self._later(seconds, cb)

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
        self._move_left = None
        self._cancel(self._grace)
        self._grace = None
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

    # ---- reconnect budget ----
    def _budget_now(self, pid: uuid.UUID) -> float:
        left = self.budget_left.get(pid, 0.0)
        since = self.offline_since.get(pid)
        if since is not None:
            left -= time.time() - since
        return max(0.0, left)

    def _reconnecting(self, pid: uuid.UUID) -> bool:
        """Offline with budget left (or right after a restart): the player's move timer waits."""
        if self.sockets.get(pid) is not None:
            return False
        if pid in self.offline_since:
            return self._budget_now(pid) > 0
        return self.restored_until is not None and time.time() < self.restored_until

    def _reconnect_deadline(self, pid: uuid.UUID) -> Optional[float]:
        if not self.active or not self._reconnecting(pid):
            return None
        if pid in self.offline_since:
            return time.time() + self._budget_now(pid)
        return self.restored_until + self.budget_left[pid]       # the grace window, then the budget

    def _start_offline_clock(self, pid: uuid.UUID):
        self.offline_since[pid] = time.time()
        self._cancel(self._dc_timers.pop(pid, None))
        if self.budget_left[pid] > 0:
            self._dc_timers[pid] = self._later(self.budget_left[pid], lambda: self._budget_spent(pid))
        else:
            self._dc_timers[pid] = self._later(settings.disconnect_after_budget_s, lambda: self._gone(pid))

    async def _budget_spent(self, pid: uuid.UUID):
        self._dc_timers.pop(pid, None)
        if not self.active or self.sockets.get(pid) is not None:
            return
        self.budget_left[pid] = 0.0
        self.offline_since[pid] = time.time()
        if self.status == PLACING:
            await self._forfeit(pid, "disconnect")
            return
        self._dc_timers[pid] = self._later(settings.disconnect_after_budget_s, lambda: self._gone(pid))
        if self.status == PLAYING and self.turn == pid and self._move_left is not None:
            self._arm_move(self._move_left)      # auto-moves from now on
        opp = self.opponent(pid)
        if opp is not None:
            await self._send(opp, self.snapshot(opp))

    async def _gone(self, pid: uuid.UUID):
        self._dc_timers.pop(pid, None)
        if self.active and self.sockets.get(pid) is None:
            await self._forfeit(pid, "disconnect")

    # ---- move timer ----
    def _arm_move(self, seconds: Optional[float] = None):
        seconds = settings.move_s if seconds is None else seconds
        if self.turn is not None and self._reconnecting(self.turn):
            self._disarm()
            self._move_left = seconds
            return
        self._move_left = None
        self._arm(seconds, self._expire_move)

    # ---- snapshot ----
    def snapshot(self, pid: uuid.UUID) -> dict:
        opp = self.opponent(pid)
        mine = self.boards.get(pid)
        theirs = self.boards.get(opp) if opp else None
        you: Dict[str, Any] = {"placed": mine is not None, "reconnect_left_s": round(self._budget_now(pid), 1)}
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
                        "placed": theirs is not None,
                        # the opponent is reconnecting until then; None — online or the budget is spent
                        "reconnect_deadline_ts": self._reconnect_deadline(opp)}
        solo = self.solo == pid
        return {
            "t": "state",
            "match_id": str(self.id),
            "code": self.code,
            "phase": self.status,
            "you": you,
            "enemy": enemy,
            "your_turn": (self.status == PLAYING and self.turn == pid) or solo,
            "opponent": opponent,
            "deadline_ts": self.deadline_ts if self.active else None,
            "move_s": settings.move_s,
            "auto_streak": self.auto_streak.get(pid, 0),
            "idle_limit": settings.idle_moves_limit,
            "winner": str(self.winner) if self.winner else None,
            "you_won": (self.winner == pid) if self.winner else None,
            "end_reason": self.end_reason,
            "solo": solo,
            "enemy_ships": theirs.ships if (theirs is not None and not self.active and not solo) else None,
        }

    # ---- events ----
    def join(self, pid: uuid.UUID, name: Optional[str], tag: str) -> bool:
        """The second player joins. False if not allowed."""
        self.names[pid] = (name, tag)
        if pid in self.players:
            return True
        if len(self.players) >= 2 or self.status != WAITING:
            return False
        self._add_player(pid)
        self.status = PLACING
        self._arm(settings.placing_s, self._expire_placing)
        # from here on offline time is spent from the budget — including never connecting at all
        for p in self.players:
            if self.sockets[p] is None:
                self._start_offline_clock(p)
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
        if was_disconnected:
            self.budget_left[pid] = self._budget_now(pid)
        self.sockets[pid] = ws
        if old is not None and old is not ws:
            try:
                await old.close(code=4000, reason="replaced")
            except Exception:
                pass
        self._cancel(self._dc_timers.pop(pid, None))
        since = self.offline_since.pop(pid, None)
        if self.status == WAITING and was_disconnected:
            self._arm(settings.room_wait_s, self._expire_waiting)
        if self.status == PLAYING and self.turn == pid and self._move_left is not None:
            # the paused turn resumes; the time offline is not the player's think time
            if since is not None:
                self._turn_since += time.time() - since
            self._arm_move(max(self._move_left, min(10.0, settings.move_s)))
        await self._send(pid, self.snapshot(pid))
        opp = self.opponent(pid)
        if opp is not None and was_disconnected and self.active:
            await self._send(opp, {"t": "opponent_back"})
            await self._send(opp, self.snapshot(opp))

    async def disconnect(self, pid: uuid.UUID, ws: WebSocket):
        if self.sockets.get(pid) is not ws:
            return
        self.sockets[pid] = None
        if not self.active:
            return                    # a solo is bounded by its idle timer
        if self.status == WAITING:
            self._arm(settings.disconnect_grace_s, self._expire_waiting)
            return
        self._start_offline_clock(pid)
        if self.status == PLAYING and self.turn == pid and self.deadline_ts is not None:
            self._arm_move(max(0.0, self.deadline_ts - time.time()))   # pauses while the budget lasts
        opp = self.opponent(pid)
        if opp is not None:
            left = self._budget_now(pid)
            await self._send(opp, {"t": "opponent_left", "grace_s": round(left),
                                   "reconnect_deadline_ts": time.time() + left if left > 0 else None})
            await self._send(opp, self.snapshot(opp))

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
        self._arm_move()
        for p in self.players:
            await self._send(p, {"t": "start", "your_turn": self.turn == p, "deadline_ts": self.deadline_ts})

    async def shoot(self, pid: uuid.UUID, cell) -> Optional[str]:
        if self.status == FINISHED and self.solo == pid:
            return await self._solo_shot(pid, cell)
        if self.status != PLAYING:
            return "wrong_phase"
        if self.turn != pid:
            return "not_your_turn"
        try:
            cell = int(cell)
        except (TypeError, ValueError):
            return "illegal_shot"
        return await self._shot(pid, cell, auto=False)

    async def _shot(self, pid: uuid.UUID, cell: int, auto: bool) -> Optional[str]:
        opp = self.opponent(pid)
        board = self.boards[opp]
        try:
            outcome = board.shoot(cell)
        except IllegalShot:
            return "illegal_shot"
        self.shots[pid].append(cell)
        now = time.time()
        self.think_ms[pid].append(int((now - self._turn_since) * 1000))
        self._turn_since = now
        if auto:
            self.auto_moves[pid].append(len(self.shots[pid]) - 1)
            self.auto_streak[pid] += 1
        else:
            self.auto_streak[pid] = 0
        payload = {"cell": cell, "result": outcome.result, "sunk_cells": outcome.sunk_cells,
                   "revealed": outcome.revealed, "alive": board.alive,
                   "auto": auto, "auto_streak": self.auto_streak[pid]}
        if board.done:
            payload.update(your_turn=False, deadline_ts=None)
            await self._send(pid, {"t": "shot_result", **payload})
            await self._send(opp, {"t": "opponent_shot", **payload})
            await self._finish(pid, "fleet_sunk")
            return None
        idle = auto and self.auto_streak[pid] >= settings.idle_moves_limit
        if not (EXTRA_TURN_ON_HIT and outcome.result > 0):
            self.turn = opp
        if idle:
            self._disarm()
        else:
            self._arm_move()
        payload["deadline_ts"] = self.deadline_ts
        await self._send(pid, {"t": "shot_result", **payload, "your_turn": self.turn == pid and not idle})
        await self._send(opp, {"t": "opponent_shot", **payload, "your_turn": self.turn == opp and not idle})
        if idle:
            await self._forfeit(pid, "idle")
        return None

    async def _solo_shot(self, pid: uuid.UUID, cell) -> Optional[str]:
        board = self.boards[self.opponent(pid)]
        try:
            outcome = board.shoot(int(cell))
        except (IllegalShot, TypeError, ValueError):
            return "illegal_shot"
        self.shots[pid].append(int(cell))
        now = time.time()
        self.think_ms[pid].append(int((now - self._turn_since) * 1000))
        self._turn_since = now
        await self._send(pid, {"t": "shot_result", "cell": int(cell), "result": outcome.result,
                               "sunk_cells": outcome.sunk_cells, "revealed": outcome.revealed,
                               "alive": board.alive, "auto": False, "auto_streak": 0,
                               "your_turn": not board.done, "deadline_ts": None})
        if board.done:
            await self._end_solo()
        else:
            self._cancel(self._timer)
            self._timer = self._later(settings.solo_idle_s, self._end_solo)
        return None

    async def leave(self, pid: uuid.UUID):
        if self.status == FINISHED and self.solo == pid:
            await self._end_solo()
            return
        if not self.active:
            return
        if self.status == WAITING or self.opponent(pid) is None:
            await self._abandon("abandoned")
            return
        await self._forfeit(pid, "resigned")

    # ---- finishing ----
    async def _expire_waiting(self):
        if self.status == WAITING:
            await self._abandon("abandoned")

    async def _expire_placing(self):
        if self.status == PLACING:
            await self._abandon("abandoned")

    async def _expire_move(self):
        """Time is up: a random shot at an unopened cell instead of a forfeit."""
        if self.status != PLAYING or self.turn is None:
            return
        pid = self.turn
        board = self.boards[self.opponent(pid)]
        cell = random.choice([i for i in range(N * N) if not board.known[i]])
        await self._shot(pid, cell, auto=True)

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
        await self._broadcast({"t": "game_over", "winner": None, "you_won": None, "reason": reason,
                               "enemy_ships": None, "solo": False})
        await self._save()

    async def _finish(self, winner: uuid.UUID, reason: str):
        self._disarm_all()
        self.status = FINISHED
        self.winner = winner
        self.end_reason = reason
        self.finished_at = datetime.now(timezone.utc)
        target = self.boards.get(self.opponent(winner))
        if (reason in LEFT_EARLY and self.started_at is not None and target is not None
                and not target.done and self.sockets.get(winner) is not None):
            # the race is decided; the board is static — the winner may clear it for the stats
            self.solo = winner
            self._turn_since = time.time()
            self._timer = self._later(settings.solo_idle_s, self._end_solo)
        for p in self.players:
            await self._send(p, self._game_over(p))
        if self.solo is None:
            await self._save()

    def _game_over(self, p: uuid.UUID) -> dict:
        opp = self.opponent(p)
        theirs = self.boards.get(opp) if opp else None
        solo = self.solo == p
        return {
            "t": "game_over", "winner": str(self.winner), "you_won": p == self.winner, "reason": self.end_reason,
            "enemy_ships": theirs.ships if (theirs is not None and not solo) else None,
            "solo": solo, "n_shots": len(self.shots.get(p, [])),
            "cleared": bool(theirs is not None and theirs.done),
        }

    async def _end_solo(self):
        p = self.solo
        if p is None:
            return
        self.solo = None
        self._disarm()
        await self._send(p, self._game_over(p))
        await self._save()

    async def _save(self):
        if self._saved:
            return
        self._saved = True
        await self._on_finish(self)

    # ---- restart ----
    def to_state(self, clocks: bool = True) -> dict:
        """Everything needed to continue the match in another process (JSON)."""
        now = time.time()
        d: Dict[str, Any] = {
            "v": STATE_VERSION, "id": str(self.id), "kind": self.kind, "code": self.code, "status": self.status,
            "players": [str(p) for p in self.players],
            "names": {str(p): list(v) for p, v in self.names.items()},
            "ships": {str(p): b.ships for p, b in self.boards.items()},
            "shots": {str(p): list(v) for p, v in self.shots.items()},
            "think_ms": {str(p): list(v) for p, v in self.think_ms.items()},
            "placement_mode": {str(p): v for p, v in self.placement_mode.items()},
            "auto_moves": {str(p): list(v) for p, v in self.auto_moves.items()},
            "auto_streak": {str(p): v for p, v in self.auto_streak.items()},
            "turn": str(self.turn) if self.turn else None,
            "winner": str(self.winner) if self.winner else None,
            "end_reason": self.end_reason, "solo": str(self.solo) if self.solo else None,
            "created_at": _iso(self.created_at), "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
        }
        if clocks:
            # remaining time, not deadlines: the downtime must not count
            d["clocks"] = {
                "budget_left": {str(p): round(self._budget_now(p), 3) for p in self.players},
                "timer_left": round(max(0.0, self.deadline_ts - now), 3) if self.deadline_ts else None,
                "move_left": self._move_left,
                "think_elapsed": round(now - self._turn_since, 3) if self._turn_since else 0.0,
            }
        return d

    def content_hash(self) -> str:
        """Changes on moves and phase changes, not with the ticking clocks."""
        return hashlib.sha1(json.dumps(self.to_state(clocks=False), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_state(cls, d: dict, on_finish: Callable[["Match"], Awaitable[None]]) -> "Match":
        if d.get("v") != STATE_VERSION:
            raise ValueError(f"state v{d.get('v')}, ожидается v{STATE_VERSION}")
        players = [uuid.UUID(p) for p in d["players"]]
        m = cls(d["kind"], players[0], d["code"], on_finish)
        m._disarm()                                        # __init__ armed the waiting room
        m.id = uuid.UUID(d["id"])
        for p in players[1:]:
            m._add_player(p)
        U = uuid.UUID
        m.status = d["status"]
        m.names = {U(p): (v[0], v[1]) for p, v in d["names"].items()}
        m.shots = {U(p): list(v) for p, v in d["shots"].items()}
        m.think_ms = {U(p): list(v) for p, v in d["think_ms"].items()}
        m.placement_mode = {U(p): v for p, v in d["placement_mode"].items()}
        m.auto_moves.update({U(p): list(v) for p, v in d["auto_moves"].items()})
        m.auto_streak.update({U(p): int(v) for p, v in d["auto_streak"].items()})
        for p, ships in d["ships"].items():
            board = Board(ships)
            opp = m.opponent(U(p))
            for c in m.shots.get(opp, []) if opp else []:
                board.shoot(c)                            # IllegalShot — a broken state, the caller skips it
            m.boards[U(p)] = board
        m.turn = U(d["turn"]) if d["turn"] else None
        m.winner = U(d["winner"]) if d["winner"] else None
        m.end_reason = d["end_reason"]
        m.solo = U(d["solo"]) if d["solo"] else None
        m.created_at = _dt(d["created_at"]) or m.created_at
        m.started_at, m.finished_at = _dt(d["started_at"]), _dt(d["finished_at"])
        clocks = d.get("clocks") or {}
        m.budget_left.update({U(p): float(v) for p, v in (clocks.get("budget_left") or {}).items()})
        m._move_left = clocks.get("move_left")
        m._turn_since = time.time() - float(clocks.get("think_elapsed") or 0.0)
        m._resume_after_restart(clocks.get("timer_left"))
        return m

    def _resume_after_restart(self, timer_left: Optional[float]):
        """Nobody is connected yet: re-arm the timers from what was left, open the grace window."""
        self.restored_until = time.time() + settings.restart_grace_s
        if self.status == WAITING:
            self._arm(settings.room_wait_s, self._expire_waiting)
        elif self.status == PLACING:
            self._arm(max(timer_left or settings.placing_s, settings.restart_grace_s), self._expire_placing)
        elif self.status == PLAYING:
            # the turn waits: connect() resumes it, or the end of the grace window
            if self._move_left is None:
                self._move_left = timer_left if timer_left is not None else settings.move_s
        elif self.status == FINISHED and self.solo is not None:
            self._timer = self._later(settings.solo_idle_s, self._end_solo)
        if self.active:
            self._grace = self._later(settings.restart_grace_s, self._restart_grace_over)

    async def _restart_grace_over(self):
        self._grace = None
        self.restored_until = None
        if self.status not in (PLACING, PLAYING):
            return
        for p in self.players:
            if self.sockets.get(p) is None and p not in self.offline_since:
                self._start_offline_clock(p)               # the usual reconnect budget from now on
        if self.status == PLAYING and self._move_left is not None:
            self._arm_move(self._move_left)
        for p in self.players:
            await self._send(p, self.snapshot(p))

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
                info: Dict[str, Any] = {"placement": self.placement_mode.get(p, "unknown")}
                if self.auto_moves[p]:
                    info["auto_moves"] = self.auto_moves[p]      # not the player's decisions
                logs.append(GameLog(
                    client_game_id=uuid.uuid5(self.id, str(p)), mode="h2h", match_id=self.id,
                    attacker_kind="player", attacker_player=p, attacker_label="player",
                    defender_player=opp, ships=board.ships, shots=self.shots[p],
                    n_shots=len(self.shots[p]), fleet_cleared=board.done,
                    won=(p == self.winner), client="server",
                    think_ms=self.think_ms[p], started_at=self.started_at,
                    client_info=info,
                ))
        return row, logs

"""
Match registry, room codes and the random queue. All in the memory of one process,
but unfinished matches are mirrored into live_matches (checkpoint_forever, shutdown)
and restored on startup — a server update looks like a network glitch to the players.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from typing import Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from .config import settings
from .db import SessionLocal
from .h2h import Match
from .models import LiveMatch, Match as MatchRow

log = logging.getLogger("matchmaking")


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
FINISHED_TTL_S = 10 * 60


class MatchRegistry:
    def __init__(self):
        self.matches: Dict[uuid.UUID, Match] = {}
        self.by_code: Dict[str, uuid.UUID] = {}
        self.by_player: Dict[uuid.UUID, uuid.UUID] = {}
        self.queue: Dict[uuid.UUID, float] = {}          # player -> when they joined
        self._queue_names: Dict[uuid.UUID, tuple] = {}
        self._finished_at: Dict[uuid.UUID, float] = {}

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if code not in self.by_code:
                return code

    def get(self, match_id: uuid.UUID) -> Optional[Match]:
        return self.matches.get(match_id)

    def active_for(self, pid: uuid.UUID) -> Optional[Match]:
        mid = self.by_player.get(pid)
        if mid is None:
            return None
        m = self.matches.get(mid)
        if m is None or not m.active:
            self.by_player.pop(pid, None)
            return None
        return m

    def _register(self, m: Match):
        self.matches[m.id] = m
        if m.code:
            self.by_code[m.code] = m.id
        for p in m.players:
            self.by_player[p] = m.id

    def create_room(self, host: uuid.UUID, name: Optional[str], tag: str) -> Match:
        self.leave_queue(host)
        m = Match("room", host, self._new_code(), self._on_finish)
        m.names[host] = (name, tag)
        self._register(m)
        return m

    def join_room(self, code: str, pid: uuid.UUID, name: Optional[str], tag: str) -> Optional[Match]:
        mid = self.by_code.get(code.upper())
        m = self.matches.get(mid) if mid else None
        if m is None or not m.join(pid, name, tag):
            return None
        self.leave_queue(pid)
        self.by_player[pid] = m.id
        return m

    def enqueue(self, pid: uuid.UUID, name: Optional[str], tag: str) -> Optional[Match]:
        """Join the queue. Returns a match if a pair was formed (now or earlier)."""
        current = self.active_for(pid)
        if current is not None:
            return current
        now = time.time()
        for other, since in list(self.queue.items()):
            if now - since > settings.queue_ttl_s:
                self.queue.pop(other, None)
        for other in list(self.queue):
            if other == pid:
                continue
            self.queue.pop(other, None)
            self.queue.pop(pid, None)
            other_name = self._queue_names.pop(other, (None, other.hex[:4]))
            self._queue_names.pop(pid, None)
            m = Match("queue", other, None, self._on_finish)
            m.names[other] = other_name
            m.join(pid, name, tag)
            self._register(m)
            return m
        self.queue[pid] = now
        self._queue_names[pid] = (name, tag)
        return None

    def leave_queue(self, pid: uuid.UUID):
        self.queue.pop(pid, None)
        self._queue_names.pop(pid, None)

    async def _on_finish(self, m: Match):
        for p in m.players:
            if self.by_player.get(p) == m.id:
                self.by_player.pop(p, None)
        self._finished_at[m.id] = time.time()
        try:
            row, logs = m.db_rows()
            async with SessionLocal() as session:
                session.add(row)
                await session.flush()          # FK: the match first, then the logs
                session.add_all(logs)
                await session.execute(delete(LiveMatch).where(LiveMatch.id == m.id))
                await session.commit()
        except Exception:
            log.exception("не удалось сохранить матч %s", m.id)

    # ---- surviving a restart ----
    def _unfinished(self) -> List[Match]:
        return [m for m in self.matches.values() if not m._saved and (m.active or m.solo is not None)]

    async def _write(self, matches: List[Match]):
        if not matches:
            return
        async with SessionLocal() as session:
            for m in matches:
                state = m.to_state()
                await session.execute(
                    insert(LiveMatch).values(id=m.id, state=state)
                    .on_conflict_do_update(index_elements=[LiveMatch.id], set_={"state": state, "saved_at": func.now()})
                )
            await session.commit()
            # a match may have ended (and deleted its row) while this write was in flight
            ended = [m.id for m in matches if m._saved]
            if ended:
                await session.execute(delete(LiveMatch).where(LiveMatch.id.in_(ended)))
                await session.commit()

    async def checkpoint(self):
        """Write the matches whose content changed since the last write (a move, a phase)."""
        changed = []
        for m in self._unfinished():
            h = m.content_hash()
            if h != m.persisted_hash:
                changed.append((m, h))
        await self._write([m for m, _ in changed])
        for m, h in changed:
            m.persisted_hash = h

    async def checkpoint_forever(self):
        while True:
            await asyncio.sleep(settings.checkpoint_s)
            try:
                await self.checkpoint()
            except Exception:
                log.exception("чекпойнт матчей не записан")

    async def restore(self) -> int:
        """On startup: bring back the matches of the previous process."""
        async with SessionLocal() as session:
            rows = (await session.scalars(select(LiveMatch))).all()
            finished = set((await session.scalars(
                select(MatchRow.id).where(MatchRow.id.in_([r.id for r in rows]))
            )).all()) if rows else set()
        broken = []
        for row in rows:
            if row.id in finished:                 # already written as finished — a stale checkpoint
                broken.append(row.id)
                continue
            try:
                m = Match.from_state(row.state, self._on_finish)
            except Exception:
                log.exception("матч %s не восстановлен, удаляю", row.id)
                broken.append(row.id)
                continue
            m.persisted_hash = m.content_hash()
            self.matches[m.id] = m
            if m.code:
                self.by_code[m.code] = m.id
            if m.active:
                for p in m.players:
                    self.by_player[p] = m.id
        if broken:
            async with SessionLocal() as session:
                await session.execute(delete(LiveMatch).where(LiveMatch.id.in_(broken)))
                await session.commit()
        if rows:
            log.info("восстановлено матчей после перезапуска: %d из %d", len(rows) - len(broken), len(rows))
        return len(rows) - len(broken)

    async def shutdown(self):
        """On shutdown: write every unfinished match with exact clocks, then stop its timers."""
        unfinished = self._unfinished()
        try:
            await self._write(unfinished)
            if unfinished:
                log.info("сохранено матчей перед остановкой: %d", len(unfinished))
        except Exception:
            log.exception("матчи перед остановкой не сохранены")
        for m in self.matches.values():
            m._disarm_all()
        self.__init__()                            # empty: tests start the app again in one process

    async def sweep_forever(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            for mid, ts in list(self._finished_at.items()):
                if now - ts > FINISHED_TTL_S:
                    self._finished_at.pop(mid, None)
                    m = self.matches.pop(mid, None)
                    if m and m.code:
                        self.by_code.pop(m.code, None)


registry = MatchRegistry()

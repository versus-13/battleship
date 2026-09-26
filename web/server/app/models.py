from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary,
    SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    secret_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    name_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name_hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # hidden by reports
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Match(Base):
    __tablename__ = "h2h_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str | None] = mapped_column(String(8), unique=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)          # room | queue
    player_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    player_b: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    status: Mapped[str] = mapped_column(String(12), nullable=False)       # waiting|placing|playing|finished|abandoned
    winner: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    end_reason: Mapped[str | None] = mapped_column(String(16))            # fleet_sunk|resigned|idle|disconnect|abandoned (old rows: forfeit, move_timeout)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("kind IN ('room','queue')", name="ck_match_kind"),
        CheckConstraint("status IN ('waiting','placing','playing','finished','abandoned')", name="ck_match_status"),
    )


class GameLog(Base):
    """Telemetry unit: one attacker against one board."""
    __tablename__ = "game_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_game_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(4), nullable=False)           # h2m | h2h
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("h2h_matches.id"))
    attacker_kind: Mapped[str] = mapped_column(String(10), nullable=False)  # player|model|heuristic
    attacker_player: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    attacker_label: Mapped[str] = mapped_column(Text, nullable=False)
    defender_player: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    ships: Mapped[list] = mapped_column(JSONB, nullable=False)
    shots: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    n_shots: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fleet_cleared: Mapped[bool] = mapped_column(Boolean, nullable=False)
    won: Mapped[bool | None] = mapped_column(Boolean)
    client: Mapped[str] = mapped_column(String(16), nullable=False)
    client_version: Mapped[str | None] = mapped_column(String(32))
    think_ms: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))       # time per move
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_info: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    rules: Mapped[dict | None] = mapped_column(JSONB)                          # None = Russian rules
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("client_game_id", "attacker_label", name="uq_game_log_client_attacker"),
        CheckConstraint("mode IN ('h2m','h2h')", name="ck_game_log_mode"),
        CheckConstraint("attacker_kind IN ('player','model','heuristic')", name="ck_game_log_attacker_kind"),
        Index("ix_game_logs_attacker_created", "attacker_player", "created_at"),
        Index("ix_game_logs_mode_cleared", "mode", "fleet_cleared"),
    )


REPORT_REASONS = ("name", "impersonation", "cheating", "stalling", "bug")


class Report(Base):
    """A report on the opponent of an H2H match: one per match per reporter."""
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # no FK: during a match its h2h_matches row does not exist yet (written at the end)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reporter: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    reported: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    reported_name: Mapped[str | None] = mapped_column(Text)            # the name at the time of the report
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("match_id", "reporter", name="uq_report_match_reporter"),
        CheckConstraint("reason IN ('name','impersonation','cheating','stalling','bug')", name="ck_report_reason"),
        Index("ix_reports_reported_reason", "reported", "reason"),
    )


class LiveMatch(Base):
    """An unfinished H2H match (Match.to_state()): restored on startup, deleted when it ends."""
    __tablename__ = "live_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NameReject(Base):
    __tablename__ = "name_rejects"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

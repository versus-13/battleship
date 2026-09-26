from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .rules import PlacementError, validate_placement


Ships = list[list[int]]


def ships_validator(v: Ships) -> Ships:
    try:
        return validate_placement(v)
    except PlacementError as e:
        raise ValueError(str(e))


# ---- players ----
class PlayerCreated(BaseModel):
    player_id: uuid.UUID
    secret: str


class Stats(BaseModel):
    games: int = 0
    wins: int = 0
    win_rate: float | None = None
    avg_shots: float | None = None
    best_shots: int | None = None
    h2h_games: int = 0
    h2m_games: int = 0
    h2h_wins: int = 0


class PlayerOut(BaseModel):
    player_id: uuid.UUID
    name: str | None
    tag: str                    # short id suffix for "Name#a1b2"
    created_at: datetime | None = None
    stats: Stats | None = None
    name_hidden: bool = False   # the name was hidden by reports — ask for a new one


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ReportIn(BaseModel):
    reason: Literal["name", "impersonation", "cheating", "stalling", "bug"]


class NameOut(BaseModel):
    name: str
    tag: str


class LeaderboardRow(BaseModel):
    player_id: uuid.UUID
    name: str | None
    tag: str
    games: int
    wins: int
    win_rate: float
    avg_shots: float | None      # over cleared boards; None — never cleared one


# ---- telemetry ----
class Attacker(BaseModel):
    kind: Literal["player", "model", "heuristic"]
    version: str | None = None


class Defender(BaseModel):
    kind: Literal["player", "model_board"]


THINK_MS_CAP = 10 * 60 * 1000
CLIENT_INFO_KEYS = {"platform", "screen", "touch", "placement", "model_backend", "ua_family"}


def clean_client_info(v: dict) -> dict:
    """Known keys and short values only — no personal data."""
    out = {}
    for k, val in (v or {}).items():
        if k not in CLIENT_INFO_KEYS:
            continue
        if isinstance(val, str):
            out[k] = val[:64]
        elif isinstance(val, (bool, int, float)):
            out[k] = val
        elif isinstance(val, list) and len(val) <= 4 and all(isinstance(x, (int, float)) for x in val):
            out[k] = val
    return out


class GameLogIn(BaseModel):
    attacker: Attacker
    defender: Defender
    ships: Ships
    shots: list[int] = Field(max_length=100)
    fleet_cleared: bool
    won: bool | None = None
    think_ms: list[int] | None = Field(default=None, max_length=100)   # time per move, ms
    started_at: float | None = None                                      # unix seconds on the client

    @field_validator("ships")
    @classmethod
    def _ships(cls, v):
        return ships_validator(v)

    @model_validator(mode="after")
    def _think_ms(self):
        if self.think_ms is not None:
            if len(self.think_ms) != len(self.shots):
                raise ValueError("think_ms должен быть той же длины, что shots")
            self.think_ms = [min(max(int(t), 0), THINK_MS_CAP) for t in self.think_ms]
        return self


class GamesIn(BaseModel):
    client_game_id: uuid.UUID
    mode: Literal["h2m"]
    client: Literal["web", "android", "ios"] = "web"
    client_version: str | None = Field(default=None, max_length=32)
    client_info: dict = Field(default_factory=dict)
    logs: list[GameLogIn] = Field(min_length=1, max_length=2)

    @field_validator("client_info")
    @classmethod
    def _client_info(cls, v):
        return clean_client_info(v)


class RejectedLog(BaseModel):
    index: int
    code: str
    detail: str | None = None


class GamesOut(BaseModel):
    accepted: list[int]
    rejected: list[RejectedLog]


# ---- rooms ----
class RoomCreated(BaseModel):
    match_id: uuid.UUID
    code: str
    ws_url: str


class RoomInfo(BaseModel):
    match_id: uuid.UUID
    code: str
    status: str
    host_name: str | None
    host_tag: str


class RoomJoined(BaseModel):
    match_id: uuid.UUID
    ws_url: str


class QueueOut(BaseModel):
    status: Literal["queued", "matched"]
    match_id: uuid.UUID | None = None
    ws_url: str | None = None


class ModelInfo(BaseModel):
    version: str
    url: str
    input_shape: list[int]
    output_shape: list[int]

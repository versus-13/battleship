from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://localhost:5432/battleship"
    cors_origins: list[str] = ["http://localhost:5173"]
    static_dir: str | None = None          # frontend/dist in production

    # model for the client
    model_url: str = "/model/battleship_int8.onnx"
    model_version: str = "int8-35d9f084"

    # names
    name_change_cooldown_s: int = 600

    # reports: this many different players reporting a name (or impersonation) hide it;
    # cheating and "something broke" go to text files in reports_dir for manual review
    name_report_threshold: int = 3
    reports_dir: str = "reports"

    # telemetry
    games_per_hour: int = 60

    # H2H timers (seconds)
    room_wait_s: int = 15 * 60
    placing_s: int = 3 * 60
    move_s: float = 30                      # then a random shot is made for the player
    idle_moves_limit: int = 5               # this many auto-moves in a row — the player is gone, loss
    reconnect_budget_s: float = 90          # offline time per player per match; the move timer waits
    disconnect_after_budget_s: float = 120  # offline this long after the budget ran out — loss
    solo_idle_s: float = 5 * 60             # finishing the board after the opponent left
    disconnect_grace_s: float = 60          # the host left the waiting room
    # restart: unfinished matches are saved (checkpoint_s after a change, fully on shutdown)
    # and restored; for restart_grace_s after startup offline time costs nobody anything
    restart_grace_s: float = 60
    checkpoint_s: float = 1.0
    queue_ttl_s: int = 120


settings = Settings()

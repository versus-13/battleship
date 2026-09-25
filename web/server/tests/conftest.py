import os
import uuid

os.environ.setdefault("BS_DATABASE_URL", "postgresql+asyncpg://localhost:5432/battleship_test")
os.environ.setdefault("BS_DISCONNECT_GRACE_S", "1")
os.environ.setdefault("BS_RECONNECT_BUDGET_S", "1")
os.environ.setdefault("BS_DISCONNECT_AFTER_BUDGET_S", "1")
os.environ.setdefault("BS_IDLE_MOVES_LIMIT", "2")
os.environ.setdefault("BS_SOLO_IDLE_S", "5")
os.environ.setdefault("BS_MOVE_S", "2")
os.environ.setdefault("BS_PLACING_S", "2")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import engine
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE game_logs, h2h_matches, name_rejects, players CASCADE"))
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def player(client):
    r = await client.post("/api/players")
    assert r.status_code == 201
    body = r.json()
    return {"id": body["player_id"], "secret": body["secret"],
            "headers": {"Authorization": f"Bearer {body['secret']}"}}


SHIPS = [[0, 1, 2, 3], [30, 31, 32], [34, 35, 36], [50, 51], [53, 54], [56, 57], [70], [72], [74], [76]]
ALL_SHOTS = [c for s in SHIPS for c in s]

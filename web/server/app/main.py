from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .config import settings
from .db import engine
from .matchmaking import registry
from .routers import games, players, rooms, stats
from .schemas import ModelInfo
from .ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(registry.sweep_forever())
    yield
    sweeper.cancel()
    await engine.dispose()


app = FastAPI(title="Морской бой", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(players.router)
app.include_router(games.router)
app.include_router(stats.router)
app.include_router(rooms.router)
app.include_router(ws_router)


@app.get("/api/model", response_model=ModelInfo)
async def model_info():
    return ModelInfo(version=settings.model_version, url=settings.model_url,
                     input_shape=[1, 8, 10, 10], output_shape=[1, 10, 10])


@app.get("/healthz")
async def healthz():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("select 1"))
        db = True
    except Exception:
        db = False
    return {"ok": db, "db": db, "matches": len(registry.matches), "queue": len(registry.queue)}


if settings.static_dir and Path(settings.static_dir).is_dir():
    static = Path(settings.static_dir)
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
    app.mount("/model", StaticFiles(directory=static / "model"), name="model")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = static / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static / "index.html")

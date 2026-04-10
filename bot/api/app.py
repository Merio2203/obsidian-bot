"""Инициализация FastAPI приложения."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bot.config import settings
from bot.database import engine
from bot.database.models import init_db
from bot.services.obsidian_service import ObsidianService

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="ObsidianBot Mini App API", version="1.0.0")

    origins = settings.api_cors_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    async def _on_startup() -> None:
        await init_db(engine)
        await ObsidianService().ensure_dirs()

    return app


app = create_app()

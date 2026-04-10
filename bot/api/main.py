"""Точка запуска HTTP API."""

from __future__ import annotations

import uvicorn

from bot.config import settings


def main() -> None:
    uvicorn.run(
        "bot.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

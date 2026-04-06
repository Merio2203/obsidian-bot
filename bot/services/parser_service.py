"""Сервис парсинга статей и метаданных YouTube."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL


@dataclass(frozen=True)
class ArticleData:
    """Результат парсинга статьи."""

    title: str
    content: str


@dataclass(frozen=True)
class YouTubeData:
    """Результат парсинга YouTube-метаданных."""

    title: str
    description: str
    author: str


class ParserService:
    """Единый сервис получения данных по URL."""

    YOUTUBE_RE = re.compile(r"(youtube\.com|youtu\.be)", re.IGNORECASE)

    @classmethod
    def is_youtube_url(cls, url: str) -> bool:
        """Определяет, является ли URL ссылкой на YouTube."""
        return bool(cls.YOUTUBE_RE.search(url or ""))

    async def parse_article(self, url: str) -> ArticleData:
        """Парсит HTML-страницу и возвращает заголовок + основной текст."""
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else "Без названия"
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        body = "\n".join([p for p in paragraphs if p]).strip()
        if not body:
            body = "Не удалось извлечь текст статьи."
        return ArticleData(title=title, content=body[:12000])

    async def parse_youtube(self, url: str) -> YouTubeData:
        """Получает метаданные YouTube-видео без скачивания."""

        def _extract() -> dict:
            with YoutubeDL({"quiet": True, "skip_download": True, "extract_flat": False}) as ydl:
                return ydl.extract_info(url, download=False)

        info = await asyncio.to_thread(_extract)
        title = (info.get("title") or "Без названия").strip()
        description = (info.get("description") or "").strip()
        author = (info.get("uploader") or info.get("channel") or "Неизвестный автор").strip()
        return YouTubeData(title=title, description=description[:8000], author=author)

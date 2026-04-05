"""Сервис взаимодействия с RouterAI (OpenAI-compatible API)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import APIError, AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import settings
from bot.database.models import AICache

logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Контролируемая ошибка при работе с AI."""


@dataclass(frozen=True, slots=True)
class AIRequestConfig:
    """Конфигурация запроса по типу операции."""

    task_type: str
    max_tokens: int


REQUEST_CONFIGS = {
    "tags": AIRequestConfig(task_type="tags", max_tokens=50),
    "article_summary": AIRequestConfig(task_type="article_summary", max_tokens=500),
    "youtube_summary": AIRequestConfig(task_type="youtube_summary", max_tokens=300),
    "subtasks": AIRequestConfig(task_type="subtasks", max_tokens=400),
    "cursor_prompt": AIRequestConfig(task_type="cursor_prompt", max_tokens=1500),
}


class AIService:
    """Асинхронный сервис RouterAI с кэшированием ответов."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._client = AsyncOpenAI(
            api_key=settings.routerai_api_key,
            base_url=settings.routerai_base_url,
        )

    async def generate_tags(self, text: str) -> str:
        """Генерирует теги для короткой заметки."""
        system_prompt = "Ты помощник для Obsidian. Верни только список тегов через запятую на русском."
        user_prompt = f"Сгенерируй до 5 тегов для заметки:\n\n{text}"
        return await self._cached_completion("tags", system_prompt, user_prompt)

    async def summarize_article(self, title: str, content: str) -> str:
        """Генерирует краткое резюме статьи и ключевые мысли."""
        system_prompt = (
            "Ты помощник для базы знаний. Кратко резюмируй статью на русском. "
            "Формат: Резюме + 5 ключевых мыслей."
        )
        user_prompt = f"Заголовок: {title}\n\nТекст статьи:\n{content}"
        return await self._cached_completion("article_summary", system_prompt, user_prompt)

    async def summarize_youtube(self, title: str, description: str, author: str) -> str:
        """Генерирует резюме YouTube-видео по метаданным."""
        system_prompt = (
            "Ты помощник для базы знаний. Сделай краткое резюме видео на русском "
            "по названию и описанию."
        )
        user_prompt = f"Название: {title}\nАвтор: {author}\nОписание:\n{description}"
        return await self._cached_completion("youtube_summary", system_prompt, user_prompt)

    async def generate_subtasks_and_criteria(self, task_context: str) -> str:
        """Разбивает задачу на подзадачи и критерии готовности."""
        system_prompt = (
            "Ты проектный ассистент. Сформируй подзадачи и критерии готовности в markdown на русском."
        )
        user_prompt = f"Контекст задачи:\n{task_context}"
        return await self._cached_completion("subtasks", system_prompt, user_prompt)

    async def generate_cursor_prompt(self, payload: dict[str, Any]) -> str:
        """Генерирует структурированный промт для Cursor AI."""
        system_prompt = (
            "Ты технический ассистент. Сформируй структурированный промт для Cursor AI на русском "
            "с секциями: Контекст, Что нужно сделать, Технические детали, Шаги реализации, "
            "Ожидаемый результат, Критерии готовности."
        )
        user_prompt = f"Данные задачи:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        return await self._cached_completion("cursor_prompt", system_prompt, user_prompt)

    async def _cached_completion(self, task_type: str, system_prompt: str, user_prompt: str) -> str:
        config = REQUEST_CONFIGS[task_type]
        prompt_hash = self._make_hash(task_type, system_prompt, user_prompt)

        cached = await self._get_cache(prompt_hash)
        if cached:
            return cached

        response = await self._request_with_retry(config.max_tokens, system_prompt, user_prompt)
        await self._save_cache(prompt_hash, config.task_type, response)
        return response

    async def _request_with_retry(self, max_tokens: int, system_prompt: str, user_prompt: str) -> str:
        last_error: Exception | None = None
        attempts = settings.ai_max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                completion = await self._client.chat.completions.create(
                    model=settings.routerai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                )
                content = completion.choices[0].message.content
                if not content:
                    raise AIServiceError("AI вернул пустой ответ")
                return content.strip()
            except (APIError, AIServiceError, TimeoutError) as exc:
                last_error = exc
                logger.warning("Ошибка AI (попытка %s/%s): %s", attempt, attempts, exc)
                if attempt < attempts:
                    await asyncio.sleep(settings.ai_retry_delay_seconds)

        raise AIServiceError(f"Не удалось получить ответ AI после {attempts} попыток") from last_error

    async def _get_cache(self, prompt_hash: str) -> str | None:
        async with self._session_factory() as session:
            result = await session.execute(select(AICache).where(AICache.prompt_hash == prompt_hash))
            entity = result.scalar_one_or_none()
            if entity:
                return entity.response
            return None

    async def _save_cache(self, prompt_hash: str, task_type: str, response: str) -> None:
        async with self._session_factory() as session:
            session.add(AICache(prompt_hash=prompt_hash, task_type=task_type, response=response))
            await session.commit()

    @staticmethod
    def _make_hash(task_type: str, system_prompt: str, user_prompt: str) -> str:
        normalized = f"{task_type}\n{system_prompt.strip()}\n{user_prompt.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

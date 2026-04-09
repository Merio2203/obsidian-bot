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


@dataclass(frozen=True)
class AIRequestConfig:
    """Конфигурация запроса по типу операции."""

    task_type: str
    max_tokens: int


REQUEST_CONFIGS = {
    "tags_general": AIRequestConfig(task_type="tags_general", max_tokens=80),
    "task_tags_links": AIRequestConfig(task_type="task_tags_links", max_tokens=150),
    "diary_tags_links": AIRequestConfig(task_type="diary_tags_links", max_tokens=150),
    "resource_tags_links": AIRequestConfig(task_type="resource_tags_links", max_tokens=150),
    "short_title": AIRequestConfig(task_type="short_title", max_tokens=50),
    "task_slug": AIRequestConfig(task_type="task_slug", max_tokens=50),
    "article_summary": AIRequestConfig(task_type="article_summary", max_tokens=500),
    "youtube_summary": AIRequestConfig(task_type="youtube_summary", max_tokens=300),
    "cursor_prompt": AIRequestConfig(task_type="cursor_prompt", max_tokens=1500),
    "diary_help": AIRequestConfig(task_type="diary_help", max_tokens=300),
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
        """Генерирует теги для заметки/идеи/входящих."""
        system_prompt = (
            "Ты помощник Obsidian. Верни только теги через запятую, 2-5 штук, без объяснений."
        )
        user_prompt = f"Текст:\n{text}"
        return await self._cached_completion("tags_general", system_prompt, user_prompt)

    async def generate_short_title(self, raw_title: str, content: str = "") -> str:
        """Формирует короткий и читаемый title."""
        system_prompt = (
            "Сократи заголовок до короткого, понятного названия на русском. "
            "Верни только одну строку без кавычек. "
            "Требования к названию файла: только русские/латинские буквы, цифры, пробелы, дефисы; "
            "без эмодзи; без символов / \\ : * ? \" < > |; максимум 50 символов."
        )
        user_prompt = f"Сырой заголовок: {raw_title}\nКонтекст:\n{content}"
        return await self._cached_completion("short_title", system_prompt, user_prompt)

    async def generate_task_slug(self, title: str, description: str, project_name: str = "") -> str:
        """Генерирует осмысленный slug имени файла задачи."""
        system_prompt = (
            "Сгенерируй короткое имя файла (slug) для задачи в Obsidian.\n"
            "Требования:\n"
            "- Отражает суть задачи (не просто глагол)\n"
            "- Если есть проект — можно добавить короткое упоминание контекста\n"
            "- Только строчные буквы, цифры, дефисы\n"
            "- БЕЗ эмодзи, БЕЗ пробелов\n"
            "- БЕЗ символов: / \\ : * ? \" < > |\n"
            "- Максимум 50 символов\n"
            "- На русском языке (транслитерация не нужна)\n"
            "Верни только slug одной строкой, без кавычек и пояснений."
        )
        user_prompt = (
            f"Название задачи: {title}\n"
            f"Проект: {project_name or 'без проекта'}\n"
            f"Описание:\n{description}"
        )
        return await self._cached_completion("task_slug", system_prompt, user_prompt)

    async def generate_task_tags_and_links(
        self,
        title: str,
        description: str,
        project_name: str,
        existing_links: list[str],
    ) -> dict[str, Any]:
        """Генерирует теги и wiki-links для задачи."""
        link_rules = (
            "Правила формирования внутренних ссылок Obsidian (wikilinks):\n"
            "1. Формат ссылки: [[Название заметки]] — только имя файла БЕЗ расширения .md\n"
            "2. Если нужен отображаемый текст: [[Название заметки|Псевдоним]]\n"
            "3. НЕ используй markdown-ссылки [текст](путь) для внутренних ссылок\n"
            "4. НЕ добавляй расширение .md в ссылках\n"
            "5. НЕ добавляй путь к папке, если имя файла уникально\n"
            "6. Используй ТОЛЬКО имена из предоставленного списка существующих файлов vault\n"
            "7. НЕ придумывай несуществующие файлы\n"
            "8. Для связи задачи с проектом используй ТОЛЬКО файл вида \"Проект X\" "
            "(например [[Проект Sever VPN]]), не используй [[Sever VPN]]\n"
            "9. Если в списке есть и \"Проект X\" и \"X\" — всегда выбирай \"Проект X\"\n"
            "10. Возвращай links в виде списка: [\"[[Файл1]]\", \"[[Файл2]]\"]"
        )
        system_prompt = (
            "Ты помощник по оформлению Obsidian. Не придумывай содержание задачи. "
            "Верни JSON: {\"tags\": [..], \"links\": [..]}. "
            "Теги 2-5 штук, короткие и релевантные. "
            f"{link_rules}"
        )
        user_prompt = json.dumps(
            {
                "title": title,
                "description": description,
                "project_name": project_name,
                "existing_files": existing_links,
            },
            ensure_ascii=False,
        )
        text = await self._cached_completion("task_tags_links", system_prompt, user_prompt)
        return self._safe_parse_json(text, fallback={"tags": ["задача"], "links": []})

    async def generate_links_for_content(
        self,
        content_type: str,
        text: str,
        existing_links: list[str],
    ) -> dict[str, Any]:
        """Генерирует теги и links для произвольного контента."""
        key = "diary_tags_links" if content_type == "diary" else "resource_tags_links"
        link_rules = (
            "Правила формирования внутренних ссылок Obsidian (wikilinks):\n"
            "1. Формат ссылки: [[Название заметки]] — только имя файла БЕЗ расширения .md\n"
            "2. Если нужен отображаемый текст: [[Название заметки|Псевдоним]]\n"
            "3. НЕ используй markdown-ссылки [текст](путь) для внутренних ссылок\n"
            "4. НЕ добавляй расширение .md в ссылках\n"
            "5. НЕ добавляй путь к папке, если имя файла уникально\n"
            "6. Используй ТОЛЬКО имена из предоставленного списка существующих файлов vault\n"
            "7. НЕ придумывай несуществующие файлы\n"
            "8. Если это ссылка на проект — используй заметку \"Проект X\", не голое имя папки \"X\"\n"
            "9. Если есть оба варианта \"Проект X\" и \"X\", выбирай только \"Проект X\"\n"
            "10. Возвращай links в виде списка: [\"[[Файл1]]\", \"[[Файл2]]\"]"
        )
        system_prompt = (
            "Ты помощник Obsidian. Верни JSON: {\"tags\": [..], \"links\": [..]}. "
            "Теги 2-5 штук, короткие и релевантные. "
            f"{link_rules}"
        )
        user_prompt = json.dumps(
            {
                "content_type": content_type,
                "text": text,
                "existing_files": existing_links,
            },
            ensure_ascii=False,
        )
        text_out = await self._cached_completion(key, system_prompt, user_prompt)
        return self._safe_parse_json(text_out, fallback={"tags": [], "links": []})

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
        return await self.summarize_video(title=title, description=description, author=author)

    async def summarize_video(self, title: str, description: str, author: str) -> str:
        """Генерирует резюме видео по метаданным."""
        system_prompt = (
            "Ты помощник для базы знаний. Сделай краткое резюме видео на русском "
            "по названию и описанию."
        )
        user_prompt = f"Название: {title}\nАвтор: {author}\nОписание:\n{description}"
        return await self._cached_completion("youtube_summary", system_prompt, user_prompt)

    async def generate_task_title_from_description(self, description: str, project_name: str = "") -> str:
        """Генерирует короткий заголовок задачи по описанию."""
        system_prompt = (
            "Сгенерируй короткое и понятное название задачи на русском по описанию. "
            "Верни только одну строку без кавычек, максимум 60 символов."
        )
        user_prompt = (
            f"Проект: {project_name or 'без проекта'}\n"
            f"Описание задачи:\n{description}"
        )
        return await self._cached_completion("short_title", system_prompt, user_prompt)

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
            except (APIError, AIServiceError, TimeoutError):
                logger.warning("Ошибка AI (попытка %s/%s)", attempt, attempts, exc_info=True)
                if attempt < attempts:
                    await asyncio.sleep(settings.ai_retry_delay_seconds)
                last_error = AIServiceError("Запрос AI завершился с ошибкой")

        raise AIServiceError(f"Не удалось получить ответ AI после {attempts} попыток") from last_error

    async def _get_cache(self, prompt_hash: str) -> str | None:
        async with self._session_factory() as session:
            result = await session.execute(select(AICache).where(AICache.prompt_hash == prompt_hash))
            entity = result.scalar_one_or_none()
            return entity.response if entity else None

    async def _save_cache(self, prompt_hash: str, task_type: str, response: str) -> None:
        async with self._session_factory() as session:
            session.add(AICache(prompt_hash=prompt_hash, task_type=task_type, response=response))
            await session.commit()

    @staticmethod
    def _make_hash(task_type: str, system_prompt: str, user_prompt: str) -> str:
        normalized = f"{task_type}\n{system_prompt.strip()}\n{user_prompt.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_parse_json(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return fallback
        except Exception:
            return fallback

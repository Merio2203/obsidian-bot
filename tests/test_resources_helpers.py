from __future__ import annotations

from bot.handlers.resources import _extract_key_points, _normalize_tags
from bot.services.parser_service import ParserService
from bot.utils.formatters import render_resource_markdown


def test_is_youtube_url() -> None:
    assert ParserService.is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert ParserService.is_youtube_url("https://youtu.be/abc")
    assert not ParserService.is_youtube_url("https://example.com/article")


def test_normalize_tags_resources() -> None:
    tags = _normalize_tags("#AI, Product Management, ai, python")
    assert tags == ["ai", "product-management", "python"]


def test_extract_key_points() -> None:
    summary = "- Пункт 1\n- Пункт 2\nТекст"
    assert _extract_key_points(summary) == ["Пункт 1", "Пункт 2"]


def test_render_resource_markdown() -> None:
    markdown = render_resource_markdown(
        title="Как устроен FastAPI",
        url="https://example.com/fastapi",
        resource_type="article",
        tags=["python", "fastapi"],
        summary="Короткое резюме.",
        key_points=["Пункт A", "Пункт B"],
    )
    assert "title: Как устроен FastAPI" in markdown
    assert "type: article" in markdown
    assert "- Пункт A" in markdown

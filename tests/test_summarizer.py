from __future__ import annotations

from datetime import UTC, datetime

from src.models import Article
from src.summarizer import build_summary_prompt


def test_build_summary_prompt_injects_geo_context_when_article_is_geo_boosted() -> None:
    """Geo-relevant articles should carry an explicit Spain/Europe instruction into summarization."""

    article = Article(
        title="Spain AI regulation update",
        url="https://example.com/spain-ai-regulation",
        source_name="Feed A",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="European regulation update for the Spanish telecom market.",
        category="ai",
        geo_boost=True,
    )

    prompt = build_summary_prompt(article, max_words=50)

    assert "Mention that relevance explicitly" in prompt
    assert "50 words or less" in prompt
    assert article.raw_content in prompt


def test_build_summary_prompt_keeps_geo_instruction_conditional_for_generic_articles() -> None:
    """Generic articles should not force a Spain/Europe angle in the summary prompt."""

    article = Article(
        title="Generic AI update",
        url="https://example.com/generic-ai-update",
        source_name="Feed B",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="Global enterprise AI release.",
        category="ai",
    )

    prompt = build_summary_prompt(article)

    assert "only when the article clearly supports it" in prompt
    assert "Mention that relevance explicitly" not in prompt
from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.models import AiSummarySettings, Article
from src.summarizer import build_summary_prompt, summarize_articles


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


def test_summarize_articles_placeholder_extracts_first_max_words() -> None:
    """Placeholder provider should extract the first N words offline."""

    article = Article(
        title="Spain AI regulation update",
        url="https://example.com/spain-ai-regulation",
        source_name="Feed A",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="European regulation update for the Spanish telecom market.",
        category="ai",
        geo_boost=True,
    )

    settings = AiSummarySettings(provider="placeholder", max_words=5)
    summarized = summarize_articles([article], settings, api_key=None)

    assert "Spain/Europe relevance" in summarized[0].summary
    assert "European regulation update for the" in summarized[0].summary


def test_summarize_articles_uses_configured_model_and_prompt_template_with_external_provider() -> None:
    """External providers (Groq, xAI, etc.) should honor model and prompt template."""

    article = Article(
        title="Spain AI regulation update",
        url="https://example.com/spain-ai-regulation",
        source_name="Feed A",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="European regulation update for the Spanish telecom market.",
        category="ai",
        geo_boost=True,
    )
    captured_request: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["authorization"] = request.headers.get("Authorization")
        captured_request["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Spain and Europe remain central to this telecom AI policy update."
                        }
                    }
                ]
            },
        )

    settings = AiSummarySettings(
        provider="groq",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        model="grok-vision-beta",
        max_words=12,
        prompt_template="Custom prompt for {max_words} words. {geo_instruction} Article: {content}",
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summarized = summarize_articles([article], settings, "groq-test-key", client=client)

    assert captured_request["authorization"] == "Bearer groq-test-key"
    assert '"model":"grok-vision-beta"' in str(captured_request["payload"])
    assert "Custom prompt for 12 words." in str(captured_request["payload"])
    assert "Mention that relevance explicitly" in str(captured_request["payload"])
    assert summarized[0].summary == "Spain and Europe remain central to this telecom AI policy update."


def test_summarize_articles_enforces_the_configured_word_limit_with_external_provider() -> None:
    """Post-processing should trim model output when it exceeds the limit."""

    article = Article(
        title="Generic AI update",
        url="https://example.com/generic-ai-update",
        source_name="Feed B",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="Global enterprise AI release.",
        category="ai",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "One two three four five six seven eight nine ten"
                        }
                    }
                ]
            },
        )

    settings = AiSummarySettings(
        provider="groq",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        max_words=5,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summarized = summarize_articles(
            [article],
            settings,
            "groq-test-key",
            client=client,
        )

    assert summarized[0].summary == "One two three four five"


def test_summarize_articles_falls_back_to_excerpt_when_provider_fails() -> None:
    """When provider calls fail, fallback summary should use the article excerpt/content."""

    article = Article(
        title="Network outage analysis",
        url="https://example.com/network-outage",
        source_name="Feed C",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="Original excerpt content for fallback behavior in case of provider failure.",
        category="telco",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "upstream error"}})

    settings = AiSummarySettings(
        provider="groq",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        max_words=6,
        max_retries=0,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summarized = summarize_articles([article], settings, "groq-test-key", client=client)

    assert summarized[0].summary == "Original excerpt content for fallback behavior"


def test_summarize_articles_retries_rate_limit_then_succeeds() -> None:
    """Transient rate limits should be retried with backoff and eventually return summary."""

    article = Article(
        title="Spain AI update",
        url="https://example.com/spain-ai",
        source_name="Feed D",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="AI update for Spain telecom market.",
        category="ai",
    )
    attempts = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})

        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Recovered summary after retry."}}]},
        )

    settings = AiSummarySettings(
        provider="groq",
        api_url="https://api.groq.com/openai/v1/chat/completions",
        max_words=10,
        max_retries=2,
        retry_base_seconds=0.0,
        retry_max_seconds=0.0,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summarized = summarize_articles([article], settings, "groq-test-key", client=client)

    assert attempts["count"] == 2
    assert summarized[0].summary == "Recovered summary after retry."

from __future__ import annotations

from dataclasses import replace
import logging
import time

import httpx

from .models import AiSummarySettings, Article
from .summary_prompts import DEFAULT_RELEVANCE_INSTRUCTION, DEFAULT_SUMMARY_PROMPT_TEMPLATE, GEO_RELEVANCE_INSTRUCTION

LOGGER = logging.getLogger(__name__)
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def build_summary_prompt(
    article: Article,
    *,
    max_words: int = 60,
    prompt_template: str = DEFAULT_SUMMARY_PROMPT_TEMPLATE,
) -> str:
    """Render a summary prompt that carries geo-relevance into downstream summarization."""

    content = article.raw_content.strip() or article.title.strip()
    geo_instruction = GEO_RELEVANCE_INSTRUCTION if article.geo_boost else DEFAULT_RELEVANCE_INSTRUCTION
    return prompt_template.format(
        max_words=max_words,
        geo_instruction=geo_instruction,
        content=content,
    )


def summarize_articles(
    articles: list[Article],
    settings: AiSummarySettings,
    api_key: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> list[Article]:
    """Attach AI summaries to each article when the feature is enabled.
    
    Provider routing:
    - 'placeholder': Simple heuristic (works offline, always available).
    - 'groq' or 'xai': Requires api_key and active billing.
    """

    if not settings.enabled or not articles:
        return articles

    provider = settings.provider or "placeholder"
    
    if provider == "placeholder":
        return [replace(article, summary=_placeholder_summary(article, settings)) for article in articles]
    
    # For external providers (Groq, xAI, etc.)
    active_key = api_key or settings.api_key
    if active_key is None:
        LOGGER.info("Resumen IA con proveedor '%s' habilitado pero sin clave efectiva; se omite.", provider)
        return articles

    own_client = client is None
    http_client = client or httpx.Client(timeout=settings.timeout_seconds)

    try:
        return [
            replace(article, summary=generate_summary(article, settings, active_key, client=http_client) or article.summary or _excerpt_fallback_summary(article, settings.max_words))
            for article in articles
        ]
    finally:
        if own_client:
            http_client.close()


def _placeholder_summary(article: Article, settings: AiSummarySettings) -> str | None:
    """Generate a simple offline summary for demonstration or fallback.
    
    Extracts the first `max_words` words from content and annotates if geo-relevant.
    """
    
    content = article.raw_content.strip() or article.title.strip()
    words = content.split()
    summary = " ".join(words[: settings.max_words])
    
    if article.geo_boost:
        summary = f"[Spain/Europe relevance] {summary}"
    
    return summary[:500] if summary else None


def generate_summary(
    article: Article,
    settings: AiSummarySettings,
    api_key: str,
    *,
    client: httpx.Client,
) -> str | None:
    """Generate a single article summary using Groq, xAI, or other OpenAI-compatible APIs.
    
    Requires active billing with the configured provider.
    """

    prompt = build_summary_prompt(
        article,
        max_words=settings.max_words,
        prompt_template=settings.prompt_template,
    )

    for attempt in range(settings.max_retries + 1):
        try:
            response = client.post(
                settings.api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            summary = _extract_summary_text(response.json())
            if not summary:
                LOGGER.warning("Groq devolvio una respuesta vacia para '%s'.", article.title)
                return None

            return _truncate_to_max_words(summary, settings.max_words)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if _should_retry_status(status_code) and attempt < settings.max_retries:
                _sleep_backoff(settings, attempt)
                continue

            LOGGER.warning("No se pudo generar el resumen para '%s': %s", article.title, exc)
            return None
        except httpx.RequestError as exc:
            if attempt < settings.max_retries:
                _sleep_backoff(settings, attempt)
                continue

            LOGGER.warning("No se pudo generar el resumen para '%s': %s", article.title, exc)
            return None

    return None


def _excerpt_fallback_summary(article: Article, max_words: int) -> str | None:
    """Use original content as fallback summary when the provider call fails."""

    content = article.raw_content.strip() or article.title.strip()
    return _truncate_to_max_words(content, max_words) if content else None


def _sleep_backoff(settings: AiSummarySettings, attempt: int) -> None:
    """Apply exponential backoff capped by configured retry maximum."""

    delay = min(settings.retry_base_seconds * (2 ** attempt), settings.retry_max_seconds)
    if delay > 0:
        time.sleep(delay)


def _should_retry_status(status_code: int) -> bool:
    """Return True when the upstream status is likely transient."""

    return status_code in RETRYABLE_STATUS_CODES


def _extract_summary_text(payload: dict) -> str:
    """Read the first assistant message from a Groq chat completion payload."""

    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    return " ".join(str(message.get("content") or "").split())


def _truncate_to_max_words(text: str, max_words: int) -> str:
    """Enforce a hard word limit in case the model overshoots the requested budget."""

    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)

    return " ".join(words[:max_words])

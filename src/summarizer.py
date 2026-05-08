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
        LOGGER.debug(
            f"Resumen omitido: enabled={settings.enabled}, articles={len(articles) if articles else 0}",
            extra={"operation": "summarize_articles", "reason": "disabled_or_empty"}
        )
        return articles

    provider = settings.provider or "placeholder"
    start_time = time.time()
    
    LOGGER.info(
        f"Iniciando resumen de {len(articles)} articulos con proveedor '{provider}'",
        extra={"operation": "summarize_articles", "provider": provider, "article_count": len(articles)}
    )
    
    if provider == "placeholder":
        result = [replace(article, summary=_placeholder_summary(article, settings)) for article in articles]
        elapsed = time.time() - start_time
        LOGGER.info(
            f"Resumen offline completado para {len(result)} articulos",
            extra={"operation": "summarize_articles", "provider": provider, "result_count": len(result), "elapsed_seconds": elapsed}
        )
        return result
    
    # For external providers (Groq, xAI, etc.)
    active_key = api_key or settings.api_key
    if active_key is None:
        LOGGER.info(
            f"Resumen IA con proveedor '{provider}' habilitado pero sin clave efectiva; se omite.",
            extra={"operation": "summarize_articles", "provider": provider, "reason": "missing_api_key"}
        )
        return articles

    own_client = client is None
    http_client = client or httpx.Client(timeout=settings.timeout_seconds)
    summaries_generated = 0
    summaries_failed = 0

    try:
        result = []
        for article in articles:
            summary = generate_summary(article, settings, active_key, client=http_client)
            if summary:
                summaries_generated += 1
                result.append(replace(article, summary=summary))
            else:
                summaries_failed += 1
                fallback = _excerpt_fallback_summary(article, settings.max_words)
                result.append(replace(article, summary=fallback))
        
        elapsed = time.time() - start_time
        LOGGER.info(
            f"Resumen IA completado: {summaries_generated} generados, {summaries_failed} fallback",
            extra={
                "operation": "summarize_articles",
                "provider": provider,
                "total_articles": len(articles),
                "summaries_generated": summaries_generated,
                "summaries_failed": summaries_failed,
                "elapsed_seconds": elapsed,
            }
        )
        return result
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
    
    start_time = time.time()
    article_title_short = article.title[:60]

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
                LOGGER.warning(
                    f"Groq devolvio una respuesta vacia para '{article_title_short}'",
                    extra={"operation": "generate_summary", "article_title": article_title_short, "reason": "empty_response"}
                )
                return None

            elapsed = time.time() - start_time
            LOGGER.debug(
                f"Resumen generado para '{article_title_short}'",
                extra={
                    "operation": "generate_summary",
                    "article_title": article_title_short,
                    "attempt": attempt + 1,
                    "elapsed_seconds": elapsed,
                }
            )
            return _truncate_to_max_words(summary, settings.max_words)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if _should_retry_status(status_code) and attempt < settings.max_retries:
                LOGGER.debug(
                    f"Error HTTP {status_code} para '{article_title_short}', reintentando (intento {attempt + 1}/{settings.max_retries + 1})",
                    extra={
                        "operation": "generate_summary",
                        "article_title": article_title_short,
                        "status_code": status_code,
                        "attempt": attempt + 1,
                    }
                )
                _sleep_backoff(settings, attempt)
                continue

            LOGGER.warning(
                f"No se pudo generar el resumen para '{article_title_short}': {exc}",
                extra={
                    "operation": "generate_summary",
                    "article_title": article_title_short,
                    "error": str(exc),
                    "status_code": status_code if isinstance(exc, httpx.HTTPStatusError) else None,
                }
            )
            return None
        except httpx.RequestError as exc:
            if attempt < settings.max_retries:
                LOGGER.debug(
                    f"Error de red para '{article_title_short}', reintentando (intento {attempt + 1}/{settings.max_retries + 1})",
                    extra={
                        "operation": "generate_summary",
                        "article_title": article_title_short,
                        "attempt": attempt + 1,
                    }
                )
                _sleep_backoff(settings, attempt)
                continue

            LOGGER.warning(
                f"No se pudo generar el resumen para '{article_title_short}': {exc}",
                extra={
                    "operation": "generate_summary",
                    "article_title": article_title_short,
                    "error": str(exc),
                }
            )
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

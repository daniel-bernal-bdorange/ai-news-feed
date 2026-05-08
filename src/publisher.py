"""Publish the weekly digest to a Power Automate HTTP trigger endpoint."""

from __future__ import annotations

import logging
import time
from collections import Counter

import httpx

from .models import Article

logger = logging.getLogger(__name__)

_DEFAULT_RETRIES = 3
_DEFAULT_TIMEOUT = 15.0


def build_digest_payload(articles: list[Article], week_label: str) -> dict:
    """Assemble the JSON payload sent to Power Automate."""

    categories: Counter[str] = Counter()
    for article in articles:
        if article.category:
            categories[article.category] += 1

    return {
        "week": week_label,
        "total_articles": len(articles),
        "categories": dict(categories),
        "articles": [
            {
                "title": a.title,
                "url": a.url,
                "source": a.source_name,
                "category": a.category or "",
                "geo_boost": a.geo_boost,
                "summary": a.summary or "",
            }
            for a in articles
        ],
    }


def publish_digest(
    articles: list[Article],
    week_label: str,
    webhook_url: str,
    *,
    max_retries: int = _DEFAULT_RETRIES,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """POST the digest payload to the Power Automate endpoint with retries.

    Raises RuntimeError if all retry attempts are exhausted.
    """

    payload = build_digest_payload(articles, week_label)

    for attempt in range(1, max_retries + 1):
        try:
            response = httpx.post(webhook_url, json=payload, timeout=timeout)
            response.raise_for_status()
            logger.info("Digest publicado correctamente en el intento %d/%d", attempt, max_retries)
            return
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Error HTTP en intento %d/%d al publicar digest: %s",
                attempt, max_retries, exc,
            )
        except httpx.RequestError as exc:
            logger.warning(
                "Error de red en intento %d/%d al publicar digest: %s",
                attempt, max_retries, exc,
            )

        if attempt < max_retries:
            wait = 2 ** (attempt - 1)  # 1s, 2s, ...
            logger.info("Reintentando en %ds...", wait)
            time.sleep(wait)

    raise RuntimeError(
        f"No se pudo publicar el digest tras {max_retries} intentos."
    )

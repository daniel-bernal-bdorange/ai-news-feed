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

    logger.debug(
        f"Construyendo payload de digest para semana '{week_label}': {len(articles)} articulos",
        extra={
            "operation": "build_digest_payload",
            "week_label": week_label,
            "article_count": len(articles),
            "categories": dict(categories),
        }
    )

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
    start_time = time.time()
    
    logger.info(
        f"Iniciando publicacion de digest para semana '{week_label}': {len(articles)} articulos",
        extra={
            "operation": "publish_digest",
            "week_label": week_label,
            "article_count": len(articles),
            "max_retries": max_retries,
        }
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = httpx.post(webhook_url, json=payload, timeout=timeout)
            response.raise_for_status()
            elapsed = time.time() - start_time
            logger.info(
                f"Digest publicado correctamente en el intento {attempt}/{max_retries}",
                extra={
                    "operation": "publish_digest",
                    "week_label": week_label,
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "elapsed_seconds": elapsed,
                }
            )
            return
        except httpx.HTTPStatusError as exc:
            logger.warning(
                f"Error HTTP en intento {attempt}/{max_retries} al publicar digest: {exc}",
                extra={
                    "operation": "publish_digest",
                    "week_label": week_label,
                    "attempt": attempt,
                    "status_code": exc.response.status_code,
                    "error": str(exc),
                }
            )
        except httpx.RequestError as exc:
            logger.warning(
                f"Error de red en intento {attempt}/{max_retries} al publicar digest: {exc}",
                extra={
                    "operation": "publish_digest",
                    "week_label": week_label,
                    "attempt": attempt,
                    "error": str(exc),
                }
            )

        if attempt < max_retries:
            wait = 2 ** (attempt - 1)  # 1s, 2s, ...
            logger.debug(
                f"Reintentando en {wait}s (intento {attempt + 1}/{max_retries})",
                extra={
                    "operation": "publish_digest",
                    "week_label": week_label,
                    "attempt": attempt,
                    "retry_delay_seconds": wait,
                }
            )
            time.sleep(wait)

    elapsed = time.time() - start_time
    logger.error(
        f"No se pudo publicar el digest tras {max_retries} intentos",
        extra={
            "operation": "publish_digest",
            "week_label": week_label,
            "max_retries": max_retries,
            "elapsed_seconds": elapsed,
        }
    )
    raise RuntimeError(
        f"No se pudo publicar el digest tras {max_retries} intentos."
    )

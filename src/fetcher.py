from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .models import Article, Settings

LOGGER = logging.getLogger(__name__)
NEWSAPI_URL = "https://newsapi.org/v2/everything"
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def fetch_all_articles(
    settings: Settings,
    api_key: str | None = None,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    parser: Any = feedparser.parse,
) -> list[Article]:
    rss_articles = fetch_rss_articles(settings, now=now, parser=parser)
    newsapi_articles = fetch_newsapi_articles(settings, api_key, client=client, now=now)
    combined = deduplicate_articles(rss_articles + newsapi_articles)
    combined.sort(key=lambda article: article.published_date, reverse=True)
    return combined[: settings.schedule.max_articles_total]


def fetch_rss_articles(
    settings: Settings,
    *,
    now: datetime | None = None,
    parser: Any = feedparser.parse,
) -> list[Article]:
    current_time = now or datetime.now(UTC)
    threshold = current_time - timedelta(hours=settings.schedule.lookback_hours)
    articles: list[Article] = []

    for source in settings.sources.rss:
        try:
            parsed_feed = parser(source.url)
        except Exception as exc:
            LOGGER.warning("Fallo al leer el feed %s: %s", source.name, exc)
            continue

        entries = list(parsed_feed.get("entries", []))
        entries.sort(key=lambda entry: _entry_published_date(entry) or datetime.min.replace(tzinfo=UTC), reverse=True)

        added_for_source = 0
        for entry in entries:
            if added_for_source >= settings.schedule.max_articles_per_source:
                break

            published_date = _entry_published_date(entry)
            if published_date is None or published_date < threshold or published_date > current_time:
                continue

            title = (entry.get("title") or "").strip()
            url = (entry.get("link") or "").strip()
            if not title or not url:
                continue

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_name=source.name,
                    published_date=published_date,
                    raw_content=_extract_raw_content(entry),
                    category=source.category,
                )
            )
            added_for_source += 1

    return articles


def fetch_newsapi_articles(
    settings: Settings,
    api_key: str | None,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> list[Article]:
    if not settings.sources.newsapi.enabled:
        return []

    if not api_key:
        LOGGER.info("NewsAPI habilitada pero sin clave; se omite la fuente opcional.")
        return []

    current_time = now or datetime.now(UTC)
    since = current_time - timedelta(hours=settings.schedule.lookback_hours)
    own_client = client is None
    http_client = client or httpx.Client(timeout=10.0)
    articles: list[Article] = []

    try:
        for query in settings.sources.newsapi.queries:
            try:
                response = http_client.get(
                    NEWSAPI_URL,
                    params={
                        "q": query,
                        "from": since.isoformat(),
                        "sortBy": "publishedAt",
                        "language": "en",
                        "pageSize": settings.schedule.max_articles_per_source,
                    },
                    headers={"X-Api-Key": api_key},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                LOGGER.warning("NewsAPI fallo para la query '%s': %s", query, exc)
                continue

            payload = response.json()
            for item in payload.get("articles", []):
                published_at = _parse_iso8601(item.get("publishedAt"))
                if published_at is None:
                    continue

                articles.append(
                    Article(
                        title=(item.get("title") or "").strip(),
                        url=(item.get("url") or "").strip(),
                        source_name=(item.get("source") or {}).get("name", "NewsAPI"),
                        published_date=published_at,
                        raw_content=(item.get("content") or item.get("description") or "").strip(),
                        category="newsapi",
                    )
                )
    finally:
        if own_client:
            http_client.close()

    return [article for article in articles if article.title and article.url]


def deduplicate_articles(
    articles: list[Article],
    *,
    title_similarity_threshold: float = 0.92,
) -> list[Article]:
    unique_articles: list[Article] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []

    for article in sorted(articles, key=lambda item: item.published_date, reverse=True):
        canonical_url = _canonicalize_url(article.url)
        normalized_title = _normalize_title(article.title)

        if canonical_url in seen_urls:
            continue

        if any(_similarity(normalized_title, existing) >= title_similarity_threshold for existing in seen_titles):
            continue

        seen_urls.add(canonical_url)
        seen_titles.append(normalized_title)
        unique_articles.append(article)

    return unique_articles


def _entry_published_date(entry: dict[str, Any]) -> datetime | None:
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time is None:
        return None

    return datetime(
        parsed_time.tm_year,
        parsed_time.tm_mon,
        parsed_time.tm_mday,
        parsed_time.tm_hour,
        parsed_time.tm_min,
        parsed_time.tm_sec,
        tzinfo=UTC,
    )


def _extract_raw_content(entry: dict[str, Any]) -> str:
    content_items = entry.get("content") or []
    if content_items and isinstance(content_items, list):
        value = content_items[0].get("value")
        if value:
            return value.strip()

    return (entry.get("summary") or entry.get("description") or "").strip()


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in TRACKING_QUERY_KEYS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(filtered_query), ""))


def _normalize_title(title: str) -> str:
    sanitized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return " ".join(sanitized.split())


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .models import Article, EditorialSettings, Settings

LOGGER = logging.getLogger(__name__)
NEWSAPI_URL = "https://newsapi.org/v2/everything"
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
TITLE_NOISE_TOKENS = {
    "analysis",
    "ap",
    "associated",
    "bloomberg",
    "exclusive",
    "photos",
    "podcast",
    "press",
    "reuters",
    "update",
    "video",
}


def fetch_all_articles(
    settings: Settings,
    api_key: str | None = None,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    parser: Any = feedparser.parse,
) -> list[Article]:
    """Fetch, merge, and rank articles from all configured sources."""

    rss_articles = fetch_rss_articles(settings, now=now, parser=parser)
    newsapi_articles = fetch_newsapi_articles(settings, api_key, client=client, now=now)
    combined = filter_editorial_articles(rss_articles + newsapi_articles, settings.editorial)
    combined = deduplicate_articles(combined)
    combined.sort(key=lambda article: article.published_date, reverse=True)
    return combined[: settings.schedule.max_articles_total]


def filter_editorial_articles(articles: list[Article], editorial: EditorialSettings) -> list[Article]:
    """Drop articles that fail the editorial inclusion, exclusion, or title rules."""

    return [article for article in articles if _matches_editorial_rules(article, editorial)]


def fetch_rss_articles(
    settings: Settings,
    *,
    now: datetime | None = None,
    parser: Any = feedparser.parse,
) -> list[Article]:
    """Collect recent entries from every configured RSS source."""

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
        # Sort newest first so the per-source cap keeps the most relevant items.
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
    """Fetch optional NewsAPI articles using the same lookback window as RSS."""

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
    """Remove repeated stories by canonical URL and near-duplicate titles."""

    unique_articles: list[Article] = []
    seen_urls: set[str] = set()
    seen_titles: list[tuple[str, set[str]]] = []

    for article in sorted(articles, key=lambda item: item.published_date, reverse=True):
        # URL normalization strips tracking noise so syndicated links collapse reliably.
        canonical_url = _canonicalize_url(article.url)
        normalized_title = _normalize_title(article.title)
        title_tokens = _meaningful_title_tokens(normalized_title)

        if canonical_url in seen_urls:
            continue

        if any(
            _titles_match(
                normalized_title,
                title_tokens,
                existing_title,
                existing_tokens,
                title_similarity_threshold,
            )
            for existing_title, existing_tokens in seen_titles
        ):
            continue

        seen_urls.add(canonical_url)
        seen_titles.append((normalized_title, title_tokens))
        unique_articles.append(article)

    return unique_articles


def _matches_editorial_rules(article: Article, editorial: EditorialSettings) -> bool:
    """Evaluate an article against the configured editorial filters."""

    if len(article.title.strip()) < editorial.min_title_length:
        return False

    searchable_text = _normalize_search_text(f"{article.title} {article.raw_content}")

    if editorial.include_keywords and not any(_keyword_matches(searchable_text, keyword) for keyword in editorial.include_keywords):
        return False

    if editorial.exclude_keywords and any(_keyword_matches(searchable_text, keyword) for keyword in editorial.exclude_keywords):
        return False

    return True


def _entry_published_date(entry: dict[str, Any]) -> datetime | None:
    """Extract a timezone-aware publication date from a parsed feed entry."""

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
    """Prefer full content when present and fall back to summary fields."""

    content_items = entry.get("content") or []
    if content_items and isinstance(content_items, list):
        value = content_items[0].get("value")
        if value:
            return value.strip()

    return (entry.get("summary") or entry.get("description") or "").strip()


def _parse_iso8601(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp into UTC, returning None on invalid input."""

    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _canonicalize_url(url: str) -> str:
    """Normalize URLs so equivalent links compare equal during deduplication."""

    parsed = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.startswith("utm_") and key not in TRACKING_QUERY_KEYS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(filtered_query), ""))


def _normalize_title(title: str) -> str:
    """Reduce title noise before fuzzy title comparison."""

    sanitized = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return " ".join(sanitized.split())


def _normalize_search_text(value: str) -> str:
    """Normalize article text so keyword rules behave consistently."""

    return " ".join(value.lower().split())


def _keyword_matches(searchable_text: str, keyword: str) -> bool:
    """Match configured keywords case-insensitively against normalized article text."""

    normalized_keyword = _normalize_search_text(keyword)
    return bool(normalized_keyword) and normalized_keyword in searchable_text


def _meaningful_title_tokens(title: str) -> set[str]:
    """Drop low-signal attribution tokens before comparing title variants."""

    return {token for token in title.split() if token not in TITLE_NOISE_TOKENS}


def _titles_match(
    left_title: str,
    left_tokens: set[str],
    right_title: str,
    right_tokens: set[str],
    threshold: float,
) -> bool:
    """Treat small syndicated title variants as the same story."""

    if _similarity(left_title, right_title) >= threshold:
        return True

    if not left_tokens or not right_tokens:
        return False

    shared_tokens = left_tokens & right_tokens
    smaller_tokens, larger_tokens = sorted((left_tokens, right_tokens), key=len)

    return len(smaller_tokens) >= 4 and len(shared_tokens) >= 4 and smaller_tokens <= larger_tokens and len(larger_tokens - smaller_tokens) <= 1


def _similarity(left: str, right: str) -> float:
    """Return the similarity ratio used for near-duplicate title detection."""

    return SequenceMatcher(None, left, right).ratio()

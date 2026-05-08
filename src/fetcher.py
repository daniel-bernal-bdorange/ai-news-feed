from __future__ import annotations

from dataclasses import replace
import logging
import re
import time
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

    start_time = time.time()
    
    LOGGER.info("Iniciando obtención de articulos desde múltiples fuentes", extra={"operation": "fetch_all_articles"})
    
    rss_articles = fetch_rss_articles(settings, now=now, parser=parser)
    LOGGER.debug(f"RSS articulos obtenidos: {len(rss_articles)}", extra={"source": "rss", "count": len(rss_articles)})
    
    newsapi_articles = fetch_newsapi_articles(settings, api_key, client=client, now=now)
    LOGGER.debug(f"NewsAPI articulos obtenidos: {len(newsapi_articles)}", extra={"source": "newsapi", "count": len(newsapi_articles)})
    
    combined = rss_articles + newsapi_articles
    LOGGER.debug(f"Articulos combinados: {len(combined)}", extra={"combined_count": len(combined)})
    
    combined = filter_editorial_articles(combined, settings.editorial)
    LOGGER.debug(f"Articulos tras filtro editorial: {len(combined)}", extra={"after_editorial_filter": len(combined)})
    
    combined = deduplicate_articles(combined)
    LOGGER.debug(f"Articulos tras deduplicacion: {len(combined)}", extra={"after_dedup": len(combined)})
    
    result = rank_articles_for_digest(combined, settings)
    
    elapsed = time.time() - start_time
    LOGGER.info(
        f"Obtención completada: {len(result)} articulos finales",
        extra={
            "operation": "fetch_all_articles",
            "rss_count": len(rss_articles),
            "newsapi_count": len(newsapi_articles),
            "final_count": len(result),
            "elapsed_seconds": elapsed,
        }
    )
    
    return result


def filter_editorial_articles(articles: list[Article], editorial: EditorialSettings) -> list[Article]:
    """Drop articles that fail the editorial inclusion, exclusion, or title rules."""

    start_time = time.time()
    filtered = [article for article in articles if _matches_editorial_rules(article, editorial)]
    elapsed = time.time() - start_time
    
    LOGGER.info(
        f"Filtro editorial: {len(filtered)} articulos validos de {len(articles)} totales",
        extra={
            "operation": "filter_editorial_articles",
            "input_count": len(articles),
            "output_count": len(filtered),
            "rejected_count": len(articles) - len(filtered),
            "elapsed_seconds": elapsed,
        }
    )
    
    return filtered


def rank_articles_for_digest(articles: list[Article], settings: Settings) -> list[Article]:
    """Return the final digest shortlist ordered by priority and constrained by ranking caps."""

    start_time = time.time()
    
    ranked_articles = sorted(
        articles,
        key=lambda article: _article_rank_key(article, settings.editorial),
        reverse=True,
    )
    selected: list[Article] = []
    source_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}

    for article in ranked_articles:
        if _reaches_ranking_limit(article.source_name, source_counts, settings.ranking.max_articles_per_source):
            continue

        if article.category and _reaches_ranking_limit(
            article.category,
            category_counts,
            settings.ranking.max_articles_per_category,
        ):
            continue

        selected.append(article)
        source_counts[article.source_name] = source_counts.get(article.source_name, 0) + 1
        if article.category:
            category_counts[article.category] = category_counts.get(article.category, 0) + 1

        if len(selected) >= settings.schedule.max_articles_total:
            break

    elapsed = time.time() - start_time
    LOGGER.info(
        f"Ranking completado: {len(selected)} articulos seleccionados de {len(articles)} candidatos",
        extra={
            "operation": "rank_articles_for_digest",
            "input_count": len(articles),
            "output_count": len(selected),
            "source_counts": dict(source_counts),
            "category_counts": dict(category_counts),
            "elapsed_seconds": elapsed,
        }
    )

    return selected


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
    
    LOGGER.info(
        f"Iniciando obtención de fuentes RSS: {len(settings.sources.rss)} fuentes configuradas",
        extra={"operation": "fetch_rss_articles", "source_count": len(settings.sources.rss)}
    )

    for source in settings.sources.rss:
        try:
            parsed_feed = parser(source.url)
        except Exception as exc:
            LOGGER.warning(
                f"Fallo al leer el feed {source.name}: {exc}",
                extra={"source": source.name, "url": source.url, "error": str(exc)}
            )
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
                _with_geo_boost(
                    Article(
                        title=title,
                        url=url,
                        source_name=source.name,
                        published_date=published_date,
                        raw_content=_extract_raw_content(entry),
                        category=source.category,
                        fetched_at=current_time,
                    ),
                    settings.editorial,
                )
            )
            added_for_source += 1
        
        LOGGER.debug(
            f"RSS fuente {source.name}: {added_for_source} articulos",
            extra={"source": source.name, "articles_added": added_for_source}
        )

    LOGGER.info(
        f"RSS obtencion completada: {len(articles)} articulos totales",
        extra={"operation": "fetch_rss_articles", "total_articles": len(articles)}
    )
    
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
        LOGGER.debug("NewsAPI deshabilitada", extra={"source": "newsapi"})
        return []

    if not api_key:
        LOGGER.info(
            "NewsAPI habilitada pero sin clave; se omite la fuente opcional.",
            extra={"source": "newsapi", "reason": "missing_api_key"}
        )
        return []

    current_time = now or datetime.now(UTC)
    since = current_time - timedelta(hours=settings.schedule.lookback_hours)
    own_client = client is None
    http_client = client or httpx.Client(timeout=10.0)
    articles: list[Article] = []
    
    LOGGER.info(
        f"Iniciando obtención NewsAPI: {len(settings.sources.newsapi.queries)} queries",
        extra={"operation": "fetch_newsapi_articles", "query_count": len(settings.sources.newsapi.queries)}
    )

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
                LOGGER.warning(
                    f"NewsAPI fallo para la query '{query}': {exc}",
                    extra={"source": "newsapi", "query": query, "error": str(exc)}
                )
                continue

            payload = response.json()
            articles_in_response = len(payload.get("articles", []))
            LOGGER.debug(
                f"NewsAPI query '{query}': {articles_in_response} articulos",
                extra={"query": query, "articles_count": articles_in_response}
            )
            
            for item in payload.get("articles", []):
                published_at = _parse_iso8601(item.get("publishedAt"))
                if published_at is None:
                    continue

                articles.append(
                    _with_geo_boost(
                        Article(
                            title=(item.get("title") or "").strip(),
                            url=(item.get("url") or "").strip(),
                            source_name=(item.get("source") or {}).get("name", "NewsAPI"),
                            published_date=published_at,
                            raw_content=(item.get("content") or item.get("description") or "").strip(),
                            category="newsapi",
                            fetched_at=current_time,
                        ),
                        settings.editorial,
                    )
                )
    finally:
        if own_client:
            http_client.close()

    result = [article for article in articles if article.title and article.url]
    LOGGER.info(
        f"NewsAPI obtencion completada: {len(result)} articulos finales",
        extra={"operation": "fetch_newsapi_articles", "total_articles": len(result)}
    )
    
    return result


def deduplicate_articles(
    articles: list[Article],
    *,
    title_similarity_threshold: float = 0.92,
) -> list[Article]:
    """Remove repeated stories by canonical URL and near-duplicate titles."""

    start_time = time.time()
    unique_articles: list[Article] = []
    seen_urls: dict[str, int] = {}
    seen_titles: list[tuple[str, set[str], int]] = []
    duplicates_removed = 0

    for article in sorted(articles, key=lambda item: item.published_date, reverse=True):
        # URL normalization strips tracking noise so syndicated links collapse reliably.
        canonical_url = _canonicalize_url(article.url)
        normalized_title = _normalize_title(article.title)
        title_tokens = _meaningful_title_tokens(normalized_title)

        existing_index = seen_urls.get(canonical_url)
        if existing_index is not None:
            unique_articles[existing_index] = _merge_article_signals(unique_articles[existing_index], article)
            duplicates_removed += 1
            continue

        title_match_index = next(
            (
                existing_index
                for existing_title, existing_tokens, existing_index in seen_titles
                if _titles_match(
                    normalized_title,
                    title_tokens,
                    existing_title,
                    existing_tokens,
                    title_similarity_threshold,
                )
            ),
            None,
        )
        if title_match_index is not None:
            unique_articles[title_match_index] = _merge_article_signals(unique_articles[title_match_index], article)
            duplicates_removed += 1
            continue

        seen_urls[canonical_url] = len(unique_articles)
        seen_titles.append((normalized_title, title_tokens, len(unique_articles)))
        unique_articles.append(article)

    elapsed = time.time() - start_time
    LOGGER.info(
        f"Deduplicacion completada: {len(unique_articles)} articulos unicos, {duplicates_removed} duplicados removidos",
        extra={
            "operation": "deduplicate_articles",
            "input_count": len(articles),
            "output_count": len(unique_articles),
            "duplicates_removed": duplicates_removed,
            "elapsed_seconds": elapsed,
        }
    )

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


def _article_rank_key(article: Article, editorial: EditorialSettings) -> tuple[float, datetime, str, str]:
    """Sort geo-prioritized articles first, then newer items, with deterministic ties."""

    relevance_score = max(article.relevance_score, _geo_priority_multiplier(article, editorial))

    return (
        relevance_score,
        article.published_date,
        article.category or "",
        article.source_name.casefold(),
    )


def _geo_priority_multiplier(article: Article, editorial: EditorialSettings) -> float:
    """Return the configured boost for Spain and EU-relevant articles."""

    geo_priority = editorial.geo_priority
    if _has_geo_priority(article, editorial):
        return geo_priority.boost_score

    return 1.0


def _with_geo_boost(article: Article, editorial: EditorialSettings) -> Article:
    """Persist the geo-priority match on the article so downstream stages can reuse it."""

    geo_boost = _has_geo_priority(article, editorial)
    relevance_score = max(article.relevance_score, editorial.geo_priority.boost_score if geo_boost else 1.0)
    if article.geo_boost == geo_boost and article.relevance_score == relevance_score:
        return article

    return replace(article, geo_boost=geo_boost, relevance_score=relevance_score)


def _has_geo_priority(article: Article, editorial: EditorialSettings) -> bool:
    """Check whether an article is relevant to Spain or EU regulation."""

    geo_priority = editorial.geo_priority
    if not geo_priority.enabled:
        return article.geo_boost

    if article.geo_boost:
        return True

    searchable_text = _normalize_search_text(f"{article.title} {article.raw_content}")
    return any(_keyword_matches(searchable_text, keyword) for keyword in geo_priority.boost_keywords)


def _merge_article_signals(primary: Article, duplicate: Article) -> Article:
    """Keep the chosen canonical article while preserving positive signals from duplicates."""

    return replace(
        primary,
        geo_boost=primary.geo_boost or duplicate.geo_boost,
        fetched_at=_newest_datetime(primary.fetched_at, duplicate.fetched_at),
        relevance_score=max(primary.relevance_score, duplicate.relevance_score),
        summary=primary.summary or duplicate.summary,
        selected=primary.selected or duplicate.selected,
        id=primary.id or duplicate.id,
    )


def _newest_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    """Return the newest available timestamp, tolerating missing fetched dates."""

    if left is None:
        return right

    if right is None:
        return left

    return max(left, right)


def _reaches_ranking_limit(key: str, counts: dict[str, int], limit: int | None) -> bool:
    """Report whether a ranking bucket already consumed its configured quota."""

    if limit is None:
        return False

    return counts.get(key, 0) >= limit

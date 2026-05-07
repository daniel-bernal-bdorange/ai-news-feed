from __future__ import annotations

from datetime import UTC, datetime
from time import gmtime

import httpx

from src.fetcher import deduplicate_articles, fetch_all_articles, fetch_newsapi_articles, fetch_rss_articles
from src.models import Article, EditorialSettings, NewsApiSettings, RssSourceConfig, ScheduleSettings, Settings, SourceSettings


def build_settings(
    *,
    newsapi_enabled: bool = True,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    min_title_length: int = 0,
    max_articles_total: int = 5,
    max_articles_per_source: int = 2,
) -> Settings:
    """Build a compact settings object for ingestion-focused tests."""

    return Settings(
        schedule=ScheduleSettings(
            lookback_hours=24,
            max_articles_total=max_articles_total,
            max_articles_per_source=max_articles_per_source,
        ),
        sources=SourceSettings(
            rss=[RssSourceConfig(name="Feed A", url="https://example.com/rss", category="ai")],
            newsapi=NewsApiSettings(enabled=newsapi_enabled, queries=["orange ai"]),
        ),
        editorial=EditorialSettings(
            include_keywords=list(include_keywords or []),
            exclude_keywords=list(exclude_keywords or []),
            min_title_length=min_title_length,
        ),
    )


def test_fetch_rss_articles_filters_by_window_and_source_limit() -> None:
    """RSS ingestion should keep only recent entries within the per-source cap."""

    now = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    settings = build_settings(newsapi_enabled=False)

    def parser(_: str) -> dict[str, object]:
        return {
            "entries": [
                _entry("Fresh 1", "https://example.com/fresh-1", now),
                _entry("Fresh 2", "https://example.com/fresh-2", now.replace(hour=6)),
                _entry("Fresh 3", "https://example.com/fresh-3", now.replace(hour=4)),
                _entry("Old", "https://example.com/old", now.replace(day=5)),
            ]
        }

    articles = fetch_rss_articles(settings, now=now, parser=parser)

    assert [article.title for article in articles] == ["Fresh 1", "Fresh 2"]


def test_fetch_newsapi_articles_skips_missing_api_key() -> None:
    """NewsAPI ingestion should be a no-op when no API key is available."""

    settings = build_settings(newsapi_enabled=True)

    articles = fetch_newsapi_articles(settings, api_key=None)

    assert articles == []


def test_fetch_all_articles_deduplicates_url_and_similar_titles() -> None:
    """Combined ingestion should collapse duplicate stories across source types."""

    now = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    settings = build_settings(newsapi_enabled=True)

    def parser(_: str) -> dict[str, object]:
        return {
            "entries": [
                _entry("Orange launches AI network platform", "https://example.com/story", now),
            ]
        }

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "title": "Orange launches AI network platform today",
                        "url": "https://example.com/story?utm_source=rss",
                        "publishedAt": "2026-05-07T07:30:00Z",
                        "source": {"name": "NewsAPI"},
                        "description": "Duplicated story through NewsAPI.",
                    }
                ]
            },
        )
    )
    client = httpx.Client(transport=transport)

    articles = fetch_all_articles(settings, api_key="secret", client=client, now=now, parser=parser)

    assert len(articles) == 1
    assert articles[0].title == "Orange launches AI network platform"


def test_fetch_all_articles_continues_with_rss_when_newsapi_fails() -> None:
    """Combined ingestion should still return RSS items when NewsAPI errors out."""

    now = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    settings = build_settings(newsapi_enabled=True)

    def parser(_: str) -> dict[str, object]:
        return {
            "entries": [
                _entry("RSS survives NewsAPI outage", "https://example.com/rss-only", now),
            ]
        }

    transport = httpx.MockTransport(lambda request: httpx.Response(429, request=request, json={"status": "error"}))
    client = httpx.Client(transport=transport)

    articles = fetch_all_articles(settings, api_key="secret", client=client, now=now, parser=parser)

    assert len(articles) == 1
    assert articles[0].title == "RSS survives NewsAPI outage"


def test_fetch_all_articles_applies_editorial_filters_before_ranking() -> None:
    """Editorial rules should remove excluded items before the ranked cap is applied."""

    now = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    settings = build_settings(
        newsapi_enabled=False,
        include_keywords=["orange"],
        exclude_keywords=["podcast"],
        min_title_length=20,
        max_articles_total=1,
        max_articles_per_source=3,
    )

    def parser(_: str) -> dict[str, object]:
        return {
            "entries": [
                _entry("Orange AI podcast recap", "https://example.com/excluded", now),
                _entry("Orange AI", "https://example.com/too-short", now.replace(hour=7)),
                _entry(
                    "Orange launches enterprise AI platform",
                    "https://example.com/included",
                    now.replace(hour=6),
                ),
            ]
        }

    articles = fetch_all_articles(settings, api_key=None, now=now, parser=parser)

    assert [article.title for article in articles] == ["Orange launches enterprise AI platform"]


def test_deduplicate_articles_preserves_most_recent_unique_items() -> None:
    """Deduplication should keep the newest version of repeated content."""

    older = Article(
        title="Shared Story",
        url="https://example.com/shared",
        source_name="Feed A",
        published_date=datetime(2026, 5, 7, 6, 0, tzinfo=UTC),
        raw_content="Older",
        category="ai",
    )
    newer = Article(
        title="Shared Story Updated",
        url="https://example.com/shared?utm_source=rss",
        source_name="Feed B",
        published_date=datetime(2026, 5, 7, 7, 0, tzinfo=UTC),
        raw_content="Newer",
        category="ai",
    )
    unique = Article(
        title="Completely different article",
        url="https://example.com/unique",
        source_name="Feed C",
        published_date=datetime(2026, 5, 7, 5, 0, tzinfo=UTC),
        raw_content="Unique",
        category="telco",
    )

    articles = deduplicate_articles([older, newer, unique], title_similarity_threshold=0.8)

    assert [article.title for article in articles] == ["Shared Story Updated", "Completely different article"]


def test_deduplicate_articles_collapses_syndicated_title_variants() -> None:
    """Title variants with wire suffixes or one extra keyword should still collapse."""

    older = Article(
        title="Orange launches AI network platform",
        url="https://feed-a.example.com/story",
        source_name="Feed A",
        published_date=datetime(2026, 5, 7, 6, 0, tzinfo=UTC),
        raw_content="Older",
        category="ai",
    )
    middle = Article(
        title="Orange launches AI network platform - Reuters",
        url="https://feed-b.example.com/story",
        source_name="Feed B",
        published_date=datetime(2026, 5, 7, 7, 0, tzinfo=UTC),
        raw_content="Middle",
        category="ai",
    )
    newer = Article(
        title="Orange launches AI-powered network platform",
        url="https://feed-c.example.com/story",
        source_name="Feed C",
        published_date=datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        raw_content="Newer",
        category="ai",
    )
    unique = Article(
        title="Independent telco cloud update",
        url="https://feed-d.example.com/story",
        source_name="Feed D",
        published_date=datetime(2026, 5, 7, 5, 0, tzinfo=UTC),
        raw_content="Unique",
        category="telco",
    )

    articles = deduplicate_articles([older, middle, newer, unique])

    assert [article.title for article in articles] == [
        "Orange launches AI-powered network platform",
        "Independent telco cloud update",
    ]


def _entry(title: str, url: str, published_date: datetime) -> dict[str, object]:
    """Create a feedparser-like entry payload for deterministic RSS tests."""

    return {
        "title": title,
        "link": url,
        "summary": f"Summary for {title}",
        "published_parsed": gmtime(published_date.timestamp()),
    }
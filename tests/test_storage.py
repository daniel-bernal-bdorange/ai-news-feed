from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.models import Article
from src.storage import load_weekly_store, persist_weekly_articles, reset_weekly_store


def test_persist_weekly_articles_creates_expected_weekly_schema(tmp_path: Path) -> None:
    """Weekly persistence should create the expected envelope and article fields."""

    now = datetime(2026, 5, 7, 8, 3, 21, tzinfo=UTC)
    path = tmp_path / "articles_week.json"

    store = persist_weekly_articles(
        [
            Article(
                title="Spain enterprise AI update",
                url="https://example.com/spain-ai",
                source_name="Feed A",
                published_date=datetime(2026, 5, 7, 6, 30, tzinfo=UTC),
                fetched_at=now,
                raw_content="Spain and enterprise AI",
                category="ai",
                geo_boost=True,
                relevance_score=1.5,
            )
        ],
        path,
        now=now,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["week_start"] == "2026-05-04"
    assert payload["week_end"] == "2026-05-10"
    assert payload["last_updated"] == "2026-05-07T08:03:21Z"
    assert payload["articles"][0]["geo_boost"] is True
    assert payload["articles"][0]["relevance_score"] == 1.5
    assert payload["articles"][0]["selected"] is False
    assert len(payload["articles"][0]["id"]) == 12
    assert store.articles[0].title == "Spain enterprise AI update"


def test_persist_weekly_articles_merges_with_existing_week_and_keeps_unique_urls(tmp_path: Path) -> None:
    """Weekly persistence should deduplicate against already stored articles."""

    path = tmp_path / "articles_week.json"
    first_run = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    second_run = datetime(2026, 5, 7, 10, 0, tzinfo=UTC)

    persist_weekly_articles(
        [
            Article(
                title="Orange AI launch",
                url="https://example.com/story",
                source_name="Feed A",
                published_date=datetime(2026, 5, 7, 7, 0, tzinfo=UTC),
                fetched_at=first_run,
                raw_content="Initial content",
                category="orange",
                geo_boost=False,
                relevance_score=1.0,
            )
        ],
        path,
        now=first_run,
    )

    store = persist_weekly_articles(
        [
            Article(
                title="Orange AI launch in Spain",
                url="https://example.com/story?utm_source=newsapi",
                source_name="Feed B",
                published_date=datetime(2026, 5, 7, 9, 0, tzinfo=UTC),
                fetched_at=second_run,
                raw_content="Duplicate with geo context",
                category="orange",
                geo_boost=True,
                relevance_score=1.5,
            ),
            Article(
                title="Unique telco article",
                url="https://example.com/unique",
                source_name="Feed C",
                published_date=datetime(2026, 5, 7, 8, 30, tzinfo=UTC),
                fetched_at=second_run,
                raw_content="Unique content",
                category="telco",
                relevance_score=1.0,
            ),
        ],
        path,
        now=second_run,
    )

    assert len(store.articles) == 2
    assert store.articles[0].url == "https://example.com/story?utm_source=newsapi"
    assert store.articles[0].geo_boost is True
    assert store.articles[0].relevance_score == 1.5
    assert store.articles[0].fetched_at == second_run


def test_load_weekly_store_resets_when_the_week_rolls_over(tmp_path: Path) -> None:
    """A persisted file from a previous week should not leak into the new accumulator."""

    path = tmp_path / "articles_week.json"
    reset_weekly_store(path, now=datetime(2026, 5, 7, 8, 0, tzinfo=UTC))

    store = load_weekly_store(path, now=datetime(2026, 5, 11, 8, 0, tzinfo=UTC))

    assert store.week_start.isoformat() == "2026-05-11"
    assert store.week_end.isoformat() == "2026-05-17"
    assert store.articles == []
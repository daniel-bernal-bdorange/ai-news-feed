from __future__ import annotations

from datetime import UTC, date, datetime

import main
from src.models import Article, Settings
from src.storage import WeeklyArticleStore


def _sample_article(title: str) -> Article:
    return Article(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-').lower()}",
        source_name="Feed",
        published_date=datetime(2026, 5, 8, 8, 0, tzinfo=UTC),
        raw_content=f"{title} content",
        category="tech",
    )


def test_main_daily_mode_skips_publish(monkeypatch) -> None:
    """Daily mode should not call publisher even when webhook URL is configured."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "load_settings", lambda: Settings())
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: [_sample_article("Daily")])
    monkeypatch.setattr(main, "summarize_articles", lambda articles, *_args, **_kwargs: articles)

    store = WeeklyArticleStore(
        week_start=date(2026, 5, 4),
        week_end=date(2026, 5, 10),
        last_updated=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
        articles=[_sample_article("Daily")],
    )
    monkeypatch.setattr(main, "persist_weekly_articles", lambda *_args, **_kwargs: store)

    publish_calls: list[tuple] = []
    monkeypatch.setattr(main, "publish_digest", lambda *args, **_kwargs: publish_calls.append((args, _kwargs)))
    monkeypatch.setenv("POWER_AUTOMATE_URL", "https://example.com/hook")

    main.main(["--mode", "daily"])

    assert publish_calls == []


def test_main_weekly_mode_publishes_digest(monkeypatch) -> None:
    """Weekly mode should publish digest when webhook URL is available."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "load_settings", lambda: Settings())
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: [_sample_article("Weekly")])
    monkeypatch.setattr(main, "summarize_articles", lambda articles, *_args, **_kwargs: articles)

    persisted_articles: list[list[Article]] = []

    def fake_persist(articles, *_args, **_kwargs) -> WeeklyArticleStore:
        persisted_articles.append(list(articles))
        return WeeklyArticleStore(
            week_start=date(2026, 5, 4),
            week_end=date(2026, 5, 10),
            last_updated=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            articles=list(articles),
        )

    monkeypatch.setattr(main, "persist_weekly_articles", fake_persist)

    published: list[tuple[list[Article], str, str]] = []

    def fake_publish(articles: list[Article], week_label: str, webhook_url: str) -> None:
        published.append((articles, week_label, webhook_url))

    monkeypatch.setattr(main, "publish_digest", fake_publish)
    monkeypatch.setenv("POWER_AUTOMATE_URL", "https://example.com/hook")

    main.main(["--mode", "weekly"])

    assert len(persisted_articles) == 2
    assert len(published) == 1
    assert published[0][1] == "2026-05-04 / 2026-05-10"
    assert published[0][2] == "https://example.com/hook"

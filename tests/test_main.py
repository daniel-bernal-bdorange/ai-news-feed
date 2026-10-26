from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from time import perf_counter

import main
from src.models import Article, ScheduleSettings, Settings
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


def test_main_daily_mode_skips_publish(monkeypatch, capsys) -> None:
    """Daily mode should not call publisher even when webhook URL is configured."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "load_settings", lambda: Settings())
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: [_sample_article("Daily")])
    monkeypatch.setattr(main, "fetch_trending_topics", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "summarize_articles", lambda articles, *_args, **_kwargs: articles)
    monkeypatch.setattr(main, "apply_trending_boost", lambda articles, *_args, **_kwargs: articles)

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

    main.main(["--mode", "daily", "--show-scores"])

    output = capsys.readouterr().out

    assert publish_calls == []
    assert "[1.00]" in output
    assert "[Feed] Daily" in output


def test_main_weekly_mode_publishes_digest(monkeypatch) -> None:
    """Weekly mode should publish digest when webhook URL is available."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "load_settings", lambda: Settings())
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: [_sample_article("Weekly")])
    monkeypatch.setattr(main, "fetch_trending_topics", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "summarize_articles", lambda articles, *_args, **_kwargs: articles)
    monkeypatch.setattr(main, "apply_trending_boost", lambda articles, *_args, **_kwargs: articles)

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

    start = perf_counter()
    main.main(["--mode", "weekly"])
    elapsed_seconds = perf_counter() - start

    assert len(persisted_articles) == 2
    assert len(published) == 1
    assert published[0][1] == "2026-05-04 / 2026-05-10"
    assert published[0][2] == "https://example.com/hook"
    assert elapsed_seconds < 1.0


def test_main_reranks_articles_after_summarization(monkeypatch) -> None:
    """The final order should use the post-summary relevance score."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "load_settings", lambda: Settings())
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)

    source_articles = [_sample_article("Low priority"), _sample_article("High priority")]
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: list(source_articles))
    monkeypatch.setattr(main, "fetch_trending_topics", lambda *_args, **_kwargs: [])

    def fake_summarize(input_articles, *_args, **_kwargs):
        return [
            replace(article, relevance_score=1.0 if article.title == "Low priority" else 5.0)
            for article in input_articles
        ]

    monkeypatch.setattr(main, "summarize_articles", fake_summarize)
    monkeypatch.setattr(main, "apply_trending_boost", lambda articles, *_args, **_kwargs: articles)

    persisted_articles: list[list[Article]] = []

    def fake_persist(input_articles, *_args, **_kwargs) -> WeeklyArticleStore:
        persisted_articles.append(list(input_articles))
        return WeeklyArticleStore(
            week_start=date(2026, 5, 4),
            week_end=date(2026, 5, 10),
            last_updated=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            articles=list(input_articles),
        )

    monkeypatch.setattr(main, "persist_weekly_articles", fake_persist)

    published: list[list[Article]] = []
    monkeypatch.setattr(main, "publish_digest", lambda input_articles, *_args, **_kwargs: published.append(list(input_articles)))
    monkeypatch.setenv("POWER_AUTOMATE_URL", "https://example.com/hook")

    main.main(["--mode", "weekly"])

    assert len(persisted_articles) == 2
    assert [article.title for article in published[0]] == ["High priority", "Low priority"]


def test_main_applies_trending_boost_before_final_ranking(monkeypatch) -> None:
    """Trending topics should influence final ordering before persistence and publish."""

    from src.models import TrendingSettings, TrendingTopic

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)

    settings = Settings(trending=TrendingSettings(enabled=True, seed_queries=["spain"]))
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    source_articles = [
        _sample_article("Generic item"),
        _sample_article("Spain AI item"),
    ]
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: list(source_articles))
    monkeypatch.setattr(main, "fetch_trending_topics", lambda *_args, **_kwargs: [TrendingTopic(query="spain", article_count=10)])

    def fake_summarize(input_articles, *_args, **_kwargs):
        return [replace(article, relevance_score=1.0) for article in input_articles]

    monkeypatch.setattr(main, "summarize_articles", fake_summarize)

    persisted_articles: list[list[Article]] = []

    def fake_persist(input_articles, *_args, **_kwargs) -> WeeklyArticleStore:
        persisted_articles.append(list(input_articles))
        return WeeklyArticleStore(
            week_start=date(2026, 5, 4),
            week_end=date(2026, 5, 10),
            last_updated=datetime(2026, 5, 8, 9, 0, tzinfo=UTC),
            articles=list(input_articles),
        )

    monkeypatch.setattr(main, "persist_weekly_articles", fake_persist)

    published: list[list[Article]] = []
    monkeypatch.setattr(main, "publish_digest", lambda input_articles, *_args, **_kwargs: published.append(list(input_articles)))
    monkeypatch.setenv("POWER_AUTOMATE_URL", "https://example.com/hook")

    main.main(["--mode", "weekly"])

    assert len(persisted_articles) == 2
    assert [article.title for article in published[0]] == ["Spain AI item", "Generic item"]


def test_main_weekly_digest_caps_a_larger_accumulated_store(monkeypatch) -> None:
    """The weekly digest should publish only the configured shortlist from the full store."""

    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    settings = Settings(schedule=ScheduleSettings(max_articles_total=4))
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "validate_secrets", lambda _settings: None)
    monkeypatch.setattr(main, "fetch_all_articles", lambda *_args, **_kwargs: [_sample_article("Today")])
    monkeypatch.setattr(main, "fetch_trending_topics", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "summarize_articles", lambda articles, *_args, **_kwargs: articles)
    monkeypatch.setattr(main, "apply_trending_boost", lambda articles, *_args, **_kwargs: articles)

    accumulated_articles = [_sample_article(f"Weekly {index}") for index in range(15)]

    def fake_persist(_articles, *_args, **_kwargs) -> WeeklyArticleStore:
        return WeeklyArticleStore(
            week_start=date(2026, 10, 19),
            week_end=date(2026, 10, 25),
            last_updated=datetime(2026, 10, 23, 9, 0, tzinfo=UTC),
            articles=accumulated_articles,
        )

    monkeypatch.setattr(main, "persist_weekly_articles", fake_persist)

    published: list[list[Article]] = []
    monkeypatch.setattr(main, "publish_digest", lambda articles, *_args, **_kwargs: published.append(list(articles)))
    monkeypatch.setenv("POWER_AUTOMATE_URL", "https://example.com/hook")

    main.main(["--mode", "weekly"])

    assert len(accumulated_articles) == 15
    assert len(published) == 1
    assert len(published[0]) == 4

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

from .fetcher import deduplicate_articles
from .models import Article

DEFAULT_ARTICLE_STORE_PATH = Path("data/articles_week.json")


@dataclass(frozen=True)
class WeeklyArticleStore:
    """Current-week article accumulator persisted inside the repository."""

    week_start: date
    week_end: date
    last_updated: datetime
    articles: list[Article]


def load_weekly_store(
    path: str | Path = DEFAULT_ARTICLE_STORE_PATH,
    *,
    now: datetime | None = None,
) -> WeeklyArticleStore:
    """Load the current weekly store, resetting transparently when the week changed."""

    store_path = Path(path)
    current_time = _current_time(now)
    week_start, week_end = _week_window(current_time)

    if not store_path.exists():
        return WeeklyArticleStore(week_start=week_start, week_end=week_end, last_updated=current_time, articles=[])

    payload = json.loads(store_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Weekly storage payload must be a JSON object: {store_path}")

    stored_start = _parse_date(payload.get("week_start"))
    stored_end = _parse_date(payload.get("week_end"))
    if stored_start != week_start or stored_end != week_end:
        return WeeklyArticleStore(week_start=week_start, week_end=week_end, last_updated=current_time, articles=[])

    articles_payload = payload.get("articles", [])
    if not isinstance(articles_payload, list):
        raise ValueError(f"Weekly storage articles must be a JSON array: {store_path}")

    return WeeklyArticleStore(
        week_start=week_start,
        week_end=week_end,
        last_updated=_parse_datetime(payload.get("last_updated")) or current_time,
        articles=[_article_from_dict(item) for item in articles_payload if isinstance(item, dict)],
    )


def persist_weekly_articles(
    articles: list[Article],
    path: str | Path = DEFAULT_ARTICLE_STORE_PATH,
    *,
    now: datetime | None = None,
) -> WeeklyArticleStore:
    """Merge newly fetched articles into the current week and persist them atomically."""

    current_time = _current_time(now)
    current_store = load_weekly_store(path, now=current_time)
    merged_articles = deduplicate_articles([*current_store.articles, *articles])
    updated_store = WeeklyArticleStore(
        week_start=current_store.week_start,
        week_end=current_store.week_end,
        last_updated=current_time,
        articles=merged_articles,
    )
    save_weekly_store(updated_store, path)
    return updated_store


def reset_weekly_store(
    path: str | Path = DEFAULT_ARTICLE_STORE_PATH,
    *,
    now: datetime | None = None,
) -> WeeklyArticleStore:
    """Reset the weekly store to an empty envelope for the current week."""

    current_time = _current_time(now)
    week_start, week_end = _week_window(current_time)
    store = WeeklyArticleStore(week_start=week_start, week_end=week_end, last_updated=current_time, articles=[])
    save_weekly_store(store, path)
    return store


def save_weekly_store(store: WeeklyArticleStore, path: str | Path = DEFAULT_ARTICLE_STORE_PATH) -> None:
    """Write the weekly store atomically so readers never observe a partial file."""

    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "week_start": store.week_start.isoformat(),
        "week_end": store.week_end.isoformat(),
        "last_updated": _format_datetime(store.last_updated),
        "articles": [_article_to_dict(article, store.last_updated) for article in store.articles],
    }
    tmp_path = store_path.with_suffix(f"{store_path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(store_path)


def _article_to_dict(article: Article, fallback_fetched_at: datetime) -> dict[str, Any]:
    """Map the in-memory article model into the persisted weekly JSON schema."""

    fetched_at = article.fetched_at or fallback_fetched_at
    return {
        "id": article.id or _build_article_id(article.url),
        "url": article.url,
        "title": article.title,
        "source_name": article.source_name,
        "category": article.category,
        "published_at": _format_datetime(article.published_date),
        "fetched_at": _format_datetime(fetched_at),
        "raw_content": article.raw_content,
        "relevance_score": article.relevance_score,
        "geo_boost": article.geo_boost,
        "summary": article.summary,
        "selected": article.selected,
    }


def _article_from_dict(payload: dict[str, Any]) -> Article:
    """Rehydrate a persisted article back into the shared in-memory model."""

    return Article(
        id=payload.get("id") or _build_article_id(str(payload.get("url", ""))),
        url=str(payload.get("url", "")),
        title=str(payload.get("title", "")),
        source_name=str(payload.get("source_name", "")),
        category=payload.get("category"),
        published_date=_parse_datetime(payload.get("published_at")) or datetime.now(UTC),
        fetched_at=_parse_datetime(payload.get("fetched_at")),
        raw_content=str(payload.get("raw_content", "")),
        relevance_score=float(payload.get("relevance_score", 1.0)),
        geo_boost=bool(payload.get("geo_boost", False)),
        summary=payload.get("summary"),
        selected=bool(payload.get("selected", False)),
    )


def _build_article_id(url: str) -> str:
    """Build a stable short identifier from the article URL."""

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


def _current_time(now: datetime | None) -> datetime:
    """Return the current UTC time, keeping tests deterministic when needed."""

    return (now or datetime.now(UTC)).astimezone(UTC)


def _week_window(current_time: datetime) -> tuple[date, date]:
    """Return the Monday-Sunday window for the provided timestamp."""

    week_start = current_time.date() - timedelta(days=current_time.weekday())
    return week_start, week_start + timedelta(days=6)


def _format_datetime(value: datetime) -> str:
    """Serialize datetimes in a compact UTC ISO 8601 form."""

    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any) -> datetime | None:
    """Parse persisted ISO timestamps back into timezone-aware UTC datetimes."""

    if not value or not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    """Parse persisted week boundary dates."""

    if not value or not isinstance(value, str):
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
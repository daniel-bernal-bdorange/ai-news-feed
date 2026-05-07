from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Article:
    """Normalized article representation shared across all ingestion sources."""

    title: str
    url: str
    source_name: str
    published_date: datetime
    raw_content: str
    category: str | None = None


@dataclass(frozen=True)
class RssSourceConfig:
    """Configuration for a single RSS feed source."""

    name: str
    url: str
    category: str


@dataclass(frozen=True)
class NewsApiSettings:
    """Optional NewsAPI configuration layered on top of RSS ingestion."""

    enabled: bool = False
    queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceSettings:
    """Grouping of all upstream content source settings."""

    rss: list[RssSourceConfig] = field(default_factory=list)
    newsapi: NewsApiSettings = field(default_factory=NewsApiSettings)


@dataclass(frozen=True)
class ScheduleSettings:
    """Scheduling and volume limits that bound each ingestion run."""

    lookback_hours: int = 24
    max_articles_total: int = 8
    max_articles_per_source: int = 3


@dataclass(frozen=True)
class Settings:
    """Top-level application settings loaded from configuration."""

    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    sources: SourceSettings = field(default_factory=SourceSettings)

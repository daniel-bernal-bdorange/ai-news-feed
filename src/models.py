from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .summary_prompts import DEFAULT_SUMMARY_PROMPT_TEMPLATE


DEFAULT_GEO_PRIORITY_KEYWORDS = [
    "spain",
    "españa",
    "spanish",
    "madrid",
    "barcelona",
    "masorange",
    "telefónica",
    "european",
    "europe",
    "european union",
    "eu regulation",
    "european regulation",
    "eu ai act",
]


@dataclass(frozen=True)
class Article:
    """Normalized article representation shared across all ingestion sources."""

    title: str
    url: str
    source_name: str
    published_date: datetime
    raw_content: str
    category: str | None = None
    geo_boost: bool = False
    fetched_at: datetime | None = None
    relevance_score: float = 1.0
    summary: str | None = None
    selected: bool = False
    id: str | None = None


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
class EditorialSettings:
    """Editorial rules used to keep low-signal content out of the shortlist."""

    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_title_length: int = 0
    geo_priority: "GeoPrioritySettings" = field(default_factory=lambda: GeoPrioritySettings())


@dataclass(frozen=True)
class GeoPrioritySettings:
    """Keywords and multiplier used to surface Spain and EU-relevant stories first."""

    enabled: bool = True
    boost_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_GEO_PRIORITY_KEYWORDS))
    boost_score: float = 1.5


@dataclass(frozen=True)
class RankingSettings:
    """Final digest ranking controls used after ingestion and deduplication."""

    max_articles_per_category: int | None = None
    max_articles_per_source: int | None = None


@dataclass(frozen=True)
class AiSummarySettings:
    """Runtime settings for AI-based article summaries.
    
    Supports multiple providers (Groq, xAI Grok, etc.) via OpenAI-compatible API.
    When no provider is configured or unavailable, falls back to placeholder.
    """

    enabled: bool = True
    provider: str = "placeholder"
    model: str = "grok-beta"
    max_words: int = 60
    prompt_template: str = DEFAULT_SUMMARY_PROMPT_TEMPLATE
    api_url: str = ""
    api_key: str | None = None
    timeout_seconds: float = 20.0
    max_retries: int = 3
    retry_base_seconds: float = 0.5
    retry_max_seconds: float = 4.0


@dataclass(frozen=True)
class Settings:
    """Top-level application settings loaded from configuration."""

    schedule: ScheduleSettings = field(default_factory=ScheduleSettings)
    sources: SourceSettings = field(default_factory=SourceSettings)
    editorial: EditorialSettings = field(default_factory=EditorialSettings)
    ranking: RankingSettings = field(default_factory=RankingSettings)
    ai_summary: AiSummarySettings = field(default_factory=AiSummarySettings)

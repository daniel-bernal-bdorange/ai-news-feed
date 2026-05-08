from __future__ import annotations

from pathlib import Path

import yaml

from .models import AiSummarySettings, EditorialSettings, GeoPrioritySettings, NewsApiSettings, RankingSettings, RssSourceConfig, ScheduleSettings, Settings, SourceSettings


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    """Load application settings from YAML into typed configuration objects."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    schedule = ScheduleSettings(**data.get("schedule", {}))
    sources_data = data.get("sources", {})
    editorial_data = data.get("editorial", {})
    geo_priority_data = editorial_data.get("geo_priority", {})
    ranking_data = data.get("ranking", {})
    ai_summary_data = data.get("ai_summary", {})

    # Keep source parsing explicit so malformed sections fail close to the config boundary.
    rss_sources = [RssSourceConfig(**item) for item in sources_data.get("rss", [])]
    newsapi_data = sources_data.get("newsapi", {})
    newsapi = NewsApiSettings(
        enabled=newsapi_data.get("enabled", False),
        queries=list(newsapi_data.get("queries", [])),
    )
    editorial = EditorialSettings(
        include_keywords=list(editorial_data.get("include_keywords", [])),
        exclude_keywords=list(editorial_data.get("exclude_keywords", [])),
        min_title_length=editorial_data.get("min_title_length", 0),
        geo_priority=GeoPrioritySettings(
            enabled=geo_priority_data.get("enabled", True),
            boost_keywords=list(geo_priority_data.get("boost_keywords", GeoPrioritySettings().boost_keywords)),
            boost_score=geo_priority_data.get("boost_score", GeoPrioritySettings().boost_score),
        ),
    )
    ranking = RankingSettings(
        max_articles_per_category=ranking_data.get("max_articles_per_category"),
        max_articles_per_source=ranking_data.get("max_articles_per_source"),
    )
    ai_summary = AiSummarySettings(
        enabled=ai_summary_data.get("enabled", True),
        provider=ai_summary_data.get("provider", AiSummarySettings().provider),
        model=ai_summary_data.get("model", AiSummarySettings().model),
        max_words=ai_summary_data.get("max_words", AiSummarySettings().max_words),
        prompt_template=ai_summary_data.get("prompt_template", AiSummarySettings().prompt_template),
        api_url=ai_summary_data.get("api_url", AiSummarySettings().api_url),
        api_key=ai_summary_data.get("api_key", AiSummarySettings().api_key),
        timeout_seconds=ai_summary_data.get("timeout_seconds", AiSummarySettings().timeout_seconds),
        max_retries=ai_summary_data.get("max_retries", AiSummarySettings().max_retries),
        retry_base_seconds=ai_summary_data.get("retry_base_seconds", AiSummarySettings().retry_base_seconds),
        retry_max_seconds=ai_summary_data.get("retry_max_seconds", AiSummarySettings().retry_max_seconds),
    )

    return Settings(
        schedule=schedule,
        sources=SourceSettings(rss=rss_sources, newsapi=newsapi),
        editorial=editorial,
        ranking=ranking,
        ai_summary=ai_summary,
    )

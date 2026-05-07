from __future__ import annotations

from pathlib import Path

import yaml

from .models import EditorialSettings, NewsApiSettings, RssSourceConfig, ScheduleSettings, Settings, SourceSettings


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    """Load application settings from YAML into typed configuration objects."""

    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    schedule = ScheduleSettings(**data.get("schedule", {}))
    sources_data = data.get("sources", {})
    editorial_data = data.get("editorial", {})

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
    )

    return Settings(
        schedule=schedule,
        sources=SourceSettings(rss=rss_sources, newsapi=newsapi),
        editorial=editorial,
    )

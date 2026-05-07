from __future__ import annotations

from pathlib import Path

import yaml

from .models import NewsApiSettings, RssSourceConfig, ScheduleSettings, Settings, SourceSettings


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    schedule = ScheduleSettings(**data.get("schedule", {}))
    sources_data = data.get("sources", {})

    rss_sources = [RssSourceConfig(**item) for item in sources_data.get("rss", [])]
    newsapi_data = sources_data.get("newsapi", {})
    newsapi = NewsApiSettings(
        enabled=newsapi_data.get("enabled", False),
        queries=list(newsapi_data.get("queries", [])),
    )

    return Settings(
        schedule=schedule,
        sources=SourceSettings(rss=rss_sources, newsapi=newsapi),
    )

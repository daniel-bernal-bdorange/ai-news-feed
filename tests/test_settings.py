from pathlib import Path

from src.settings import load_settings


def test_load_settings_reads_rss_and_newsapi_configuration(tmp_path: Path) -> None:
    """YAML settings should map cleanly into the typed configuration objects."""

    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
schedule:
  lookback_hours: 12
  max_articles_total: 5
  max_articles_per_source: 2
sources:
  rss:
    - name: Example Feed
      url: https://example.com/rss
      category: ai
  newsapi:
    enabled: true
    queries:
      - example query
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.schedule.lookback_hours == 12
    assert settings.schedule.max_articles_per_source == 2
    assert settings.sources.rss[0].name == "Example Feed"
    assert settings.sources.newsapi.enabled is True
    assert settings.sources.newsapi.queries == ["example query"]

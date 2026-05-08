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
editorial:
  include_keywords:
    - orange
  exclude_keywords:
    - podcast
  min_title_length: 18
  geo_priority:
    enabled: true
    boost_keywords:
      - Spain
      - European regulation
    boost_score: 1.8
ranking:
  max_articles_per_category: 2
  max_articles_per_source: 1
ai_summary:
  enabled: true
  model: grok-vision-beta
  max_words: 45
  timeout_seconds: 15
  max_retries: 4
  retry_base_seconds: 0.25
  retry_max_seconds: 2.0
  prompt_template: |
    Summarize in {max_words} words.
    {geo_instruction}
    Article: {content}
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.schedule.lookback_hours == 12
    assert settings.schedule.max_articles_per_source == 2
    assert settings.sources.rss[0].name == "Example Feed"
    assert settings.sources.newsapi.enabled is True
    assert settings.sources.newsapi.queries == ["example query"]
    assert settings.editorial.include_keywords == ["orange"]
    assert settings.editorial.exclude_keywords == ["podcast"]
    assert settings.editorial.min_title_length == 18
    assert settings.editorial.geo_priority.enabled is True
    assert settings.editorial.geo_priority.boost_keywords == ["Spain", "European regulation"]
    assert settings.editorial.geo_priority.boost_score == 1.8
    assert settings.ranking.max_articles_per_category == 2
    assert settings.ranking.max_articles_per_source == 1
    assert settings.ai_summary.enabled is True
    assert settings.ai_summary.model == "grok-vision-beta"
    assert settings.ai_summary.max_words == 45
    assert settings.ai_summary.timeout_seconds == 15
    assert settings.ai_summary.max_retries == 4
    assert settings.ai_summary.retry_base_seconds == 0.25
    assert settings.ai_summary.retry_max_seconds == 2.0
    assert "Summarize in {max_words} words." in settings.ai_summary.prompt_template

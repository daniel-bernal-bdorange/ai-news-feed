from __future__ import annotations

import logging
import os

from src.fetcher import fetch_all_articles
from src.settings import load_settings
from src.storage import DEFAULT_ARTICLE_STORE_PATH, persist_weekly_articles
from src.summarizer import summarize_articles


def main() -> None:
    """Run the ingestion flow and print the shortlisted articles."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = load_settings()
    articles = fetch_all_articles(settings, api_key=os.getenv("NEWSAPI_KEY"))
    articles = summarize_articles(articles, settings.ai_summary, api_key=os.getenv("GROQ_API_KEY"))
    weekly_store = persist_weekly_articles(articles)

    logging.info("Articulos candidatos tras deduplicacion: %s", len(articles))
    logging.info("Acumulado semanal persistido en %s: %s", DEFAULT_ARTICLE_STORE_PATH, len(weekly_store.articles))
    for article in articles:
        # Keep the CLI output compact so it can be used as a quick smoke check.
        print(f"- [{article.source_name}] {article.title} -> {article.url}")
        if article.summary:
            print(f"  Summary: {article.summary}")


if __name__ == "__main__":
    main()

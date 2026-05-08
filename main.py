from __future__ import annotations

import argparse
import logging
import os
from typing import Sequence

from dotenv import load_dotenv

from src.fetcher import fetch_all_articles
from src.publisher import publish_digest
from src.settings import load_settings, validate_secrets
from src.storage import DEFAULT_ARTICLE_STORE_PATH, persist_weekly_articles
from src.summarizer import summarize_articles


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for selecting the runtime flow."""

    parser = argparse.ArgumentParser(description="AI News Feed runner")
    parser.add_argument(
        "--mode",
        choices=("daily", "weekly"),
        default="daily",
        help="daily ingests and stores articles, weekly also publishes the digest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run ingestion flow and optionally publish the weekly digest."""

    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    load_dotenv()  # No-op when .env is absent (e.g. in CI where secrets are injected directly).

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = load_settings()
    validate_secrets(settings)
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

    webhook_url = os.getenv("POWER_AUTOMATE_URL")
    if args.mode == "weekly" and webhook_url:
        # Re-summarize the full weekly store before publishing so legacy entries
        # created in previous runs keep the same language/tone contract.
        weekly_articles = summarize_articles(
            weekly_store.articles,
            settings.ai_summary,
            api_key=os.getenv("GROQ_API_KEY"),
        )
        weekly_store = persist_weekly_articles(weekly_articles)
        week_label = f"{weekly_store.week_start} / {weekly_store.week_end}"
        publish_digest(weekly_store.articles, week_label, webhook_url)
    elif args.mode == "weekly":
        logging.info("POWER_AUTOMATE_URL no configurada; digest semanal omitido.")
    else:
        logging.info("Modo diario: publicacion omitida.")


if __name__ == "__main__":
    main()

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
from src.structured_logging import (
    STAGE_FETCH,
    STAGE_FILTER,
    STAGE_PERSIST,
    STAGE_PUBLISH,
    STAGE_RANK,
    STAGE_SUMMARIZE,
    configure_structured_logging,
    get_logger,
    log_stage,
)


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

    configure_structured_logging(stage="main")
    logger = get_logger(__name__)

    settings = load_settings()
    validate_secrets(settings)

    # FETCH stage
    with log_stage(STAGE_FETCH, logger) as fetch_ctx:
        articles = fetch_all_articles(settings, api_key=os.getenv("NEWSAPI_KEY"))
        fetch_ctx["articles_fetched"] = len(articles)

    # SUMMARIZE stage
    with log_stage(STAGE_SUMMARIZE, logger, {"articles_to_summarize": len(articles)}) as summary_ctx:
        articles = summarize_articles(articles, settings.ai_summary, api_key=os.getenv("GROQ_API_KEY"))
        summary_ctx["articles_summarized"] = len(articles)

    # PERSIST stage
    with log_stage(STAGE_PERSIST, logger, {"articles_to_persist": len(articles)}) as persist_ctx:
        weekly_store = persist_weekly_articles(articles)
        persist_ctx["articles_persisted"] = len(articles)
        persist_ctx["store_size"] = len(weekly_store.articles)

    logger.info(
        "Pipeline diario completado",
        extra={
            "stage": "main",
            "articles_candidate": len(articles),
            "weekly_accumulated": len(weekly_store.articles),
            "store_path": DEFAULT_ARTICLE_STORE_PATH,
        },
    )
    for article in articles:
        # Keep the CLI output compact so it can be used as a quick smoke check.
        print(f"- [{article.source_name}] {article.title} -> {article.url}")
        if article.summary:
            print(f"  Summary: {article.summary}")

    webhook_url = os.getenv("POWER_AUTOMATE_URL")
    if args.mode == "weekly" and webhook_url:
        # SUMMARIZE (re-summarize for weekly consistency)
        with log_stage(STAGE_SUMMARIZE, logger, {"weekly_articles": len(weekly_store.articles), "context": "weekly_consistency"}) as summary_ctx:
            weekly_articles = summarize_articles(
                weekly_store.articles,
                settings.ai_summary,
                api_key=os.getenv("GROQ_API_KEY"),
            )
            summary_ctx["articles_summarized"] = len(weekly_articles)

        # PERSIST (weekly refresh)
        with log_stage(STAGE_PERSIST, logger, {"context": "weekly_refresh"}) as persist_ctx:
            weekly_store = persist_weekly_articles(weekly_articles)
            persist_ctx["weekly_articles_final"] = len(weekly_store.articles)

        # PUBLISH stage
        with log_stage(STAGE_PUBLISH, logger, {"articles": len(weekly_store.articles)}) as publish_ctx:
            week_label = f"{weekly_store.week_start} / {weekly_store.week_end}"
            publish_digest(weekly_store.articles, week_label, webhook_url)
            publish_ctx["week_label"] = week_label
            publish_ctx["status"] = "published"
    elif args.mode == "weekly":
        logger.info("POWER_AUTOMATE_URL no configurada; digest semanal omitido.", extra={"stage": "main"})
    else:
        logger.info("Modo diario: publicacion omitida.", extra={"stage": "main"})


if __name__ == "__main__":
    main()

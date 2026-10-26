from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from dotenv import load_dotenv

from src.fetcher import fetch_all_articles, rank_articles_for_digest
from src.fetcher import apply_trending_boost, fetch_trending_topics
from src.publisher import publish_digest
from src.settings import load_settings, validate_secrets
from src.storage import DEFAULT_ARTICLE_STORE_PATH, persist_weekly_articles
from src.structured_logging import (
    STAGE_FETCH,
    STAGE_PERSIST,
    STAGE_PUBLISH,
    STAGE_SUMMARIZE,
    configure_structured_logging,
    get_logger,
    log_stage,
)
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
    parser.add_argument(
        "--show-scores",
        action="store_true",
        help="print relevance scores next to each article in the CLI output",
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

    trending_topics = fetch_trending_topics(settings.trending)

    # FETCH stage
    with log_stage(STAGE_FETCH, logger) as fetch_ctx:
        articles = fetch_all_articles(settings, api_key=os.getenv("NEWSAPI_KEY"))
        fetch_ctx["articles_fetched"] = len(articles)

    # SUMMARIZE stage
    with log_stage(STAGE_SUMMARIZE, logger, {"articles_to_summarize": len(articles)}) as summary_ctx:
        articles = summarize_articles(articles, settings.ai_summary, api_key=os.getenv("GROQ_API_KEY"))
        articles = apply_trending_boost(articles, trending_topics, settings.trending)
        articles = rank_articles_for_digest(articles, settings)
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
    _print_articles(articles, show_scores=args.show_scores)

    webhook_url = os.getenv("POWER_AUTOMATE_URL")
    if args.mode == "weekly" and webhook_url:
        # SUMMARIZE (re-summarize for weekly consistency)
        with log_stage(STAGE_SUMMARIZE, logger, {"weekly_articles": len(weekly_store.articles), "context": "weekly_consistency"}) as summary_ctx:
            weekly_articles = summarize_articles(
                weekly_store.articles,
                settings.ai_summary,
                api_key=os.getenv("GROQ_API_KEY"),
            )
            weekly_articles = apply_trending_boost(weekly_articles, trending_topics, settings.trending)
            weekly_articles = rank_articles_for_digest(weekly_articles, settings)
            summary_ctx["articles_summarized"] = len(weekly_articles)

        # PERSIST (weekly refresh)
        with log_stage(STAGE_PERSIST, logger, {"context": "weekly_refresh"}) as persist_ctx:
            weekly_store = persist_weekly_articles(weekly_articles)
            persist_ctx["weekly_articles_final"] = len(weekly_store.articles)

        # PUBLISH stage
        with log_stage(STAGE_PUBLISH, logger, {"articles": len(weekly_articles)}) as publish_ctx:
            week_label = f"{weekly_store.week_start} / {weekly_store.week_end}"
            publish_digest(weekly_articles, week_label, webhook_url)
            publish_ctx["week_label"] = week_label
            publish_ctx["articles_sent"] = len(weekly_articles)
            publish_ctx["status"] = "published"
    elif args.mode == "weekly":
        logger.info("POWER_AUTOMATE_URL no configurada; digest semanal omitido.", extra={"stage": "main"})
    else:
        logger.info("Modo diario: publicacion omitida.", extra={"stage": "main"})


def _print_articles(articles: list, *, show_scores: bool) -> None:
    """Print a compact article list for local smoke checks."""

    for index, article in enumerate(articles, start=1):
        display_title = article.display_title or article.title
        score_prefix = f"[{article.relevance_score:.2f}] " if show_scores else ""
        print(f"{index}. {score_prefix}[{article.source_name}] {display_title} -> {article.url}")
        if article.summary:
            print(f"   Summary: {article.summary}")


if __name__ == "__main__":
    main()

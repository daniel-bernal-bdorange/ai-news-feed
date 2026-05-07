from __future__ import annotations

import logging
import os

from src.fetcher import fetch_all_articles
from src.settings import load_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    settings = load_settings()
    articles = fetch_all_articles(settings, api_key=os.getenv("NEWSAPI_KEY"))

    logging.info("Articulos candidatos tras deduplicacion: %s", len(articles))
    for article in articles:
        print(f"- [{article.source_name}] {article.title} -> {article.url}")


if __name__ == "__main__":
    main()

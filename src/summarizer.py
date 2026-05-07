from __future__ import annotations

from .models import Article

DEFAULT_SUMMARY_PROMPT_TEMPLATE = """You are a news analyst for a technology and telecom company based in Spain.
Summarize the following news article in {max_words} words or less.
{geo_instruction}
Be factual, neutral, and concise. Output only the summary, no preamble.
Article: {content}"""

GEO_RELEVANCE_INSTRUCTION = "This article is relevant to Spain or the European market. Mention that relevance explicitly."
DEFAULT_RELEVANCE_INSTRUCTION = "Mention Spain or the European market only when the article clearly supports it."


def build_summary_prompt(
    article: Article,
    *,
    max_words: int = 60,
    prompt_template: str = DEFAULT_SUMMARY_PROMPT_TEMPLATE,
) -> str:
    """Render a summary prompt that carries geo-relevance into downstream summarization."""

    content = article.raw_content.strip() or article.title.strip()
    geo_instruction = GEO_RELEVANCE_INSTRUCTION if article.geo_boost else DEFAULT_RELEVANCE_INSTRUCTION
    return prompt_template.format(
        max_words=max_words,
        geo_instruction=geo_instruction,
        content=content,
    )
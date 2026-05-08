from __future__ import annotations

DEFAULT_SUMMARY_PROMPT_TEMPLATE = """You are a news analyst for a technology and telecom company based in Spain.
Summarize the following news article in {max_words} words or less.
{geo_instruction}
Be factual, neutral, and concise. Output only the summary, no preamble.
Article: {content}"""

GEO_RELEVANCE_INSTRUCTION = "This article is relevant to Spain or the European market. Mention that relevance explicitly."
DEFAULT_RELEVANCE_INSTRUCTION = "Mention Spain or the European market only when the article clearly supports it."
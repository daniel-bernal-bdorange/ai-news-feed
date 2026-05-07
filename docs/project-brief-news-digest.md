# Project Brief: News Digest Bot for Microsoft Teams

## 1. Overview

**Project name:** `news-digest-bot`
**Goal:** Automated system that fetches news from multiple RSS/API sources, generates AI-powered summaries, and delivers a daily digest to a Microsoft Teams channel via Incoming Webhook.
**Execution environment:** GitHub Actions (scheduled cron job)
**Primary language:** Python 3.11+
**Constraint:** All technologies and services must use free tiers only. No paid subscriptions.

---

## 2. Functional Requirements

### FR-01 — News Fetching
- The system must fetch news articles from a configurable list of RSS feed URLs.
- Optionally, it must support fetching from NewsAPI (free tier: 100 requests/day, development only).
- For each source, it must retrieve up to a configurable maximum number of articles published in the last N hours (default: 24h).
- Each article must be normalized into a standard internal schema: `{ title, url, source_name, published_date, raw_content }`.
- Duplicate articles (same URL or near-identical title across sources) must be deduplicated.

### FR-02 — Article Selection & Filtering
- The system must filter articles based on a configurable list of keywords or topics of interest.
- It must support a blocklist of sources or keywords to exclude irrelevant content.
- It must rank and select the top N articles per run (default: 5–10), configurable per source category.
- It must apply a **geo-priority boost** to articles mentioning Spain, the Spanish market, or European regulation. Boosted articles receive a higher ranking score (configurable multiplier, default ×1.5) and are surfaced before equivalent non-geo articles.
- The LLM summarization prompt must include a Spain/Europe context hint so that, when an article has Spanish or European relevance, the summary mentions it explicitly.

### FR-03 — AI Summarization
- The system must call the Groq API (free tier) to generate a concise summary of each selected article.
- The summarization prompt must be configurable (template stored in config).
- Each summary must be limited to a configurable maximum number of words (default: 60 words).
- The system must handle API rate limits gracefully with retries and exponential backoff.
- If summarization fails for an article, the system must fall back to the article's original description/excerpt.

### FR-04 — Teams Notification
- The system must deliver the digest to Microsoft Teams via an Incoming Webhook URL.
- The message must be formatted as an Adaptive Card (Teams-compatible JSON payload).
- The card must include: digest title with date, list of articles each with title, source, summary, and link.
- The Webhook URL must be stored as a secret and never hardcoded.
- If the webhook delivery fails, the system must retry up to 3 times before logging the error and exiting.

### FR-05 — Scheduling & Execution
- The system must run automatically on a configurable cron schedule via GitHub Actions (default: weekdays at 08:00 CET).
- It must also support manual triggering via `workflow_dispatch`.
- Execution logs must be available in the GitHub Actions run history.

### FR-06 — Configuration
- All configurable parameters (sources, schedule, filters, model, max articles, etc.) must be defined in a YAML config file (`config/settings.yaml`), not hardcoded.
- Secrets (API keys, webhook URL) must be managed via GitHub Actions Secrets and injected as environment variables at runtime.

---

## 3. Non-Functional Requirements

- **Reliability:** The system must complete a full run in under 3 minutes under normal conditions.
- **Resilience:** Any single source failure must not abort the entire run; errors must be logged and the run must continue with remaining sources.
- **Observability:** The system must produce structured logs (INFO/WARNING/ERROR) for each stage: fetch, filter, summarize, deliver.
- **Maintainability:** Source list and filters must be editable via YAML without touching Python code.
- **Security:** No secrets may appear in logs, config files, or source code.
- **Cost:** Total monthly cost must be $0. All services must remain within free tier limits.

---

## 4. Technology Stack

| Component | Technology | Free Tier Limit |
|---|---|---|
| Language | Python 3.11 | — |
| RSS parsing | `feedparser` library | Unlimited |
| News API (optional) | NewsAPI.org | 100 req/day |
| AI summarization | Groq API | ~14,400 req/day (free tier) |
| LLM model | `llama-3.1-8b-instant` via Groq | Included in Groq free tier |
| HTTP client | `httpx` or `requests` | — |
| Teams delivery | Microsoft Teams Incoming Webhook | Free, native Teams feature |
| Scheduling | GitHub Actions (cron) | 2,000 min/month (free private repos) |
| Secrets management | GitHub Actions Secrets | Free |
| Config format | YAML (`PyYAML`) | — |
| Testing | `pytest` | — |
| Linting | `ruff` | — |

---

## 5. System Architecture

```
┌─────────────────────────────────┐
│     GitHub Actions (cron)        │
│  schedule: "0 7 * * 1-5" (UTC)  │
└────────────────┬────────────────┘
                 │ triggers
                 ▼
┌─────────────────────────────────┐
│         main.py (orchestrator)   │
│  1. Load config                  │
│  2. Run fetcher                  │
│  3. Run filter/deduplicator      │
│  4. Run summarizer               │
│  5. Run notifier                 │
└──┬──────────┬────────┬──────────┘
   │          │        │
   ▼          ▼        ▼
fetcher.py  summarizer.py  notifier.py
   │          │        │
   ▼          ▼        ▼
RSS Feeds  Groq API  Teams Webhook
NewsAPI
```

---

## 6. Repository Structure

```
news-digest-bot/
├── .github/
│   └── workflows/
│       └── daily_digest.yml        # Cron job + manual trigger
├── src/
│   ├── __init__.py
│   ├── fetcher.py                  # RSS + NewsAPI ingestion
│   ├── filter.py                   # Deduplication, keyword filtering, ranking + geo-priority boost
│   ├── summarizer.py               # Groq API integration
│   ├── notifier.py                 # Teams Adaptive Card builder + webhook POST
│   └── models.py                   # Pydantic models / dataclasses for Article schema
├── config/
│   └── settings.yaml               # All runtime configuration (no secrets)
├── tests/
│   ├── test_fetcher.py
│   ├── test_filter.py
│   ├── test_summarizer.py
│   └── test_notifier.py
├── main.py                         # Entry point
├── requirements.txt
└── README.md
```

---

## 7. Configuration Schema (`config/settings.yaml`)

```yaml
schedule:
  lookback_hours: 24
  max_articles_total: 8
  max_articles_per_source: 3

sources:
  rss:

    # ── INTELIGENCIA ARTIFICIAL ──────────────────────────────────────────────
    - name: "OpenAI Blog"
      url: "https://openai.com/blog/rss/"
      category: "ai"

    - name: "Google AI Blog"
      url: "https://ai.googleblog.com/feeds/posts/default"
      category: "ai"

    - name: "MIT Technology Review – AI"
      url: "https://news.mit.edu/rss/topic/artificial-intelligence"
      category: "ai"

    - name: "The Rundown AI"
      url: "https://rss.beehiiv.com/feeds/2R3C6BPaez.xml"
      category: "ai"

    - name: "VentureBeat – AI"
      url: "https://venturebeat.com/category/ai/feed/"
      category: "ai"

    # ── TECNOLOGÍA PUNTERA ───────────────────────────────────────────────────
    - name: "TechCrunch"
      url: "https://techcrunch.com/category/artificial-intelligence/feed/"
      category: "tech"

    - name: "Wired – AI & Tech"
      url: "https://www.wired.com/feed/tag/ai/latest/rss"
      category: "tech"

    - name: "Ars Technica"
      url: "https://feeds.arstechnica.com/arstechnica/index"
      category: "tech"

    - name: "The Verge – AI"
      url: "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
      category: "tech"

    # ── TELCO / INDUSTRIA ────────────────────────────────────────────────────
    - name: "RCR Wireless News"
      url: "https://www.rcrwireless.com/feed"
      category: "telco"

    - name: "Light Reading"
      url: "https://www.lightreading.com/rss"
      category: "telco"

    - name: "Fierce Network (Telecom)"
      url: "https://www.fierce-network.com/rss/xml"
      category: "telco"

    - name: "TelecomTV"
      url: "https://www.telecomtv.com/content/rss/"
      category: "telco"

    # ── ORANGE BUSINESS ──────────────────────────────────────────────────────
    - name: "Orange Business – Press Releases"
      url: "https://www.orange-business.com/en/rss.xml"
      category: "orange"
      # Fallback: si el feed directo falla, usar NewsAPI con query "Orange Business"

    - name: "Orange Newsroom"
      url: "https://newsroom.orange.com/feed/"
      category: "orange"

    - name: "Orange Group – GlobeNewswire"
      url: "https://www.globenewswire.com/RssFeed/organization/Orange"
      category: "orange"

  newsapi:
    enabled: true
    queries:
      - "Orange Business Services"
      - "Orange telecom enterprise AI"
    # Nota: NewsAPI free tier solo permite búsqueda en últimas 24h con plan developer

filters:
  keywords_include:
    - "artificial intelligence"
    - "AI"
    - "machine learning"
    - "LLM"
    - "generative AI"
    - "agentic"
    - "5G"
    - "6G"
    - "telecom"
    - "telco"
    - "network"
    - "cloud"
    - "cybersecurity"
    - "enterprise"
    - "Orange Business"
    - "connectivity"
  keywords_exclude:
    - "patrocinado"
    - "publicidad"
    - "sponsored"
    - "advertisement"
    - "obituary"
    - "horoscope"
  min_title_length: 25

  geo_priority:
    enabled: true
    boost_keywords:
      - "Spain"
      - "España"
      - "Spanish"
      - "Madrid"
      - "Barcelona"
      - "MasOrange"
      - "Telefónica"
      - "GSMA"           # MWC se celebra en Barcelona
      - "European"
      - "Europa"
    boost_score: 1.5     # multiplicador sobre el score base de ranking

summarization:
  model: "llama-3.1-8b-instant"
  max_summary_words: 60
  geo_context: "Spain"   # hint para el LLM: priorizar relevancia para mercado español
  prompt_template: |
    You are a news analyst for a technology and telecom company based in Spain.
    Summarize the following news article in {max_words} words or less.
    If the article is relevant to Spain or the European market, mention it explicitly.
    Be factual, neutral, and concise. Output only the summary, no preamble.
    Article: {content}

teams:
  card_title: "📡 Daily Tech & AI Digest"
  card_color: "FF6600"   # Orange brand color
```

---

## 8. Environment Variables (GitHub Secrets)

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key for LLM summarization |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams Incoming Webhook URL |
| `NEWSAPI_KEY` | NewsAPI key (optional, only if NewsAPI enabled) |

---

## 9. GitHub Actions Workflow Spec (`.github/workflows/daily_digest.yml`)

- **Triggers:** `schedule` (cron: weekdays 07:00 UTC = 08:00 CET), `workflow_dispatch`
- **Runner:** `ubuntu-latest`
- **Steps:**
  1. Checkout repository
  2. Set up Python 3.11
  3. Cache pip dependencies
  4. Install dependencies from `requirements.txt`
  5. Run `python main.py`
  6. On failure: output logs and exit with non-zero code (triggers GitHub notification)
- **Secrets injected as env vars:** `GROQ_API_KEY`, `TEAMS_WEBHOOK_URL`, `NEWSAPI_KEY`

---

## 10. Teams Adaptive Card Format

The message delivered to Teams must follow this structure:

```
┌─────────────────────────────────────────────────────┐
│ 📡 Daily Tech & AI Digest — Wed 7 May 2026          │
│ 8 artículos · AI · Tech · Telco · Orange Business   │
├─────────────────────────────────────────────────────┤
│ [AI] Título del artículo 1                          │
│ Fuente: OpenAI Blog · hace 2h                        │
│ Resumen generado en 60 palabras.                     │
│ [Leer más →]                                         │
├─────────────────────────────────────────────────────┤
│ [TELCO] Título del artículo 2                        │
│ Fuente: RCR Wireless · hace 4h                       │
│ ...                                                  │
├─────────────────────────────────────────────────────┤
│ [ORANGE] Título del artículo 3                       │
│ Fuente: Orange Business Press · hace 1h              │
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

Payload format: `application/json` POST to Teams Incoming Webhook URL using `attachments` with `contentType: application/vnd.microsoft.card.adaptive`.

---

## 11. Error Handling Strategy

| Failure scenario | Behavior |
|---|---|
| RSS feed unreachable | Log WARNING, skip source, continue |
| NewsAPI quota exceeded | Log WARNING, skip NewsAPI, continue with RSS |
| Groq API error / timeout | Retry 3x with backoff; fallback to raw excerpt |
| Groq rate limit hit | Wait and retry; if persistent, skip summarization for that article |
| Teams webhook failure | Retry 3x; log ERROR and exit with code 1 if all retries fail |
| No articles found | Log WARNING and send a minimal "no news today" card to Teams |
| Config file missing | Exit with code 1 and descriptive error message |

---

## 12. Testing Requirements

- Unit tests for each module in `src/` with mocked external calls.
- Test coverage target: ≥ 80%.
- Tests must run in GitHub Actions on every push to `main`.
- Key test cases:
  - `test_fetcher`: valid RSS parsing, malformed feed handling, deduplication
  - `test_filter`: keyword inclusion/exclusion, date filtering, ranking
  - `test_summarizer`: successful summarization, API failure fallback, prompt rendering
  - `test_notifier`: Adaptive Card JSON structure validation, webhook retry logic

---

## 13. Definition of Done

A feature or epic is considered done when:
1. Code is implemented and passes linting (`ruff`).
2. Unit tests are written and pass (`pytest`).
3. The feature works end-to-end in a GitHub Actions manual run.
4. No secrets are exposed in logs or config files.
5. `README.md` is updated with any new configuration options.

---

## 14. Out of Scope (v1)

- Web UI or dashboard
- Persistent storage / database of past digests
- User subscriptions or personalization
- Support for non-RSS sources (scrapers, Telegram, Twitter/X)
- Multi-channel or multi-team delivery
- Copilot Studio / Power Platform integration (may be added in v2)
- Translation of articles

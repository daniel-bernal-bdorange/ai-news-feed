# Project Brief: News Digest Bot for Microsoft Teams

## 1. Overview

**Project name:** `news-digest-bot`
**Goal:** Automated system that fetches news daily from multiple RSS/API sources, stores and scores articles throughout the week, and delivers a curated weekly digest every Friday to a Microsoft Teams channel via Incoming Webhook.
**Execution environment:** GitHub Actions (two scheduled cron workflows)
**Primary language:** Python 3.11+
**Constraint:** All technologies and services must use free tiers only. No paid subscriptions.
**Versioning:** This brief covers v1. A v2 roadmap is defined in section 16.

---

## 2. Functional Requirements

### FR-01 — Daily News Fetching
- The system must fetch news articles every day of the week (Monday to Sunday) at 08:00 CET.
- It must fetch from a configurable list of RSS feed URLs and optionally from NewsAPI (free tier: 100 req/day).
- For each source, it must retrieve articles published in the last 24 hours.
- Each article must be normalized into the standard internal schema defined in section 7.
- Articles already stored in `data/articles_week.json` (matched by URL) must be deduplicated and skipped.
- After fetching and filtering, new articles must be appended to `data/articles_week.json` and committed to the repository automatically.

### FR-02 — Article Filtering & Scoring
- The system must filter articles based on a configurable list of keywords or topics of interest.
- It must support a blocklist of keywords to exclude irrelevant content.
- Each article must receive a numeric relevance score based on keyword matches in title and content.
- It must apply a **geo-priority boost** to articles mentioning Spain, the Spanish market, or European regulation. Boosted articles receive a score multiplier (configurable, default ×1.5).
- The score and geo_boost flag must be persisted in `articles_week.json` for use during weekly ranking.

### FR-03 — Weekly Ranking & Selection
- Every Friday, the system must load all articles accumulated in `articles_week.json` for the current week.
- It must apply a final ranking combining: relevance score, geo-priority boost, recency weight (more recent = slightly higher), and source diversity bonus (same topic covered by 3+ sources = signal boost).
- It must select the top N articles (default: 8–10, configurable) ensuring category balance: at least 1 article per category (ai, tech, telco, orange) if available.
- After sending the digest, the system must reset `articles_week.json` to an empty array and commit the reset.

### FR-04 — AI Summarization
- The system must call the Groq API (free tier) to generate a concise summary of each selected article on Fridays only.
- The summarization prompt must include a Spain/Europe context hint: when an article has Spanish or European relevance, the summary must mention it explicitly.
- Each summary must be limited to a configurable maximum number of words (default: 60).
- The system must handle API rate limits gracefully with retries and exponential backoff.
- If summarization fails for an article, the system must fall back to the article's original description/excerpt.

### FR-05 — Weekly Teams Notification
- The system must deliver the weekly digest to Microsoft Teams every Friday via an Incoming Webhook URL.
- The message must be formatted as an Adaptive Card (Teams-compatible JSON payload).
- The card must include: digest title, week date range, total article count, category breakdown, and for each article: title, source, category badge, publication date, summary, and read-more link.
- Articles with `geo_boost: true` must display a 🇪🇸 flag badge in the card.
- The Webhook URL must be stored as a secret and never hardcoded.
- If the webhook delivery fails, the system must retry up to 3 times before logging the error and exiting with code 1.

### FR-06 — Persistent Weekly Storage
- Articles must be stored in `data/articles_week.json` inside the repository.
- The JSON schema must be aligned with the v2 SQLite schema (section 16) to make future migration a single import script with no data transformation.
- The file must be committed automatically after every daily fetch and after every weekly reset.
- The GitHub Actions bot must have write permissions to commit to the `main` branch.

### FR-07 — Configuration
- All configurable parameters must be defined in `config/settings.yaml`. No hardcoded values.
- Secrets (API keys, webhook URL) must be managed via GitHub Actions Secrets and injected as environment variables at runtime.

---

## 3. Non-Functional Requirements

- **Reliability:** Daily fetch must complete in under 2 minutes. Friday digest run must complete in under 4 minutes.
- **Resilience:** Any single source failure must not abort the run. Errors must be logged and execution must continue with remaining sources.
- **Observability:** Structured logs (INFO/WARNING/ERROR) must be produced for every stage: fetch, filter, score, rank, summarize, store, deliver.
- **Maintainability:** Source list, filters, and scoring weights must be editable via YAML without touching Python code.
- **Security:** No secrets may appear in logs, config files, or source code.
- **Cost:** Total monthly cost must be $0. All services must remain within free tier limits.

---

## 4. Technology Stack

| Component | Technology | Free Tier Limit |
|---|---|---|
| Language | Python 3.11 | — |
| RSS parsing | `feedparser` | Unlimited |
| News API (optional) | NewsAPI.org | 100 req/day |
| AI summarization | Groq API | ~14,400 req/day |
| LLM model | `llama-3.1-8b-instant` via Groq | Included in Groq free tier |
| HTTP client | `httpx` | — |
| Weekly storage | JSON file in repository | — |
| Teams delivery | Microsoft Teams Incoming Webhook | Free, native Teams feature |
| Scheduling | GitHub Actions (2 cron workflows) | 2,000 min/month free |
| Secrets management | GitHub Actions Secrets | Free |
| Config format | YAML (`PyYAML`) | — |
| Data validation | `pydantic` | — |
| Testing | `pytest` | — |
| Linting | `ruff` | — |

---

## 5. System Architecture

```
╔══════════════════════════════════════════════════════╗
║  WORKFLOW 1: daily_fetch.yml                         ║
║  Cron: "0 7 * * *"  (every day, 08:00 CET)          ║
╚══════════════════════════╦═══════════════════════════╝
                           ║ triggers
                           ▼
              ┌────────────────────────┐
              │   fetch_and_store.py   │
              │  1. Load config        │
              │  2. Fetch RSS + API    │
              │  3. Filter & score     │
              │  4. Deduplicate        │
              │  5. Append to JSON     │
              │  6. Git commit         │
              └──────────┬─────────────┘
                         │
              ┌──────────▼─────────────┐
              │  data/articles_week.json│  ← accumulates Mon–Sun
              └──────────┬─────────────┘
                         │
╔══════════════════════════════════════════════════════╗
║  WORKFLOW 2: weekly_digest.yml                       ║
║  Cron: "0 7 * * 5"  (Fridays only, 08:00 CET)       ║
╚══════════════════════════╦═══════════════════════════╝
                           ║ triggers (after daily_fetch)
                           ▼
              ┌────────────────────────┐
              │   digest_and_send.py   │
              │  1. Run daily fetch    │
              │  2. Load full week     │
              │  3. Final ranking      │
              │  4. Select top 8–10    │
              │  5. Summarize (Groq)   │
              │  6. Build Adaptive Card│
              │  7. POST to Teams      │
              │  8. Reset JSON → []    │
              │  9. Git commit reset   │
              └──────────┬─────────────┘
                         ▼
              ┌────────────────────────┐
              │  Microsoft Teams       │
              │  Weekly Digest Card    │
              └────────────────────────┘
```

---

## 6. Repository Structure

```
news-digest-bot/
├── .github/
│   └── workflows/
│       ├── ci.yml                   # Runs tests on every push to main
│       ├── daily_fetch.yml          # Runs every day — fetch, score, store
│       └── weekly_digest.yml        # Runs Fridays — rank, summarize, send
├── src/
│   ├── __init__.py
│   ├── fetcher.py                   # RSS + NewsAPI ingestion
│   ├── filter.py                    # Keyword filtering, scoring, geo-priority boost
│   ├── ranker.py                    # Weekly ranking: recency, diversity, geo, score
│   ├── summarizer.py                # Groq API integration + prompt rendering
│   ├── notifier.py                  # Teams Adaptive Card builder + webhook POST
│   ├── storage.py                   # Read/write/reset articles_week.json + git commit
│   └── models.py                    # Pydantic models: Article, Digest
├── data/
│   └── articles_week.json           # Weekly article accumulator (auto-managed)
├── config/
│   └── settings.yaml                # All runtime configuration (no secrets)
├── tests/
│   ├── test_fetcher.py
│   ├── test_filter.py
│   ├── test_ranker.py
│   ├── test_summarizer.py
│   ├── test_notifier.py
│   └── test_storage.py
├── fetch_and_store.py               # Entry point: daily_fetch workflow
├── digest_and_send.py               # Entry point: weekly_digest workflow
├── requirements.txt
└── README.md
```

---

## 7. Data Schema

### Article — Pydantic model (`src/models.py`)

```python
class Article(BaseModel):
    id: str                  # SHA256 of URL (first 12 chars)
    url: str
    title: str
    source_name: str
    category: str            # "ai" | "tech" | "telco" | "orange"
    published_at: datetime
    fetched_at: datetime
    raw_content: str         # excerpt or full text from feed
    relevance_score: float   # computed during filtering
    geo_boost: bool          # True if Spain/Europe keywords matched
    summary: Optional[str]   # populated by Groq on Fridays only
    selected: bool           # True if included in the weekly digest
```

### `data/articles_week.json` structure

```json
{
  "week_start": "2026-05-04",
  "week_end": "2026-05-10",
  "last_updated": "2026-05-07T08:03:21Z",
  "articles": [
    {
      "id": "a1b2c3d4e5f6",
      "url": "https://...",
      "title": "...",
      "source_name": "VentureBeat – AI",
      "category": "ai",
      "published_at": "2026-05-07T06:30:00Z",
      "fetched_at": "2026-05-07T08:01:45Z",
      "raw_content": "...",
      "relevance_score": 2.85,
      "geo_boost": false,
      "summary": null,
      "selected": false
    }
  ]
}
```

> **Migration note:** This schema maps directly to the v2 SQLite `articles` table (section 16). No data transformation will be required — migration is a single import script.

---

## 8. Configuration Schema (`config/settings.yaml`)

```yaml
schedule:
  lookback_hours: 24
  max_articles_per_source: 3

  weekly_digest:
    max_articles_total: 10
    min_per_category: 1          # guarantee at least 1 article per category if available

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
    - name: "TechCrunch – AI"
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

    - name: "Fierce Network"
      url: "https://www.fierce-network.com/rss/xml"
      category: "telco"

    - name: "TelecomTV"
      url: "https://www.telecomtv.com/content/rss/"
      category: "telco"

    # ── ORANGE BUSINESS ──────────────────────────────────────────────────────
    - name: "Orange Business – Press Releases"
      url: "https://www.orange-business.com/en/rss.xml"
      category: "orange"
      # Fallback: si el feed falla, usar NewsAPI con query "Orange Business"

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
    # Free tier: 100 req/day, development use only

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
      - "GSMA"              # MWC se celebra en Barcelona
      - "European"
      - "Europa"
    boost_score: 1.5        # score multiplier for geo-matched articles

ranking:
  recency_weight: 0.1       # bonus per day of recency (max 0.7 for same-day)
  diversity_bonus: 0.5      # bonus when 3+ sources cover the same topic

summarization:
  model: "llama-3.1-8b-instant"
  max_summary_words: 60
  prompt_template: |
    You are a news analyst for a technology and telecom company based in Spain.
    Summarize the following news article in {max_words} words or less.
    If the article is relevant to Spain or the European market, mention it explicitly.
    Be factual, neutral, and concise. Output only the summary, no preamble.
    Article: {content}

teams:
  card_title: "📡 Weekly Tech & AI Digest"
  card_color: "FF6600"      # Orange brand color
```

---

## 9. Environment Variables (GitHub Secrets)

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Groq API key for LLM summarization |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams Incoming Webhook URL |
| `NEWSAPI_KEY` | NewsAPI key (optional, only if NewsAPI enabled) |
| `GH_PAT` | GitHub Personal Access Token with `repo` write scope (for auto-commit) |

---

## 10. GitHub Actions Workflow Specs

### `daily_fetch.yml` — runs every day

- **Triggers:** `schedule` (cron: `0 7 * * *`), `workflow_dispatch`
- **Runner:** `ubuntu-latest`
- **Steps:**
  1. Checkout repository (using `GH_PAT` to allow push)
  2. Set up Python 3.11
  3. Cache pip dependencies
  4. Install from `requirements.txt`
  5. Run `python fetch_and_store.py`
  6. Commit and push `data/articles_week.json` if changed
  7. On failure: log error, exit with non-zero code

### `weekly_digest.yml` — runs every Friday

- **Triggers:** `schedule` (cron: `0 7 * * 5`), `workflow_dispatch`
- **Runner:** `ubuntu-latest`
- **Steps:**
  1. Checkout repository (using `GH_PAT`)
  2. Set up Python 3.11
  3. Cache pip dependencies
  4. Install from `requirements.txt`
  5. Run `python digest_and_send.py` (includes daily fetch internally)
  6. Commit and push `data/articles_week.json` (reset to `[]`)
  7. On failure: log error, exit with non-zero code (triggers GitHub notification)

### `ci.yml` — runs on every push to `main`

- **Triggers:** `push` to `main`, `pull_request`
- **Steps:** checkout, set up Python, install deps, run `ruff`, run `pytest`

---

## 11. Teams Adaptive Card Format

```
┌──────────────────────────────────────────────────────────┐
│ 📡 Weekly Tech & AI Digest                                │
│ Week of 4–10 May 2026  ·  10 articles  ·  4 categories   │
├──────────────────────────────────────────────────────────┤
│ 🤖 [AI] Título del artículo 1                    🇪🇸      │
│ VentureBeat  ·  Tue 6 May                                 │
│ Resumen generado por IA. Relevante para el mercado        │
│ español porque...                                         │
│ [Leer más →]                                              │
├──────────────────────────────────────────────────────────┤
│ 📡 [TELCO] Título del artículo 2                          │
│ Light Reading  ·  Wed 7 May                               │
│ Resumen...                                                │
│ [Leer más →]                                              │
├──────────────────────────────────────────────────────────┤
│ 🟠 [ORANGE] Título del artículo 3                         │
│ Orange Newsroom  ·  Thu 8 May                             │
│ ...                                                       │
└──────────────────────────────────────────────────────────┘
```

Category icons: 🤖 AI · 💻 Tech · 📡 Telco · 🟠 Orange Business.
Geo-boosted articles display a 🇪🇸 badge.
Payload: `application/json` POST using `attachments` with `contentType: application/vnd.microsoft.card.adaptive`.

---

## 12. Error Handling Strategy

| Failure scenario | Behavior |
|---|---|
| RSS feed unreachable | Log WARNING, skip source, continue with others |
| NewsAPI quota exceeded | Log WARNING, skip NewsAPI, continue with RSS only |
| Groq API error / timeout | Retry 3× with exponential backoff; fallback to raw excerpt |
| Groq rate limit hit | Wait and retry; if persistent, skip summarization for that article |
| Teams webhook failure | Retry 3×; log ERROR and exit with code 1 if all retries fail |
| No articles found (daily) | Log WARNING, commit empty append, no Teams notification |
| No articles for the week (Friday) | Send minimal "no news this week" card to Teams |
| JSON write failure | Log ERROR, exit with code 1, do not commit |
| Git commit failure | Log WARNING, continue — next run will include pending articles |
| Config file missing | Exit with code 1 with descriptive error message |

---

## 13. Testing Requirements

- Unit tests for each module in `src/` with mocked external calls.
- Test coverage target: ≥ 80%.
- Tests run via `ci.yml` on every push to `main`.
- Key test cases:
  - `test_fetcher`: valid RSS parsing, malformed feed handling, URL deduplication
  - `test_filter`: keyword inclusion/exclusion, date filtering, geo-boost scoring
  - `test_ranker`: ranking order, category balance enforcement, diversity bonus
  - `test_summarizer`: successful summarization, API failure fallback, prompt rendering, Spain context injection
  - `test_notifier`: Adaptive Card JSON structure, geo flag badge, webhook retry logic
  - `test_storage`: JSON read/write/reset, schema validation, duplicate detection

---

## 14. Definition of Done

A feature or epic is considered done when:
1. Code is implemented and passes linting (`ruff`).
2. Unit tests are written and pass (`pytest`), coverage ≥ 80%.
3. The feature works end-to-end in a GitHub Actions manual (`workflow_dispatch`) run.
4. No secrets are exposed in logs or config files.
5. `README.md` is updated with any new configuration options.

---

## 15. Out of Scope (v1)

- Web UI or trends dashboard
- SQLite or any external database
- Historical trend analysis
- User subscriptions or per-recipient personalization
- Non-RSS sources (scrapers, Telegram, Twitter/X)
- Multi-channel or multi-team delivery
- Article translation
- Copilot Studio / Power Platform integration

---

## 16. V2 Roadmap — Trends Dashboard

> This section defines the planned v2 evolution. It is included here so that the v1 JSON schema (section 7) is designed for zero-friction migration to SQLite — no data transformation will be needed.

### Goal
Replace `articles_week.json` with a persistent SQLite database and add a web application to visualize topic trends over time.

### Additional stack (v2, all free)

| Component | Technology | Free Tier |
|---|---|---|
| Database | SQLite (persisted as GitHub artifact or repo file) | Free |
| Web framework | FastAPI + Jinja2 | Free |
| Charts | Chart.js (frontend) | Free |
| Hosting | Render.com | 750h/month free |

### SQLite schema (maps directly from v1 JSON — import is a straight 1:1 mapping)

```sql
CREATE TABLE articles (
    id               TEXT PRIMARY KEY,
    url              TEXT UNIQUE NOT NULL,
    title            TEXT NOT NULL,
    source_name      TEXT NOT NULL,
    category         TEXT NOT NULL,       -- ai / tech / telco / orange
    published_at     DATETIME NOT NULL,
    fetched_at       DATETIME NOT NULL,
    raw_content      TEXT,
    relevance_score  REAL,
    geo_boost        INTEGER DEFAULT 0,   -- boolean as int
    summary          TEXT,
    selected         INTEGER DEFAULT 0    -- boolean as int
);

CREATE TABLE digests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start   DATE NOT NULL,
    week_end     DATE NOT NULL,
    sent_at      DATETIME NOT NULL,
    article_ids  TEXT NOT NULL            -- JSON array of article IDs
);

CREATE TABLE article_keywords (
    article_id   TEXT REFERENCES articles(id),
    keyword      TEXT NOT NULL,
    frequency    INTEGER DEFAULT 1
);
```

### Planned trend visualizations
- **Topics in ascent:** keywords appearing more this week vs. 4-week rolling average.
- **Category share over time:** % of weekly digest per category (AI / Tech / Telco / Orange).
- **Source coverage map:** which sources contribute most per topic.
- **Spain/Europe relevance ratio:** % of geo-boosted articles per week.
- **Digest archive:** browse and search any past weekly digest.

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from src.models import Article
from src.publisher import build_digest_payload, publish_digest


def _sample_articles() -> list[Article]:
    return [
        Article(
            title="Weekly digest item",
            url="https://example.com/item",
            source_name="Feed A",
            published_date=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
            raw_content="Content",
            category="tech",
            summary="Summary text",
        )
    ]


def test_build_digest_payload_counts_categories() -> None:
    payload = build_digest_payload(_sample_articles(), "2026-05-11 / 2026-05-17")

    assert payload["week"] == "2026-05-11 / 2026-05-17"
    assert payload["total_articles"] == 1
    assert payload["categories"] == {"tech": 1}
    assert payload["articles"][0]["title"] == "Weekly digest item"


def test_publish_digest_logs_response_preview_on_success(monkeypatch, caplog) -> None:
    request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(202, request=request, json={"result": "accepted", "tracking": "ok"})
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: dict, timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("src.publisher.httpx.post", fake_post)

    with caplog.at_level("INFO"):
        publish_digest(_sample_articles(), "2026-05-11 / 2026-05-17", "https://example.com/hook")

    assert captured["url"] == "https://example.com/hook"
    assert captured["payload"]["week"] == "2026-05-11 / 2026-05-17"
    assert "Response preview" in caplog.text
    assert "accepted" in caplog.text


def test_publish_digest_logs_response_preview_on_http_error(monkeypatch, caplog) -> None:
    request = httpx.Request("POST", "https://example.com/hook")
    response = httpx.Response(400, request=request, json={"error": {"message": "bad request"}})

    def fake_post(_: str, *, json: dict, timeout: float) -> httpx.Response:
        return response

    monkeypatch.setattr("src.publisher.httpx.post", fake_post)

    with caplog.at_level("WARNING"):
        try:
            publish_digest(_sample_articles(), "2026-05-11 / 2026-05-17", "https://example.com/hook")
        except RuntimeError:
            pass

    assert "Response preview" in caplog.text
    assert "bad request" in caplog.text
"""analysis.py 純邏輯測試:區間解析 + AI 請求/回應組裝 + 資料段落。全綠才可發佈。"""
from datetime import date, datetime, timedelta, timezone

import pytest

import analysis as an


TODAY = date(2026, 7, 1)


# ---------- resolve_fetch_spec ----------
def test_spec_preset_interval_and_visible_start():
    s = an.resolve_fetch_spec("天", today=TODAY)
    assert s["interval"] == "1d"
    assert s["key"] == "天"
    # 顯示 30 天,可見起點為 today-30d
    assert s["visible_start"] == (TODAY - timedelta(days=30)).isoformat()


def test_spec_preset_fetches_warmup_before_visible():
    # 「月」顯示 5 年月線,但要往前多抓 WARMUP_DAYS['1mo'] 讓 MA60 暖身
    s = an.resolve_fetch_spec("月", today=TODAY)
    assert s["interval"] == "1mo"
    visible_start = TODAY - timedelta(days=1825)
    fetch_start = visible_start - timedelta(days=an.WARMUP_DAYS["1mo"])
    p1 = int(datetime(fetch_start.year, fetch_start.month, fetch_start.day, tzinfo=timezone.utc).timestamp())
    assert f"period1={p1}" in s["query"]
    assert s["visible_start"] == visible_start.isoformat()


def test_spec_unknown_preset_is_none():
    assert an.resolve_fetch_spec("不存在", today=TODAY) is None


def test_spec_custom_short_span_uses_hourly():
    s = an.resolve_fetch_spec("天", "2026-06-28", "2026-07-01", today=TODAY)
    assert "interval=60m" in s["query"]
    assert s["visible_start"] == "2026-06-28"


def test_spec_custom_year_uses_daily_with_year_fmt():
    s = an.resolve_fetch_spec("天", "2025-01-01", "2025-12-31", today=TODAY)
    assert "interval=1d" in s["query"]
    assert s["fmt"] == "%Y/%m/%d"


def test_spec_custom_multiyear_uses_weekly():
    s = an.resolve_fetch_spec("天", "2020-01-01", "2026-01-01", today=TODAY)
    assert "interval=1wk" in s["query"]


def test_spec_custom_inclusive_end_and_warmup():
    s = an.resolve_fetch_spec("天", "2026-01-01", "2026-07-01", today=TODAY)
    fetch_start = date(2026, 1, 1) - timedelta(days=an.WARMUP_DAYS["1d"])
    p1 = int(datetime(fetch_start.year, fetch_start.month, fetch_start.day, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2026, 7, 2, tzinfo=timezone.utc).timestamp())  # end + 1 day
    assert f"period1={p1}" in s["query"]
    assert f"period2={p2}" in s["query"]


def test_spec_custom_reversed_dates_are_swapped():
    s = an.resolve_fetch_spec("天", "2026-07-01", "2026-01-01", today=TODAY)
    assert s["visible_start"] == "2026-01-01"


# ---------- build_ai_request ----------
def test_build_claude_request():
    url, headers, body = an.build_ai_request("claude", "claude-sonnet-5", "KEY", "hi")
    assert url.endswith("/v1/messages")
    assert headers["x-api-key"] == "KEY"
    assert headers["anthropic-version"]
    assert body["model"] == "claude-sonnet-5"
    assert body["messages"][0]["content"] == "hi"


def test_build_openai_request():
    url, headers, body = an.build_ai_request("openai", "gpt-4o", "KEY", "hi")
    assert "openai.com" in url
    assert headers["Authorization"] == "Bearer KEY"
    assert body["messages"][0]["content"] == "hi"


def test_build_gemini_request_puts_key_in_header():
    """Gemini 金鑰改走 x-goog-api-key header,不得出現在 URL(URL 會被記進 log/歷程)。"""
    url, headers, body = an.build_ai_request("gemini", "gemini-2.5-flash", "KEY", "hi")
    assert "KEY" not in url
    assert headers["x-goog-api-key"] == "KEY"
    assert body["contents"][0]["parts"][0]["text"] == "hi"


# ---------- resolve_models (deprecated-model migration) ----------
def test_default_gemini_model_is_not_deprecated():
    assert an.PROVIDER_MODELS["gemini"] not in an.DEPRECATED_MODELS


def test_resolve_models_uses_defaults_when_empty():
    m = an.resolve_models({})
    assert m["gemini"] == an.PROVIDER_MODELS["gemini"]
    assert m["claude"] == an.PROVIDER_MODELS["claude"]


def test_resolve_models_drops_deprecated_gemini_id():
    # 舊設定檔可能釘住已停用的 gemini-1.5-flash -> 應回退到最新預設
    m = an.resolve_models({"gemini": "gemini-1.5-flash"})
    assert m["gemini"] == an.PROVIDER_MODELS["gemini"]


def test_resolve_models_keeps_valid_custom_override():
    m = an.resolve_models({"gemini": "gemini-3.5-flash", "openai": "gpt-4o-mini"})
    assert m["gemini"] == "gemini-3.5-flash"
    assert m["openai"] == "gpt-4o-mini"


def test_build_unknown_provider_raises():
    with pytest.raises(ValueError):
        an.build_ai_request("grok", "m", "k", "p")


# ---------- parse_ai_response ----------
def test_parse_claude():
    assert an.parse_ai_response("claude", {"content": [{"type": "text", "text": " ok "}]}) == "ok"


def test_parse_openai():
    assert an.parse_ai_response("openai", {"choices": [{"message": {"content": "buy"}}]}) == "buy"


def test_parse_gemini():
    data = {"candidates": [{"content": {"parts": [{"text": "hold"}]}}]}
    assert an.parse_ai_response("gemini", data) == "hold"


# ---------- build_context_text ----------
def test_context_includes_price_and_indicators():
    quote = {"price": 100.0, "changePct": 1.23}
    detail = {
        "overlays": {"sma_20": [None, 98.0, 99.0]},
        "panels": {
            "kd": {"series": {"K": [None, 60.0], "D": [None, 55.0]}},
            "rsi": {"series": {"RSI": [None, 62.0]}},
        },
    }
    txt = an.build_context_text("AAPL", quote, detail)
    assert "AAPL" in txt
    assert "100.00" in txt
    assert "MA20=99.00" in txt
    assert "K=60.0" in txt
    assert "RSI(14)=62.0" in txt

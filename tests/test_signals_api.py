"""api.signals_from_ohlcv 純函式測試:從 _ohlcv payload 取技術訊號,供黃金頁徽章使用。"""
import api


def test_signals_from_ohlcv_error_or_empty_returns_empty():
    assert api.signals_from_ohlcv({"error": "boom"}) == []
    assert api.signals_from_ohlcv(None) == []
    assert api.signals_from_ohlcv({}) == []


def test_signals_from_ohlcv_delegates_to_detect_all():
    """有效 OHLCV → 回傳 detect_all 的訊號清單(每筆含 dir/label,與前端 renderSignals 一致)。"""
    n = 80
    close = [100 + i for i in range(n)]                      # 穩定上升,觸發多頭類訊號
    payload = {"open": close[:], "high": [c + 1 for c in close],
               "low": [c - 1 for c in close], "close": close, "volume": [1000] * n}
    out = api.signals_from_ohlcv(payload)
    assert isinstance(out, list)
    for s in out:
        assert "dir" in s and "label" in s
        assert s["dir"] in ("bullish", "bearish", "neutral")
    # 穩定上升序列應至少偵測到一個多頭訊號(均線多頭排列)
    assert any(s["dir"] == "bullish" for s in out)

"""api.normalize_ohlcv 純資料處理測試:Yahoo OHLCV 序列的 None 列剔除與 volume 補 0。

Yahoo 回傳常含 None:停牌造成中段 None、正在形成的當日 bar 尾端 None、
或 close 有值但 volume 缺失。normalize_ohlcv 統一處理,讓 RSI/OBV 等指標
不會因單一 None 整條消失。

另含 format_labels 的時區測試(小時線標籤需以交易所當地時區顯示)。
"""
import datetime as _dt

import api


def _epoch(y, mo, d, h, mi):
    return int(_dt.datetime(y, mo, d, h, mi, tzinfo=_dt.timezone.utc).timestamp())


def base_payload():
    return {
        "error": None,
        "ts":     [1, 2, 3, 4],
        "labels": ["a", "b", "c", "d"],
        "open":   [10.0, 20.0, 30.0, 40.0],
        "high":   [11.0, 21.0, 31.0, 41.0],
        "low":    [9.0, 19.0, 29.0, 39.0],
        "close":  [10.5, 20.5, 30.5, 40.5],
        "volume": [100.0, 200.0, 300.0, 400.0],
    }


def test_mid_none_row_removed():
    """中段 close=None(停牌)→ 整列剔除,其餘欄位同步對齊。"""
    p = base_payload()
    p["close"][1] = None
    out = api.normalize_ohlcv(p)
    assert out["close"] == [10.5, 30.5, 40.5]
    assert out["ts"] == [1, 3, 4]
    assert out["labels"] == ["a", "c", "d"]
    assert out["open"] == [10.0, 30.0, 40.0]
    assert out["high"] == [11.0, 31.0, 41.0]
    assert out["low"] == [9.0, 29.0, 39.0]
    assert out["volume"] == [100.0, 300.0, 400.0]


def test_tail_none_forming_bar_removed():
    """尾端 close=None(正在形成的當日 bar)→ 剔除;volume 同為 None 也一併移除。"""
    p = base_payload()
    p["close"][-1] = None
    p["volume"][-1] = None
    out = api.normalize_ohlcv(p)
    assert out["close"] == [10.5, 20.5, 30.5]
    assert out["ts"] == [1, 2, 3]
    assert len(out["close"]) == len(out["volume"]) == 3


def test_volume_none_with_close_becomes_zero():
    """close 存在但 volume=None → volume 補 0,該列保留。"""
    p = base_payload()
    p["volume"][2] = None
    out = api.normalize_ohlcv(p)
    assert out["volume"] == [100.0, 200.0, 0, 400.0]
    assert out["close"] == [10.5, 20.5, 30.5, 40.5]


def test_all_arrays_stay_aligned():
    """任意 None 剔除後,所有欄位長度必須一致(供下游平行索引使用)。"""
    p = base_payload()
    p["close"][0] = None
    out = api.normalize_ohlcv(p)
    n = len(out["close"])
    for k in ("ts", "labels", "open", "high", "low", "close", "volume"):
        assert len(out[k]) == n


def test_error_payload_passthrough():
    """有 error 的 payload 原樣返回,不嘗試處理。"""
    p = {"error": "boom"}
    assert api.normalize_ohlcv(p) == {"error": "boom"}


# ---------- format_labels 時區 ----------
def test_hour_label_uses_exchange_local_time():
    """台股 09:00 開盤 = UTC 01:00;gmtoffset=28800(+8h)後標籤應為當地 09:00。"""
    ts = _epoch(2026, 1, 5, 1, 0)
    assert api.format_labels([ts], "%m/%d %H:%M", 28800) == ["01/05 09:00"]


def test_hour_label_utc_when_no_offset():
    """無偏移(gmtoffset=0)時標籤即 UTC 時間。"""
    ts = _epoch(2026, 1, 5, 1, 0)
    assert api.format_labels([ts], "%m/%d %H:%M", 0) == ["01/05 01:00"]


def test_daily_label_unaffected_by_offset():
    """日線 fmt 不含時間,台股偏移不跨日 → 結果不變。"""
    ts = _epoch(2026, 1, 5, 1, 0)
    assert api.format_labels([ts], "%m/%d", 28800) == ["01/05"]
    assert api.format_labels([ts], "%m/%d", 0) == ["01/05"]

"""
技術訊號偵測 — 純函式,輸入指標 / OHLC 序列,輸出訊號清單,不做任何 I/O。

訊號格式:{"key", "dir", "label", "note"};dir ∈ bullish / bearish / neutral。
偵測邏輯:交叉類看「最近 lookback 根 K 棒內」是否發生(避免只在當根成立、隔天就消失);
狀態類(RSI 區間、布林、均線排列)看最新一根。序列以「舊 → 新」排列。
訊號定義由 Trader 職位把關;指標公式見 references/indicators.md。
"""
from typing import List, Optional

import indicators as ind

Num = Optional[float]
Signal = dict


def _last(seq) -> Num:
    """回傳序列最後一個非 None 值。"""
    for v in reversed(seq or []):
        if v is not None:
            return v
    return None


def _cross(a: List[Num], b: List[Num], lookback: int = 3) -> Optional[str]:
    """最近 lookback 根內 a 相對 b 的最新交叉方向:'up'(上穿)/ 'down'(下穿),否則 None。"""
    n = len(a)
    last = None
    for i in range(1, n):
        if a[i] is None or b[i] is None or a[i - 1] is None or b[i - 1] is None:
            continue
        prev, cur = a[i - 1] - b[i - 1], a[i] - b[i]
        if prev <= 0 and cur > 0:
            last = (i, "up")
        elif prev >= 0 and cur < 0:
            last = (i, "down")
    if last and last[0] >= n - lookback:
        return last[1]
    return None


def _zero_cross(series: List[Num], lookback: int = 3) -> Optional[str]:
    """最近 lookback 根內序列穿越 0 的方向('up' 翻正 / 'down' 翻負)。"""
    n = len(series)
    last = None
    for i in range(1, n):
        if series[i] is None or series[i - 1] is None:
            continue
        if series[i - 1] <= 0 and series[i] > 0:
            last = (i, "up")
        elif series[i - 1] >= 0 and series[i] < 0:
            last = (i, "down")
    if last and last[0] >= n - lookback:
        return last[1]
    return None


def detect_ma(sma_short: List[Num], sma_long: List[Num], lookback: int = 3) -> Optional[Signal]:
    """均線:近期黃金/死亡交叉優先,否則回報目前多頭/空頭排列。"""
    cr = _cross(sma_short, sma_long, lookback)
    if cr == "up":
        return {"key": "ma_golden", "dir": "bullish", "label": "黃金交叉", "note": "短均線上穿長均線"}
    if cr == "down":
        return {"key": "ma_death", "dir": "bearish", "label": "死亡交叉", "note": "短均線下穿長均線"}
    s, lng = _last(sma_short), _last(sma_long)
    if s is None or lng is None:
        return None
    if s > lng:
        return {"key": "ma_bull", "dir": "bullish", "label": "均線多頭排列", "note": "短均線在長均線之上"}
    if s < lng:
        return {"key": "ma_bear", "dir": "bearish", "label": "均線空頭排列", "note": "短均線在長均線之下"}
    return None


def detect_kd(kd_k: List[Num], kd_d: List[Num], lookback: int = 3) -> Optional[Signal]:
    """KD 金叉 / 死叉;低檔金叉、高檔死叉訊號較強。"""
    cr = _cross(kd_k, kd_d, lookback)
    k = _last(kd_k)
    if cr == "up":
        low = k is not None and k < 30
        return {"key": "kd_golden", "dir": "bullish",
                "label": "KD 低檔金叉" if low else "KD 金叉", "note": "K 上穿 D"}
    if cr == "down":
        high = k is not None and k > 70
        return {"key": "kd_death", "dir": "bearish",
                "label": "KD 高檔死叉" if high else "KD 死叉", "note": "K 下穿 D"}
    return None


def detect_rsi(rsi: List[Num], overbought: float = 70, oversold: float = 30) -> Optional[Signal]:
    """RSI 超買(回檔風險)/ 超賣(反彈機會)。"""
    r = _last(rsi)
    if r is None:
        return None
    if r >= overbought:
        return {"key": "rsi_ob", "dir": "bearish", "label": f"RSI 超買 {r:.0f}", "note": "回檔風險偏高"}
    if r <= oversold:
        return {"key": "rsi_os", "dir": "bullish", "label": f"RSI 超賣 {r:.0f}", "note": "反彈機會偏高"}
    return None


def detect_macd(macd_hist: List[Num], lookback: int = 3) -> Optional[Signal]:
    """MACD 柱體翻正 / 翻負(等同 MACD 線穿越訊號線)。"""
    z = _zero_cross(macd_hist, lookback)
    if z == "up":
        return {"key": "macd_up", "dir": "bullish", "label": "MACD 柱翻正", "note": "動能轉多"}
    if z == "down":
        return {"key": "macd_down", "dir": "bearish", "label": "MACD 柱翻負", "note": "動能轉空"}
    return None


def detect_bollinger(closes: List[Num], upper: List[Num], lower: List[Num]) -> Optional[Signal]:
    """收盤突破布林上軌(強勢/過熱)或跌破下軌(弱勢/超跌)。"""
    c, u, lo = _last(closes), _last(upper), _last(lower)
    if c is None or u is None or lo is None:
        return None
    if c > u:
        return {"key": "boll_up", "dir": "bullish", "label": "突破布林上軌", "note": "強勢,惟留意過熱"}
    if c < lo:
        return {"key": "boll_down", "dir": "bearish", "label": "跌破布林下軌", "note": "弱勢,惟留意超跌"}
    return None


def detect_gap(highs: List[Num], lows: List[Num]) -> Optional[Signal]:
    """跳空:今日最低 > 昨日最高(向上)或今日最高 < 昨日最低(向下)。"""
    if len(highs) < 2 or len(lows) < 2:
        return None
    h1, l1, h0, l0 = highs[-1], lows[-1], highs[-2], lows[-2]
    if None in (h1, l1, h0, l0):
        return None
    if l1 > h0:
        return {"key": "gap_up", "dir": "bullish", "label": "向上跳空", "note": "今低 > 昨高"}
    if h1 < l0:
        return {"key": "gap_down", "dir": "bearish", "label": "向下跳空", "note": "今高 < 昨低"}
    return None


def detect_all(opens: List[Num], highs: List[Num], lows: List[Num],
               closes: List[Num], volumes: List[Num] = None) -> List[Signal]:
    """由 OHLC 計算標準指標(MA20/60、KD、RSI、MACD、布林)並偵測所有訊號,回傳清單(可能為空)。"""
    sma_short = ind.sma(closes, 20)
    sma_long = ind.sma(closes, 60)
    kd_k, kd_d = ind.stochastic_kd(highs, lows, closes)
    rsi = ind.rsi(closes)
    _, _, macd_hist = ind.macd(closes)
    upper, _, lower = ind.bollinger(closes)
    candidates = (
        detect_ma(sma_short, sma_long),
        detect_kd(kd_k, kd_d),
        detect_rsi(rsi),
        detect_macd(macd_hist),
        detect_bollinger(closes, upper, lower),
        detect_gap(highs, lows),
    )
    return [s for s in candidates if s]

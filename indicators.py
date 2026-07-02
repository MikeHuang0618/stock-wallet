"""
技術指標計算 — 純函式,不做任何 I/O 或繪圖。
所有序列以「舊 → 新」排列。暖身期 (資料不足) 一律回傳 None,絕不丟例外。
公式與標準參數見 references/indicators.md(fintech-ta-engineer skill)。
"""
from typing import List, Optional, Tuple

Num = Optional[float]


def sma(values: List[Num], period: int) -> List[Num]:
    """簡單移動平均。視窗內含 None 或資料不足 → None。"""
    if period <= 0:
        raise ValueError("period must be positive")
    out: List[Num] = [None] * len(values)
    for i in range(len(values)):
        if i < period - 1:
            continue
        window = values[i - period + 1: i + 1]
        if any(v is None for v in window):
            continue
        out[i] = sum(window) / period
    return out


def _ema_raw(values: List[float], period: int) -> List[Num]:
    """對純數值序列 (無 None) 計算 EMA,以前 period 筆 SMA 作種子。"""
    n = len(values)
    out: List[Num] = [None] * n
    if n < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def ema(values: List[Num], period: int) -> List[Num]:
    """指數移動平均。自第一個連續數值區塊開始計算,前置 None 保留對齊。"""
    if period <= 0:
        raise ValueError("period must be positive")
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None:
        return [None] * len(values)
    tail = values[start:]
    if any(v is None for v in tail):
        # 中段若有缺值則只取最後一段連續數值
        last_gap = max(i for i, v in enumerate(tail) if v is None)
        tail = tail[last_gap + 1:]
        start += last_gap + 1
    raw = _ema_raw([float(v) for v in tail], period)
    return [None] * start + raw


def rsi(closes: List[Num], period: int = 14) -> List[Num]:
    """Wilder RSI。需要 period+1 筆收盤價。全跌 → 0,全漲 → 100。"""
    if period <= 0:
        raise ValueError("period must be positive")
    n = len(closes)
    out: List[Num] = [None] * n
    if n < period + 1 or any(c is None for c in closes):
        return out
    gains, losses = [], []
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_from(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def stochastic_kd(highs: List[Num], lows: List[Num], closes: List[Num],
                  n: int = 9, k_smooth: int = 3, d_smooth: int = 3
                  ) -> Tuple[List[Num], List[Num]]:
    """KD 隨機指標。價格區間為 0 (highest==lowest) 時沿用前值,避免除以零。"""
    size = len(closes)
    raw_k: List[Num] = [None] * size
    prev_rawk: Optional[float] = None
    for i in range(size):
        if i < n - 1:
            continue
        c = closes[i]
        w_h = highs[i - n + 1: i + 1]
        w_l = lows[i - n + 1: i + 1]
        if c is None or any(x is None for x in w_h) or any(x is None for x in w_l):
            continue
        hh = max(w_h)
        ll = min(w_l)
        rng = hh - ll
        if rng == 0:
            raw_k[i] = prev_rawk if prev_rawk is not None else 50.0
        else:
            raw_k[i] = 100 * (c - ll) / rng
        prev_rawk = raw_k[i]
    kd_k = sma(raw_k, k_smooth)
    kd_d = sma(kd_k, d_smooth)
    return kd_k, kd_d


def macd(closes: List[Num], fast: int = 12, slow: int = 26, signal: int = 9
         ) -> Tuple[List[Num], List[Num], List[Num]]:
    """MACD。回傳 (macd_line, signal_line, hist)。"""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: List[Num] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    signal_line = ema(macd_line, signal)
    hist: List[Num] = [
        (m - g) if (m is not None and g is not None) else None
        for m, g in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def bollinger(closes: List[Num], period: int = 20, num_std: float = 2.0
              ) -> Tuple[List[Num], List[Num], List[Num]]:
    """布林通道。回傳 (upper, mid, lower),使用母體標準差。"""
    mid = sma(closes, period)
    upper: List[Num] = [None] * len(closes)
    lower: List[Num] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is None:
            continue
        window = closes[i - period + 1: i + 1]
        mean = mid[i]
        var = sum((v - mean) ** 2 for v in window) / period
        sd = var ** 0.5
        upper[i] = mean + num_std * sd
        lower[i] = mean - num_std * sd
    return upper, mid, lower


def obv(closes: List[Num], volumes: List[Num]) -> List[Num]:
    """能量潮 OBV。第一筆基準為 0。"""
    out: List[Num] = [None] * len(closes)
    if not closes or any(c is None for c in closes) or any(v is None for v in volumes):
        return out
    running = 0.0
    out[0] = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            running += volumes[i]
        elif closes[i] < closes[i - 1]:
            running -= volumes[i]
        out[i] = running
    return out

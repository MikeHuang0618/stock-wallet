"""技術訊號偵測 golden tests:每個偵測器對照手算序列;涵蓋交叉、狀態、lookback、邊界。"""
import signals as sg


# ---------- 均線 MA ----------
def test_ma_golden_cross():
    s = sg.detect_ma([1, 1, 3], [2, 2, 2])       # 第 3 根:短線由下(-1)穿到上(+1)
    assert s["key"] == "ma_golden" and s["dir"] == "bullish"


def test_ma_death_cross():
    s = sg.detect_ma([3, 3, 1], [2, 2, 2])
    assert s["key"] == "ma_death" and s["dir"] == "bearish"


def test_ma_bull_alignment_when_no_recent_cross():
    s = sg.detect_ma([3, 3, 3], [2, 2, 2])       # 無交叉,短 > 長
    assert s["key"] == "ma_bull"


def test_ma_bear_alignment():
    assert sg.detect_ma([1, 1, 1], [2, 2, 2])["key"] == "ma_bear"


def test_ma_cross_outside_lookback_falls_back_to_trend():
    # 交叉發生在第 2 根,但 lookback=2 只看最後 2 根 → 視為非近期交叉,回報排列
    s = sg.detect_ma([1, 3, 3, 3, 3], [2, 2, 2, 2, 2], lookback=2)
    assert s["key"] == "ma_bull"


def test_ma_none_when_insufficient():
    assert sg.detect_ma([None, None], [None, None]) is None


# ---------- KD ----------
def test_kd_low_golden_cross_is_stronger():
    s = sg.detect_kd([10, 10, 25], [20, 20, 20])   # 上穿且 K=25<30
    assert s["key"] == "kd_golden" and "低檔" in s["label"]


def test_kd_plain_golden_cross():
    s = sg.detect_kd([40, 40, 55], [50, 50, 50])   # 上穿但 K=55 非低檔
    assert s["key"] == "kd_golden" and "低檔" not in s["label"]


def test_kd_high_death_cross():
    s = sg.detect_kd([90, 90, 75], [80, 80, 80])   # 下穿且 K=75>70
    assert s["key"] == "kd_death" and "高檔" in s["label"]


def test_kd_none_when_no_cross():
    assert sg.detect_kd([50, 50, 50], [40, 40, 40]) is None


# ---------- RSI ----------
def test_rsi_overbought():
    s = sg.detect_rsi([None, 50, 75])
    assert s["key"] == "rsi_ob" and s["dir"] == "bearish" and "75" in s["label"]


def test_rsi_oversold():
    assert sg.detect_rsi([None, 50, 25])["key"] == "rsi_os"


def test_rsi_neutral_is_none():
    assert sg.detect_rsi([50, 50, 55]) is None


# ---------- MACD ----------
def test_macd_hist_turns_positive():
    assert sg.detect_macd([-1, -1, 0.5])["key"] == "macd_up"


def test_macd_hist_turns_negative():
    assert sg.detect_macd([1, 1, -0.5])["key"] == "macd_down"


def test_macd_no_zero_cross_is_none():
    assert sg.detect_macd([1, 1, 2]) is None


# ---------- 布林 ----------
def test_bollinger_break_up():
    assert sg.detect_bollinger([100, 110], [104, 105], [95, 95])["key"] == "boll_up"


def test_bollinger_break_down():
    assert sg.detect_bollinger([100, 90], [105, 105], [95, 95])["key"] == "boll_down"


def test_bollinger_inside_is_none():
    assert sg.detect_bollinger([100, 100], [105, 105], [95, 95]) is None


# ---------- 跳空 ----------
def test_gap_up():
    assert sg.detect_gap([10, 15], [8, 11])["key"] == "gap_up"     # 今低 11 > 昨高 10


def test_gap_down():
    assert sg.detect_gap([10, 7], [8, 5])["key"] == "gap_down"     # 今高 7 < 昨低 8


def test_gap_none_when_overlap():
    assert sg.detect_gap([10, 11], [8, 9]) is None


# ---------- detect_all 整合 ----------
def test_detect_all_rising_series_flags_overbought():
    closes = list(range(1, 21))          # 嚴格遞增 → RSI = 100 超買
    keys = {s["key"] for s in sg.detect_all(closes, closes, closes, closes)}
    assert "rsi_ob" in keys


def test_detect_all_falling_series_flags_oversold():
    closes = list(range(20, 0, -1))      # 嚴格遞減 → RSI = 0 超賣
    keys = {s["key"] for s in sg.detect_all(closes, closes, closes, closes)}
    assert "rsi_os" in keys


def test_detect_all_empty_is_empty_list():
    assert sg.detect_all([], [], [], []) == []

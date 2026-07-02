"""指標單元測試 — 每個功能對照手算值 + 邊界情況。全綠才可發佈。"""
import pytest

import indicators as ta

A = pytest.approx


# ---------- SMA ----------
def test_sma_basic():
    assert ta.sma([1, 2, 3, 4, 5], 3) == [None, None, A(2), A(3), A(4)]


def test_sma_insufficient_data():
    assert ta.sma([1, 2], 3) == [None, None]


def test_sma_window_with_none_is_none():
    assert ta.sma([1, None, 3, 4], 2) == [None, None, None, A(3.5)]


# ---------- EMA ----------
def test_ema_seeded_with_sma():
    # k=0.5; seed=SMA(1,2,3)=2 -> 3 -> 4
    assert ta.ema([1, 2, 3, 4, 5], 3) == [None, None, A(2), A(3), A(4)]


def test_ema_all_none():
    assert ta.ema([None, None], 3) == [None, None]


# ---------- RSI ----------
def test_rsi_all_gains_is_100():
    out = ta.rsi(list(range(1, 17)), 14)  # strictly increasing
    assert out[13] is None
    assert out[14] == A(100)


def test_rsi_all_losses_is_0():
    out = ta.rsi(list(range(16, 0, -1)), 14)  # strictly decreasing
    assert out[14] == A(0)


def test_rsi_hand_computed_period2():
    # closes 10,11,10,11 -> [None,None,50,75]
    out = ta.rsi([10, 11, 10, 11], 2)
    assert out == [None, None, A(50), A(75)]


# ---------- KD / Stochastic ----------
def test_kd_raw_formula():
    highs = [10, 12, 11, 13]
    lows = [8, 9, 9, 10]
    closes = [9, 11, 10, 12]
    k, d = ta.stochastic_kd(highs, lows, closes, n=3, k_smooth=1, d_smooth=1)
    assert k == [None, None, A(50), A(75)]
    assert d == [None, None, A(50), A(75)]


def test_kd_zero_range_no_divide_error():
    k, _ = ta.stochastic_kd([5, 5, 5], [5, 5, 5], [5, 5, 5], n=2, k_smooth=1, d_smooth=1)
    assert k == [None, A(50), A(50)]


# ---------- MACD ----------
def test_macd_constant_series_is_zero():
    closes = [100] * 40
    macd_line, signal, hist = ta.macd(closes)
    assert macd_line[24] is None and macd_line[25] == A(0)  # slow=26 warmup
    assert hist[-1] == A(0)
    assert signal[-1] == A(0)


# ---------- Bollinger ----------
def test_bollinger_hand_computed():
    upper, mid, lower = ta.bollinger([2, 4, 6, 8], period=2, num_std=1)
    assert mid == [None, A(3), A(5), A(7)]
    assert upper == [None, A(4), A(6), A(8)]
    assert lower == [None, A(2), A(4), A(6)]


# ---------- OBV ----------
def test_obv_hand_computed():
    out = ta.obv([10, 11, 10, 12], [100, 200, 150, 300])
    assert out == [A(0), A(200), A(50), A(350)]


# ---------- guards ----------
def test_non_positive_period_raises():
    with pytest.raises(ValueError):
        ta.sma([1, 2, 3], 0)
    with pytest.raises(ValueError):
        ta.ema([1, 2, 3], -1)

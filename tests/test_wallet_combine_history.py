"""跨幣別合併歷史曲線 combine_history golden tests。
涵蓋:正常折算、fx 前向填補、fx 整段缺失(有台幣→None)、單一幣別。"""
import pytest

import wallet as w

A = pytest.approx


def test_combine_daily_usd_and_twd():
    usd = {"dates": ["2026-01-01", "2026-01-02"], "portfolio_value": [1000, 1100]}
    twd = {"dates": ["2026-01-01", "2026-01-02"], "portfolio_value": [32000, 33000]}
    fx = {"2026-01-01": 32.0, "2026-01-02": 33.0}
    out = w.combine_history(usd, twd, fx)
    assert out["dates"] == ["2026-01-01", "2026-01-02"]
    assert out["portfolio_value"][0] == A(1000 + 32000 / 32)   # 2000
    assert out["portfolio_value"][1] == A(1100 + 33000 / 33)   # 2100


def test_combine_forward_fills_missing_fx():
    usd = {"dates": ["2026-01-01", "2026-01-02"], "portfolio_value": [1000, 1100]}
    twd = {"dates": ["2026-01-01", "2026-01-02"], "portfolio_value": [32000, 33000]}
    fx = {"2026-01-01": 32.0}                       # 01-02 缺 → 沿用 32
    out = w.combine_history(usd, twd, fx)
    assert out["portfolio_value"][1] == A(1100 + 33000 / 32)


def test_combine_fx_entirely_missing_with_twd_is_none():
    usd = {"dates": ["2026-01-01"], "portfolio_value": [1000]}
    twd = {"dates": ["2026-01-01"], "portfolio_value": [32000]}
    out = w.combine_history(usd, twd, {})           # 完全無匯率
    assert out["portfolio_value"] == [None]         # 絕不折成 0


def test_combine_single_currency_ignores_fx():
    usd = {"dates": ["2026-01-01"], "portfolio_value": [1000]}
    twd = {"dates": ["2026-01-01"], "portfolio_value": [0]}
    out = w.combine_history(usd, twd, {})           # 無台幣曝險,fx 缺失無妨
    assert out["portfolio_value"] == [A(1000)]

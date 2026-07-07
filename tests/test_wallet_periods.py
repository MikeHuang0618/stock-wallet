"""期間彙總 summarize_periods + 年度已實現 realized_by_year golden tests。"""
import pytest

import wallet as w

A = pytest.approx


def tx(i, sym, qty, price, date, side="buy"):
    return {"id": i, "symbol": sym, "side": side, "quantity": qty, "price": price, "date": date}


# ---------- summarize_periods ----------
def test_monthly_periods_pnl_excludes_deposits():
    dates = ["2026-01-01", "2026-01-31", "2026-02-15", "2026-02-28"]
    pv = [1000, 1100, 1100, 1300]
    deps = [{"date": "2026-02-10", "amount": 150}]
    out = w.summarize_periods(dates, pv, deps, period="monthly")
    assert [p["period"] for p in out] == ["2026-01", "2026-02"]
    jan, feb = out
    assert jan["start_value"] == A(1000)
    assert jan["end_value"] == A(1100)
    assert jan["pnl"] == A(100)                  # 1100 - 1000 - 0
    assert jan["return_pct"] == A(10.0)
    assert feb["start_value"] == A(1100)         # 連續:接上一期期末
    assert feb["net_deposit"] == A(150)
    assert feb["pnl"] == A(50)                   # 1300 - 1100 - 150
    assert feb["return_pct"] == A(50 / 1250 * 100)   # 分母 = 期初 + 淨投入


def test_yearly_period_grouping():
    dates = ["2025-06-01", "2025-12-31", "2026-06-01"]
    pv = [1000, 1200, 1500]
    out = w.summarize_periods(dates, pv, None, period="yearly")
    assert [p["period"] for p in out] == ["2025", "2026"]
    assert out[1]["start_value"] == A(1200)
    assert out[1]["pnl"] == A(300)


def test_empty_history_returns_empty():
    assert w.summarize_periods([], [], None) == []


# ---------- realized_by_year ----------
def test_realized_by_year_splits_pnl_and_dividends():
    txs = [tx(1, "AAPL", 10, 100, "2025-01-01"),
           tx(2, "AAPL", 10, 130, "2025-06-01", side="sell"),          # 2025 已實現 +300
           tx(3, "NVDA", 5, 100, "2026-01-01"),
           {"id": 4, "symbol": "NVDA", "side": "dividend", "quantity": 0,
            "price": 50, "date": "2026-03-01"},                        # 2026 股息 50
           tx(5, "NVDA", 5, 120, "2026-06-01", side="sell")]           # 2026 已實現 +100
    out = w.realized_by_year(txs)
    assert [r["year"] for r in out] == ["2025", "2026"]
    assert out[0]["realized_pnl"] == A(300)
    assert out[0]["dividends"] == A(0)
    assert out[1]["realized_pnl"] == A(100)
    assert out[1]["dividends"] == A(50)

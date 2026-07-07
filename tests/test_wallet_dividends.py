"""股息(現金股利 + 配股)golden tests。對照手算值,涵蓋向下相容。全綠才可發佈。"""
import pytest

import wallet as w

A = pytest.approx


def tx(i, sym, qty, price, date, side="buy", fee=0.0, name=None):
    return {"id": i, "symbol": sym, "side": side, "quantity": qty,
            "price": price, "date": date, "fee": fee, "name": name}


# ---------- 現金股利 ----------
def test_cash_dividend_accumulates_not_touching_position():
    """買 100 @50,配息總額 200,股價仍 50 → 未實現 0、累計股息 200。"""
    txs = [tx(1, "0056.TW", 100, 50, "2026-01-01"),
           tx(2, "0056.TW", 0, 200, "2026-03-01", side="dividend")]
    agg = w.aggregate_holdings(txs)
    h = agg["holdings"][0]
    assert h["qty"] == A(100)
    assert h["cost_basis"] == A(5000)
    assert h["dividends"] == A(200)
    assert agg["total_dividends"] == A(200)


def test_cash_dividend_enters_portfolio_value_and_return():
    txs = [tx(1, "0056.TW", 100, 50, "2026-01-01"),
           tx(2, "0056.TW", 0, 200, "2026-03-01", side="dividend")]
    h = w.aggregate_holdings(txs)["holdings"][0]
    e = w.enrich_holding(h, {"price": 50.0}, same_day_txs=[])
    s = w.summarize_currency([e], realized_pnl=0.0, deposits_amount=5000.0,
                             dividends_amount=200.0)
    assert s["total_pnl"] == A(0)               # 未實現
    assert s["total_dividends"] == A(200)
    assert s["portfolio_value"] == A(5200)      # 5000 存入 + 0 未實現 + 200 股息
    assert s["portfolio_return_pct"] == A(4.0)  # 200 / 5000


def test_dividend_survives_after_position_closed():
    """收過股息後全數賣出:持倉列表無此標的,但股息仍計入 total 與明細。"""
    txs = [tx(1, "0056.TW", 100, 50, "2026-01-01"),
           tx(2, "0056.TW", 0, 200, "2026-03-01", side="dividend"),
           tx(3, "0056.TW", 100, 50, "2026-06-01", side="sell")]
    agg = w.aggregate_holdings(txs)
    assert agg["holdings"] == []                 # 已平倉不列入
    assert agg["total_dividends"] == A(200)
    detail = w.realized_breakdown(txs)
    assert len(detail) == 1
    assert detail[0]["dividends"] == A(200)
    assert detail[0]["closed"] is True


# ---------- 配股(股票股利) ----------
def test_stock_dividend_adds_shares_and_lowers_avg_cost():
    """買 100 @50(成本 5000)+ 配股 10 股 → qty 110、成本不變、均價 5000/110。"""
    txs = [tx(1, "2412.TW", 100, 50, "2026-01-01"),
           tx(2, "2412.TW", 10, 0, "2026-08-01", side="stock_dividend")]
    h = w.aggregate_holdings(txs)["holdings"][0]
    assert h["qty"] == A(110)
    assert h["cost_basis"] == A(5000)
    assert h["avg_cost"] == A(5000 / 110)


# ---------- 向下相容 ----------
def test_legacy_transactions_without_dividends_unchanged():
    """無任何股息/費用欄位的舊交易:total_dividends=0,每筆 holding 帶 dividends=0。"""
    txs = [{"id": 1, "symbol": "AAPL", "side": "buy", "quantity": 10,
            "price": 100, "date": "2026-01-01"}]
    agg = w.aggregate_holdings(txs)
    assert agg["total_dividends"] == A(0)
    assert agg["holdings"][0]["dividends"] == A(0)

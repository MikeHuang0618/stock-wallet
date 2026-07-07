"""手續費 / 交易稅 golden tests。費用進成本、賣出沖已實現損益;舊資料 fee=0 行為不變。"""
import pytest

import wallet as w

A = pytest.approx


def tx(i, sym, qty, price, date, side="buy", fee=0.0):
    return {"id": i, "symbol": sym, "side": side, "quantity": qty,
            "price": price, "date": date, "fee": fee}


def test_buy_fee_enters_cost_basis():
    txs = [tx(1, "2330.TW", 1000, 100, "2026-01-01", fee=142)]
    h = w.aggregate_holdings(txs)["holdings"][0]
    assert h["cost_basis"] == A(100142)          # 100000 + 142
    assert h["avg_cost"] == A(100.142)


def test_round_trip_fees_reduce_realized_pnl():
    """買 1000 @100 費 142,賣 1000 @110 費 486 → realized = (110-100)*1000 - 142 - 486 = 9372。"""
    txs = [tx(1, "2330.TW", 1000, 100, "2026-01-01", fee=142),
           tx(2, "2330.TW", 1000, 110, "2026-06-01", side="sell", fee=486)]
    agg = w.aggregate_holdings(txs)
    assert agg["holdings"] == []                 # 全平倉
    assert agg["total_realized_pnl"] == A(9372)


def test_missing_fee_field_defaults_zero():
    """舊交易無 fee 欄位:視為 0,數字與未加費用前一致。"""
    txs = [{"id": 1, "symbol": "AAPL", "side": "buy", "quantity": 10,
            "price": 100, "date": "2026-01-01"}]
    assert w.aggregate_holdings(txs)["holdings"][0]["cost_basis"] == A(1000)


def test_estimate_tw_fee_buy_and_sell():
    """買 = 手續費率;賣 = 手續費率 + 證交稅率。"""
    assert w.estimate_tw_fee(100, 1000, "buy") == A(100000 * 0.001425)   # 142.5
    assert w.estimate_tw_fee(110, 1000, "sell") == A(110000 * (0.001425 + 0.003))  # 486.75

"""拆股 / 持股調整 (side=adjust) golden tests。股數變、成本不變、未實現損益連續。"""
import pytest

import wallet as w

A = pytest.approx


def tx(i, sym, qty, price, date, side="buy"):
    return {"id": i, "symbol": sym, "side": side, "quantity": qty, "price": price, "date": date}


def test_forward_split_keeps_cost_basis_and_continuity():
    """100 @900 → 拆股 +900 股 → qty 1000、均價 90、成本不變;拆股前後未實現連續。"""
    txs = [tx(1, "NVDA", 100, 900, "2026-01-01"),
           tx(2, "NVDA", 900, 0, "2026-06-10", side="adjust")]
    h = w.aggregate_holdings(txs)["holdings"][0]
    assert h["qty"] == A(1000)
    assert h["cost_basis"] == A(90000)
    assert h["avg_cost"] == A(90)
    # 拆股前(價 900)與拆股後(價 90)市值皆 90000 → 未實現皆 0,連續無斷崖
    pre = w.enrich_holding({"qty": 100, "cost_basis": 90000}, {"price": 900.0}, [])
    post = w.enrich_holding(h, {"price": 90.0}, [])
    assert pre["pnl"] == A(0)
    assert post["pnl"] == A(0)


def test_reverse_split_reduces_shares():
    """合股:1000 @1 → adjust -900 → qty 100、均價 10、成本不變。"""
    txs = [tx(1, "PENNY", 1000, 1, "2026-01-01"),
           tx(2, "PENNY", -900, 0, "2026-06-10", side="adjust")]
    h = w.aggregate_holdings(txs)["holdings"][0]
    assert h["qty"] == A(100)
    assert h["cost_basis"] == A(1000)
    assert h["avg_cost"] == A(10)

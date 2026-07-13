"""wallet.py 純邏輯測試:持倉彙總 + 歷史市值/損益。全綠才可發佈。"""
import pytest

import wallet as w

A = pytest.approx


def tx(i, sym, qty, price, date, name=None, side="buy"):
    return {"id": i, "symbol": sym, "side": side, "quantity": qty, "price": price, "date": date, "name": name}


# ---------- aggregate_holdings ----------
def test_holdings_average_cost():
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 5, 110, "2026-01-03")]
    result = w.aggregate_holdings(txs)
    h = result["holdings"]
    assert len(h) == 1
    assert h[0]["qty"] == A(15)
    assert h[0]["avg_cost"] == A(1550 / 15)
    assert h[0]["cost_basis"] == A(1550)


def test_holdings_sell_reduces_at_avg_cost():
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 4, 130, "2026-01-05", side="sell")]
    result = w.aggregate_holdings(txs)
    h = result["holdings"]
    assert h[0]["qty"] == A(6)
    assert h[0]["avg_cost"] == A(100)          # 賣出不改變平均成本
    assert h[0]["cost_basis"] == A(600)


def test_fully_closed_position_is_excluded():
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 10, 130, "2026-01-05", side="sell")]
    result = w.aggregate_holdings(txs)
    assert result["holdings"] == []


def test_multiple_symbols():
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "NVDA", 2, 500, "2026-01-02")]
    syms = {h["symbol"] for h in w.aggregate_holdings(txs)["holdings"]}
    assert syms == {"AAPL", "NVDA"}


# ---------- 碎股數量精度 (round 8) ----------
def test_fractional_share_qty_precision():
    """碎股/加密貨幣數量:買入 1.23456789 股,彙總須保留至 8 位小數,不被捨到 6 位。"""
    txs = [tx(1, "BTC", 1.23456789, 30000, "2026-01-01")]
    result = w.aggregate_holdings(txs)
    assert result["holdings"][0]["qty"] == A(1.23456789, abs=1e-8)


def test_fractional_share_qty_sum():
    """分兩筆買入 0.12345678 + 0.11111111,加總精度須正確(不因彙總捨位失真)。"""
    txs = [tx(1, "ETH", 0.12345678, 2000, "2026-01-01"),
           tx(2, "ETH", 0.11111111, 2100, "2026-01-02")]
    result = w.aggregate_holdings(txs)
    assert result["holdings"][0]["qty"] == A(0.23456789, abs=1e-8)


# ---------- realized P&L ----------
def test_realized_pnl_partial_sell():
    """賣 4 股 @130, 成本 100 → 已實現 (130-100)*4 = 120"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 4, 130, "2026-01-05", side="sell")]
    result = w.aggregate_holdings(txs)
    assert result["total_realized_pnl"] == A(120)
    assert result["holdings"][0]["realized_pnl"] == A(120)


def test_realized_pnl_full_close():
    """全數賣出 10 股 @130, 成本 100 → 已實現 (130-100)*10 = 300"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 10, 130, "2026-01-05", side="sell")]
    result = w.aggregate_holdings(txs)
    assert result["total_realized_pnl"] == A(300)
    assert result["holdings"] == []  # 已平倉不列入


def test_realized_pnl_no_sell():
    """無賣出 → 已實現損益為 0"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01")]
    result = w.aggregate_holdings(txs)
    assert result["total_realized_pnl"] == A(0)


# ---------- realized_breakdown ----------
def test_realized_breakdown_includes_closed_position():
    """完全平倉的標的必須出現在明細,且 closed=True(aggregate_holdings 會丟棄它)。"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"),
           tx(2, "AAPL", 10, 130, "2026-01-05", side="sell")]
    detail = w.realized_breakdown(txs)
    assert len(detail) == 1
    assert detail[0]["symbol"] == "AAPL"
    assert detail[0]["closed"] is True
    assert detail[0]["realized_pnl"] == A(300)
    assert detail[0]["last_date"] == "2026-01-05"


def test_realized_breakdown_partial_matches_aggregate():
    """部分平倉標的的 realized_pnl 與 aggregate_holdings 一致,closed=False。"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"),
           tx(2, "AAPL", 4, 130, "2026-01-05", side="sell")]
    detail = w.realized_breakdown(txs)
    agg = w.aggregate_holdings(txs)
    assert len(detail) == 1
    assert detail[0]["closed"] is False
    assert detail[0]["realized_pnl"] == A(120)
    assert detail[0]["realized_pnl"] == A(agg["holdings"][0]["realized_pnl"])


def test_realized_breakdown_no_sell_is_empty():
    """全買未賣 → 無已實現損益 → 空明細。"""
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01")]
    assert w.realized_breakdown(txs) == []


def test_realized_breakdown_sorted_by_abs_desc():
    """依 |realized_pnl| 降冪排序。"""
    txs = [tx(1, "AAA", 10, 100, "2026-01-01"), tx(2, "AAA", 10, 110, "2026-01-02", side="sell"),  # +100
           tx(3, "BBB", 10, 100, "2026-01-01"), tx(4, "BBB", 10, 70, "2026-01-02", side="sell")]   # -300
    detail = w.realized_breakdown(txs)
    assert [d["symbol"] for d in detail] == ["BBB", "AAA"]


# ---------- build_history ----------
def test_history_value_and_daily_pnl():
    txs = [tx(1, "AAPL", 10, 100, "2026-01-01"), tx(2, "AAPL", 5, 110, "2026-01-03")]
    prices = {"AAPL": [("2026-01-01", 100), ("2026-01-02", 105),
                       ("2026-01-03", 110), ("2026-01-04", 120)]}
    hist = w.build_history(txs, prices)
    assert hist["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert hist["total_value"] == [A(1000), A(1050), A(1650), A(1800)]
    assert hist["daily_pnl"] == [A(0), A(50), A(50), A(150)]
    # 每日損益加總 == 未實現損益 (終值 - 投入成本)
    assert sum(hist["daily_pnl"]) == A(1800 - 1550)


def test_history_forward_fills_missing_days():
    txs = [tx(1, "AAPL", 1, 100, "2026-01-01")]
    prices = {"AAPL": [("2026-01-01", 100), ("2026-01-03", 130)]}  # 缺 01-02
    hist = w.build_history(txs, prices)
    i = hist["dates"].index("2026-01-02") if "2026-01-02" in hist["dates"] else None
    # 01-02 沒有價格資料,不在價格日期中,也不在交易日期中 -> 不應出現
    assert i is None
    assert hist["total_value"][-1] == A(130)


def test_history_empty():
    assert w.build_history([], {}) == {"dates": [], "total_value": [], "daily_pnl": []}

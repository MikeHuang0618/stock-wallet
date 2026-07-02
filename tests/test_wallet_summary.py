"""錢包彙總純函式 golden tests:單筆持倉加值、幣別彙總、跨幣別折算。
對照手算值;涵蓋 FX 失敗、當日買進、零除等邊界。全綠才可發佈。"""
import pytest

import wallet as w

A = pytest.approx


def _holding(qty=15, cost=1550.0):
    return {"symbol": "AAPL", "name": "Apple", "qty": qty,
            "avg_cost": cost / qty, "cost_basis": cost, "realized_pnl": 0.0}


# ---------- enrich_holding ----------
def test_enrich_basic_pnl_and_day_change():
    q = {"price": 120.0, "change": 2.0, "prev": 118.0,
         "market_date": "2026-07-01", "prev_date": "2026-06-30"}
    e = w.enrich_holding(_holding(), q, same_day_txs=[])
    assert e["market_value"] == A(1800)
    assert e["pnl"] == A(250)
    assert e["pnl_pct"] == A(250 / 1550 * 100)
    # 15 股昨收 118 → 今 120,當日 +2*15 = 30
    assert e["day_base"] == A(1770)
    assert e["day_change"] == A(30)


def test_enrich_day_change_excludes_pre_buy_move_for_today_purchase():
    # 今天買進 5 股 @119(現價 120):昨天就持有的 10 股賺 (120-118)*10=20,
    # 今天買的 5 股賺 (120-119)*5=5 → 當日損益 25,不把買進前的漲幅算進來。
    q = {"price": 120.0, "prev": 118.0, "market_date": "2026-07-01"}
    txs = [{"symbol": "AAPL", "side": "buy", "quantity": 5, "price": 119.0, "date": "2026-07-01"}]
    e = w.enrich_holding(_holding(qty=15, cost=1550.0), q, same_day_txs=txs)
    assert e["day_base"] == A(1775)      # 118*10 + 5*119
    assert e["day_change"] == A(25)


def test_enrich_missing_price_is_none_not_zero():
    e = w.enrich_holding(_holding(), {"price": None}, same_day_txs=[])
    assert e["market_value"] is None
    assert e["pnl"] is None
    assert e["day_change"] is None


# ---------- summarize_currency ----------
def test_summarize_currency_portfolio_value_and_returns():
    q = {"price": 120.0, "prev": 118.0, "market_date": "2026-07-01"}
    e = w.enrich_holding(_holding(), q, same_day_txs=[])
    s = w.summarize_currency([e], realized_pnl=0.0, deposits_amount=2000.0)
    assert s["total_value"] == A(1800)
    assert s["total_cost"] == A(1550)
    assert s["total_pnl"] == A(250)                 # 未實現
    assert s["portfolio_value"] == A(2250)          # 2000 存入 + 250 損益
    assert s["portfolio_return_pct"] == A(12.5)
    assert s["day_change"] == A(30)
    assert s["day_change_pct"] == A(30 / 1770 * 100)


def test_summarize_currency_no_deposits_returns_zero_pct_no_divzero():
    e = w.enrich_holding(_holding(), {"price": 120.0, "prev": 118.0}, same_day_txs=[])
    s = w.summarize_currency([e], realized_pnl=0.0, deposits_amount=0.0)
    assert s["portfolio_return_pct"] == 0


# ---------- combine_currencies ----------
def _blk(dep, pv):
    return {"total_deposits": dep, "portfolio_value": pv}


def test_combine_converts_twd_to_usd():
    c = w.combine_currencies(_blk(2000, 2250), _blk(100000, 110000), fx=32.0)
    assert c["available"] is True
    assert c["deposits_usd"] == A(2000 + 100000 / 32)
    assert c["portfolio_value_usd"] == A(2250 + 110000 / 32)


def test_combine_fx_unavailable_with_twd_assets_is_unavailable_not_zero():
    # 匯率抓不到且有台幣資產 → 不可硬折成 0(否則總資產靜默縮水)
    c = w.combine_currencies(_blk(2000, 2250), _blk(100000, 110000), fx=None)
    assert c["available"] is False
    assert c["portfolio_value_usd"] is None


def test_combine_fx_unavailable_but_no_twd_is_fine():
    c = w.combine_currencies(_blk(2000, 2250), _blk(0, 0), fx=None)
    assert c["available"] is True
    assert c["portfolio_value_usd"] == A(2250)

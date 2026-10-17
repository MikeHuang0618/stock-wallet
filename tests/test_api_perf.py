import sqlite3

import pytest

import api


@pytest.fixture()
def a(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return api.Api()


@pytest.fixture()
def traced(monkeypatch):
    stmts = []
    real = sqlite3.connect

    def connect(*args, **kw):
        c = real(*args, **kw)
        c.set_trace_callback(stmts.append)
        return c

    monkeypatch.setattr(api.sqlite3, "connect", connect)
    return stmts


def test_schema_ddl_runs_once_per_database(a, traced):
    a._db().close()
    a._db().close()
    a._db().close()
    ddl = [s for s in traced if s.lstrip().upper().startswith(("CREATE TABLE", "PRAGMA TABLE_INFO"))]
    assert len(ddl) == 7


def test_schema_reinitialised_after_restore(a, tmp_path):
    a.wallet_add("AAPL", "", 1, 100, "2026-01-01")
    legacy = tmp_path / "legacy.db"
    c = sqlite3.connect(legacy)
    c.execute("""CREATE TABLE transactions(id INTEGER PRIMARY KEY, symbol TEXT, name TEXT,
                 quantity REAL, price REAL, date TEXT, created_at TEXT)""")
    c.execute("INSERT INTO transactions(symbol,quantity,price,date) VALUES('MSFT',-2,10,'2026-01-02')")
    c.commit()
    c.close()
    assert a.restore_backup(str(legacy))["ok"]
    rows = a.wallet_list()
    assert rows[0]["side"] == "sell" and rows[0]["fee"] == 0


def test_manual_asset_list_query_count_is_constant(a, traced):
    for i in range(5):
        a.manual_asset_add(f"A{i}", "USD", 100 + i, "2026-01-01")
    traced.clear()
    out = a.manual_asset_list()
    selects = [s for s in traced if s.lstrip().upper().startswith("SELECT")]
    assert [x["value"] for x in out] == [100, 101, 102, 103, 104]
    assert len(selects) == 1


def test_manual_asset_list_picks_latest_valuation(a):
    a.manual_asset_add("定存", "TWD", 100, "2026-01-01")
    aid = a.manual_asset_list()[0]["id"]
    a.manual_asset_set_value(aid, 300, "2026-03-01")
    a.manual_asset_set_value(aid, 200, "2026-02-01")
    a.manual_asset_add("空", "USD")
    got = {x["name"]: (x["value"], x["date"]) for x in a.manual_asset_list()}
    assert got == {"定存": (300, "2026-03-01"), "空": (None, None)}


def test_get_quotes_reuses_fresh_cache_when_allowed(a, monkeypatch):
    calls = []

    def fake(sym):
        calls.append(sym)
        return {"price": 1.0, "error": None}

    monkeypatch.setattr(a, "_fetch_one", fake)
    a.get_quotes(["AAPL"])
    a.get_quotes(["AAPL", "MSFT"], max_age=90)
    assert calls == ["AAPL", "MSFT"]
    a.get_quotes(["AAPL"])
    assert calls == ["AAPL", "MSFT", "AAPL"]


def test_get_quotes_does_not_reuse_errors(a, monkeypatch):
    calls = []

    def fake(sym):
        calls.append(sym)
        return {"price": None, "error": "boom"}

    monkeypatch.setattr(a, "_fetch_one", fake)
    a.get_quotes(["AAPL"])
    a.get_quotes(["AAPL"], max_age=90)
    assert calls == ["AAPL", "AAPL"]


def test_wallet_history_report_computes_history_once(a, monkeypatch):
    n = []
    empty = {"dates": [], "total_value": [], "portfolio_value": [], "daily_pnl": []}
    monkeypatch.setattr(a, "wallet_history", lambda: n.append(1) or {"USD": empty, "TWD": empty, "TOTAL": empty})
    r = a.wallet_history_report("yearly")
    assert len(n) == 1
    assert set(r) == {"history", "report"}
    assert set(r["report"]) == {"USD", "TWD"}

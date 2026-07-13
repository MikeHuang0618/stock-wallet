"""api.py 錢包資料層測試(不碰網路):遷移提交、快照防呆/UPSERT、手動資產、備份、補登旗標。

APPDATA 指向 pytest tmp_path,每個測試一個乾淨資料庫。這些是 wallet.db
(使用者全部資產歷史的唯一載體)的資料完整性防線。
"""
import sqlite3

import pytest

import api


@pytest.fixture()
def a(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return api.Api()


# ---------- 遷移 ----------
def test_legacy_migration_commits_across_connections(a):
    """舊 schema(無 side/fee、負數量=賣出)開啟後遷移必須跨連線持久
    (回歸:遷移的 UPDATE 未 commit 會在連線關閉時回滾)。"""
    db = api._file("wallet.db")
    c = sqlite3.connect(db)
    c.execute("""CREATE TABLE transactions(id INTEGER PRIMARY KEY, symbol TEXT, name TEXT,
                 quantity REAL, price REAL, date TEXT, created_at TEXT)""")
    c.execute("INSERT INTO transactions(symbol,quantity,price,date) VALUES('AAPL',-3,100,'2026-01-01')")
    c.commit()
    c.close()
    a._db().close()                                   # 觸發遷移
    rows = a.wallet_list()                            # 全新連線讀取
    assert rows[0]["side"] == "sell"
    assert rows[0]["quantity"] == 3
    assert rows[0]["fee"] == 0


# ---------- wallet_add 驗證 ----------
def test_wallet_add_dividend_stores_amount_with_zero_qty(a):
    assert a.wallet_add("0056.TW", "元大高股息", 999, 200, "2026-03-01", "dividend")["ok"]
    row = a.wallet_list()[0]
    assert row["side"] == "dividend" and row["quantity"] == 0 and row["price"] == 200


def test_wallet_add_adjust_keeps_negative_qty(a):
    assert a.wallet_add("PENNY", "", -900, 5, "2026-03-01", "adjust")["ok"]
    row = a.wallet_list()[0]
    assert row["quantity"] == -900 and row["price"] == 0    # 合股:負數保留、price 歸零


def test_wallet_add_rejects_zero_dividend_and_zero_shares(a):
    assert not a.wallet_add("X", "", 0, 0, "2026-01-01", "dividend")["ok"]
    assert not a.wallet_add("X", "", 0, 0, "2026-01-01", "stock_dividend")["ok"]


# ---------- 快照 ----------
def _blocks(pv=9500, mv=9000):
    return {"USD": {"total_value": mv, "portfolio_value": pv, "day_date": "2026-06-10"}}


def test_snapshot_upsert_same_day(a):
    a._write_snapshot(_blocks(9500), 32.0, [])
    a._write_snapshot(_blocks(9600), 32.0, [])
    snaps = a._read_snapshots("USD")
    assert len(snaps) == 1
    assert snaps[0]["portfolio_value"] == 9600


def test_snapshot_skipped_when_any_quote_missing(a):
    """任一持倉報價缺失 → 該幣別不寫快照(絕不把低估市值寫成不可變紀錄)。"""
    enriched = [{"symbol": "AAPL", "currency": "USD", "qty": 1, "market_value": None, "price": None}]
    a._write_snapshot(_blocks(), 32.0, enriched)
    assert a._read_snapshots("USD") == []


def test_snapshot_written_when_quotes_complete(a):
    enriched = [{"symbol": "AAPL", "currency": "USD", "qty": 1, "market_value": 9000.0, "price": 9000.0}]
    a._write_snapshot(_blocks(), 32.0, enriched)
    snaps = a._read_snapshots("USD")
    assert len(snaps) == 1 and snaps[0]["market_value"] == 9000


def test_backdated_transaction_flagged(a):
    a._write_snapshot(_blocks(), 32.0, [])            # 最新快照 2026-06-10
    r = a.wallet_add("AAPL", "Apple", 10, 100, "2026-01-05", "buy")
    assert r["ok"] and r["backdated"] is True
    r2 = a.wallet_add("AAPL", "Apple", 10, 100, "2026-06-11", "buy")
    assert r2["ok"] and r2["backdated"] is False


# ---------- 手動資產 ----------
def test_manual_asset_lifecycle(a):
    assert a.manual_asset_add("定存", "TWD", 1000000, "2026-01-01")["ok"]
    lst = a.manual_asset_list()
    assert lst[0]["value"] == 1000000 and lst[0]["currency"] == "TWD"
    assert a.manual_asset_set_value(lst[0]["id"], 1050000, "2026-06-01")["ok"]
    assert a.manual_assets_current()["TWD"] == 1050000
    exported = a._export_manual_assets()
    assert len(exported[0]["valuations"]) == 2        # 估值歷史保留,不覆蓋
    assert a.manual_asset_delete(lst[0]["id"])["ok"]
    assert a.manual_asset_list() == []


def test_manual_asset_requires_name(a):
    assert not a.manual_asset_add("  ", "USD", 100)["ok"]


# ---------- 自動備份 ----------
def test_auto_backup_creates_once_per_day_and_prunes(a):
    a._db().close()                                   # 先讓 wallet.db 存在
    r1 = a.auto_backup()
    assert r1["ok"] and not r1.get("skipped")
    assert a.auto_backup()["skipped"] is True         # 同日第二次:略過
    # 塞 31 份假備份 → prune 後只留 30
    import os
    d = a._backups_dir()
    for i in range(31):
        with open(os.path.join(d, f"wallet-2025-01-{i+1:02d}.db"), "wb") as f:
            f.write(b"x")
    a._prune_backups(30)
    files = [f for f in os.listdir(d) if f.startswith("wallet-")]
    assert len(files) == 30
    assert "wallet-2025-01-01.db" not in files        # 最舊的被刪


def test_restore_backup_roundtrip(a):
    assert a.wallet_add("AAPL", "Apple", 10, 100, "2026-01-01", "buy")["ok"]
    b = a.auto_backup()
    assert a.wallet_add("NVDA", "NVIDIA", 5, 900, "2026-02-01", "buy")["ok"]
    assert len(a.wallet_list()) == 2
    assert a.restore_backup(b["path"])["ok"]
    assert len(a.wallet_list()) == 1                  # 還原到備份當下
    assert a.wallet_list()[0]["symbol"] == "AAPL"

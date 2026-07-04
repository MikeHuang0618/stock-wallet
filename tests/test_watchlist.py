"""觀察名單 v2 群組結構遷移的純函式測試(api.migrate_watchlist)。

v2 結構:{"version":2,"groups":[{"id","name","items":[{sym,name}]}]}。
舊 v1 為扁平陣列 [{sym,name}],遷移為單一「預設」群組。sym 全域去重。
"""
import api


def test_migrate_watchlist_v1_to_v2():
    v1 = [{"sym": "AAPL", "name": "Apple"}, {"sym": "NVDA", "name": "Nvidia"}]
    out = api.migrate_watchlist(v1)
    assert out["version"] == 2
    assert len(out["groups"]) == 1
    assert out["groups"][0]["id"] == "default"
    assert [i["sym"] for i in out["groups"][0]["items"]] == ["AAPL", "NVDA"]


def test_migrate_watchlist_v2_preserved():
    v2 = {"version": 2, "groups": [
        {"id": "default", "name": "預設", "items": [{"sym": "AAPL", "name": "Apple"}]},
        {"id": "g1", "name": "半導體", "items": [{"sym": "NVDA", "name": "Nvidia"}]}]}
    out = api.migrate_watchlist(v2)
    assert out["version"] == 2
    assert len(out["groups"]) == 2
    assert out["groups"][1]["name"] == "半導體"
    assert out["groups"][1]["items"][0]["sym"] == "NVDA"


def test_migrate_watchlist_empty():
    for raw in ([], None, {}):
        out = api.migrate_watchlist(raw)
        assert out["version"] == 2
        assert out["groups"][0]["id"] == "default"
        assert out["groups"][0]["items"] == []


def test_migrate_watchlist_dedupes_sym():
    """重複 sym 全域去重,保留第一次出現。"""
    v1 = [{"sym": "AAPL", "name": "Apple"}, {"sym": "AAPL", "name": "dup"}, {"sym": "NVDA"}]
    out = api.migrate_watchlist(v1)
    syms = [i["sym"] for g in out["groups"] for i in g["items"]]
    assert syms == ["AAPL", "NVDA"]


def test_migrate_watchlist_ensures_default_group():
    """v2 若缺預設群組,遷移後補上(供刪群組時 items 併回)。"""
    v2 = {"version": 2, "groups": [{"id": "g1", "name": "ETF", "items": [{"sym": "SPY"}]}]}
    out = api.migrate_watchlist(v2)
    ids = [g["id"] for g in out["groups"]]
    assert "default" in ids

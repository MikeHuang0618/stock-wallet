"""事件合併/遷移純函式測試(api.merge_events / api.migrate_events)。

內建事件(DEFAULT_EVENTS)存在於程式碼、隨版本更新;使用者自訂事件存於
custom_events.json。get_events 合併兩者並標記 source,讓內建事件不再被舊
events.json 快照凍結。遷移把舊 events.json 裡「非內建」項搬進自訂檔。
"""
import api

CPI = {"date": "2026-07-14", "type": "CPI", "title": "6 月 CPI", "time": "20:30", "impact": "high"}
NFP = {"date": "2026-07-02", "type": "NFP", "title": "6 月 NFP", "time": "20:30", "impact": "high"}
CUSTOM = {"date": "2026-07-20", "type": "自訂", "title": "我的事件", "time": "10:00", "impact": "low"}


# ---------- merge_events ----------
def test_merge_tags_source():
    out = api.merge_events([CPI], [CUSTOM])
    by_title = {e["title"]: e for e in out}
    assert by_title["6 月 CPI"]["source"] == "builtin"
    assert by_title["我的事件"]["source"] == "custom"


def test_merge_dedupes_custom_matching_builtin():
    """自訂項與內建完全相同 → 只列一次,以內建為準。"""
    out = api.merge_events([CPI], [dict(CPI)])
    assert len(out) == 1
    assert out[0]["source"] == "builtin"


def test_merge_empty_custom():
    out = api.merge_events([CPI, NFP], [])
    assert len(out) == 2
    assert all(e["source"] == "builtin" for e in out)


# ---------- migrate_events ----------
def test_migrate_moves_only_non_builtin():
    """舊檔 = 內建快照 + 自訂;只搬非內建項,且不帶殘留 source。"""
    old = [dict(CPI), dict(NFP), dict(CUSTOM)]
    custom = api.migrate_events(old, [CPI, NFP])
    assert len(custom) == 1
    assert custom[0]["title"] == "我的事件"
    assert "source" not in custom[0]


def test_migrate_dedupes():
    custom = api.migrate_events([dict(CUSTOM), dict(CUSTOM)], [])
    assert len(custom) == 1


def test_migrate_empty():
    assert api.migrate_events([], [CPI]) == []
    assert api.migrate_events(None, [CPI]) == []

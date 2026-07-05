"""QuoteRefresher 排程/去重邏輯測試(以注入 fake fetch + threading.Event 同步)。

目標:標的變更觸發立即刷新、抓取中不重疊(單執行緒序列化)。禁止 sleep 輪詢。
"""
import threading

import api


def test_refresher_immediate_on_symbol_change():
    """set_symbols 應立即觸發抓取(不等 interval),抓完通知前端,快取可讀。"""
    calls = []
    fetched = threading.Event()

    def fake_fetch(syms):
        calls.append(list(syms))
        fetched.set()
        return {s: {"price": 1.0} for s in syms}

    notified = threading.Event()
    r = api.QuoteRefresher(fake_fetch, notified.set, interval=30)
    r.start()
    try:
        r.set_symbols(["AAPL", "NVDA"])
        assert fetched.wait(3), "set_symbols 應立即觸發抓取"
        assert calls[0] == ["AAPL", "NVDA"]
        assert notified.wait(3), "抓取後應通知前端"
        assert r.get_cache()["AAPL"]["price"] == 1.0
    finally:
        r.stop()


def test_refresher_no_overlap():
    """抓取進行中再次觸發,不會產生並發抓取(任一時刻至多一個)。"""
    lock = threading.Lock()
    state = {"cur": 0, "max": 0, "n": 0}
    entered = threading.Event()
    release = threading.Event()
    two_done = threading.Event()

    def fake_fetch(syms):
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
            state["n"] += 1
            n = state["n"]
        entered.set()
        release.wait(3)             # 阻塞抓取以製造「抓取進行中」的時窗
        with lock:
            state["cur"] -= 1
        if n >= 2:
            two_done.set()
        return {}

    r = api.QuoteRefresher(fake_fetch, lambda: None, interval=30)
    r.start()
    try:
        r.set_symbols(["A"])
        assert entered.wait(3), "第一次抓取應開始"
        r.set_symbols(["B"])        # 抓取進行中再次觸發
        release.set()               # 放行,thread 依 wake 立即再抓一次
        assert two_done.wait(3), "第二次抓取應發生"
        assert state["max"] == 1, "任一時刻最多一個抓取(未重疊)"
    finally:
        r.stop()
        release.set()


def test_refresher_same_symbols_no_refetch():
    """set_symbols 相同集合(即使順序不同)→ 不重新觸發抓取(消除雙重推送)。"""
    calls = []
    ev = threading.Event()

    def fake_fetch(syms):
        calls.append(list(syms))
        ev.set()
        return {}

    r = api.QuoteRefresher(fake_fetch, lambda: None, interval=30)
    r.start()
    try:
        r.set_symbols(["A", "B"])
        assert ev.wait(2), "首次(空→新集合)應觸發抓取"
        assert len(calls) == 1
        ev.clear()
        r.set_symbols(["B", "A"])       # 同一集合、不同順序
        assert not ev.wait(0.5), "相同集合不應再觸發抓取"
        assert len(calls) == 1
    finally:
        r.stop()


def test_refresher_request_now_refetches_without_change():
    """request_now 即使標的沒變也強制抓一次(手動 ↻)。"""
    calls = []
    ev = threading.Event()

    def fake_fetch(syms):
        calls.append(list(syms))
        ev.set()
        return {}

    r = api.QuoteRefresher(fake_fetch, lambda: None, interval=30)
    r.start()
    try:
        r.set_symbols(["A"])
        assert ev.wait(2)
        ev.clear()
        r.request_now()
        assert ev.wait(2), "request_now 應強制再抓一次"
        assert len(calls) == 2
    finally:
        r.stop()


def test_refresher_dedupes_symbols():
    """set_symbols 會去重(避免同一標的重覆抓)。"""
    seen = []
    got = threading.Event()

    def fake_fetch(syms):
        seen.append(list(syms))
        got.set()
        return {}

    r = api.QuoteRefresher(fake_fetch, lambda: None, interval=30)
    r.start()
    try:
        r.set_symbols(["AAPL", "AAPL", "NVDA"])
        assert got.wait(3)
        assert seen[0] == ["AAPL", "NVDA"]
    finally:
        r.stop()

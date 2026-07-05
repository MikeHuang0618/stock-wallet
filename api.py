"""
市場儀表板 · Market Dashboard
================================
可擴充的多頁面桌面工具:

  主畫面      大盤指數 (那指/標普/道瓊/羅素/費半/VIX) + 自訂觀察名單 (Yahoo 查詢)
  黃金訊號    GLL / UGL 交易日曆 (CPI / 非農 / FOMC) + 關鍵價位訊號追蹤 (系統通知)
  (未來)      側邊欄可再掛更多特殊頁面

單檔設計,方便用 PyInstaller 打包成可攜式 exe。
資料來源:Yahoo Finance(延遲報價,僅供參考)。
"""

import copy
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from logging.handlers import RotatingFileHandler

import requests
import webview

import indicators as ta
import analysis
import signals as sig
import wallet as wl
from analysis import TIMEFRAMES, DEFAULT_AI_PROMPT, PROVIDER_MODELS

try:
    from winotify import Notification, audio
    _HAS_NOTIFY = True
except Exception:
    _HAS_NOTIFY = False

APP_NAME = "StockWallet"
APP_ID = "StockWallet"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2mo&interval=1d"
YAHOO_SEARCH = ("https://query1.finance.yahoo.com/v1/finance/search"
                "?q={q}&quotesCount=8&newsCount=0&enableFuzzyQuery=false")
YAHOO_SUMMARY = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules=calendarEvents&crumb={crumb}"
YAHOO_CRUMB = "https://query1.finance.yahoo.com/v1/test/getcrumb"
YAHOO_CHART_Q = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{query}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

WALLET_HISTORY_TTL = 600   # 錢包歷史日線快取存活秒數(停留在錢包頁時避免每 120 秒全量重抓)

log = logging.getLogger("stockwallet")

# 臺灣期貨交易所 (TAIFEX) 官方資料源
#   台股 VIX:每日波動率指數檔 (big5,tab 分隔:日期 / 時間 / VIX / 前一交易日收盤)
#   台指期:MIS 即時行情 API,取臺股期貨 (TXF) 近月合約
TAIFEX_VIX_FILE = "https://www.taifex.com.tw/file/taifex/Dailydownload/vix/log2data/{ym}new.txt"
TAIFEX_MIS_QUOTE = "https://mis.taifex.com.tw/futures/api/getQuoteList"
TAIFEX_MIS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Origin": "https://mis.taifex.com.tw",
    "Referer": "https://mis.taifex.com.tw/futures/",
}
# 前端用的合成代號 (非 Yahoo 標的,由 TAIFEX 專用抓取器處理)
TW_TXF = "TWTXF"   # 台指期近月
TW_VIX = "TWVIX"   # 台股波動率指數

# ---------------------------------------------------------------------------
# 2026 經濟事件排程 (以官方 BLS / Federal Reserve 公布為準,可用
# %APPDATA%/StockWallet/events.json 覆寫)  type: CPI / NFP / FOMC
# ---------------------------------------------------------------------------
DEFAULT_EVENTS = [
    {"date": "2026-07-14", "type": "CPI", "title": "6 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-08-12", "type": "CPI", "title": "7 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-09-11", "type": "CPI", "title": "8 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-10-14", "type": "CPI", "title": "9 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-11-10", "type": "CPI", "title": "10 月 CPI 通膨數據", "time": "21:30", "impact": "high"},
    {"date": "2026-12-10", "type": "CPI", "title": "11 月 CPI 通膨數據", "time": "21:30", "impact": "high"},
    {"date": "2026-07-02", "type": "NFP", "title": "6 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-08-07", "type": "NFP", "title": "7 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-09-04", "type": "NFP", "title": "8 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-10-02", "type": "NFP", "title": "9 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-11-06", "type": "NFP", "title": "10 月非農就業報告", "time": "21:30", "impact": "high"},
    {"date": "2026-12-04", "type": "NFP", "title": "11 月非農就業報告", "time": "21:30", "impact": "high"},
    {"date": "2026-07-29", "type": "FOMC", "title": "FOMC 利率決議", "time": "02:00", "impact": "critical"},
    {"date": "2026-09-16", "type": "FOMC", "title": "FOMC 利率決議 + 經濟預測 (點陣圖)", "time": "02:00", "impact": "critical"},
    {"date": "2026-10-28", "type": "FOMC", "title": "FOMC 利率決議", "time": "02:00", "impact": "critical"},
    {"date": "2026-12-09", "type": "FOMC", "title": "FOMC 利率決議 + 經濟預測 (點陣圖)", "time": "03:00", "impact": "critical"},
    {"date": "2026-01-13", "type": "CPI", "title": "12 月 CPI 通膨數據", "time": "21:30", "impact": "high"},
    {"date": "2026-02-13", "type": "CPI", "title": "1 月 CPI 通膨數據", "time": "21:30", "impact": "high"},
    {"date": "2026-03-11", "type": "CPI", "title": "2 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-04-10", "type": "CPI", "title": "3 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-05-12", "type": "CPI", "title": "4 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-06-10", "type": "CPI", "title": "5 月 CPI 通膨數據", "time": "20:30", "impact": "high"},
    {"date": "2026-01-09", "type": "NFP", "title": "12 月非農就業報告", "time": "21:30", "impact": "high"},
    {"date": "2026-02-06", "type": "NFP", "title": "1 月非農就業報告", "time": "21:30", "impact": "high"},
    {"date": "2026-03-06", "type": "NFP", "title": "2 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-04-03", "type": "NFP", "title": "3 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-05-08", "type": "NFP", "title": "4 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-06-05", "type": "NFP", "title": "5 月非農就業報告", "time": "20:30", "impact": "high"},
    {"date": "2026-01-28", "type": "FOMC", "title": "FOMC 利率決議", "time": "03:00", "impact": "critical"},
    {"date": "2026-03-18", "type": "FOMC", "title": "FOMC 利率決議 + 經濟預測 (點陣圖)", "time": "02:00", "impact": "critical"},
    {"date": "2026-04-29", "type": "FOMC", "title": "FOMC 利率決議", "time": "02:00", "impact": "critical"},
    {"date": "2026-06-17", "type": "FOMC", "title": "FOMC 利率決議 + 經濟預測 (點陣圖)", "time": "02:00", "impact": "critical"},
]

DEFAULT_WATCHLIST = [
    {"sym": "AAPL", "name": "Apple Inc."},
    {"sym": "NVDA", "name": "NVIDIA Corporation"},
    {"sym": "TSLA", "name": "Tesla, Inc."},
]

# ---------------------------------------------------------------------------
# 台股專屬:重大事件 (以央行 / 主計總處公布為準,可用 events_tw.json 覆寫) 與預設觀察名單
# 類型 TWR = 央行理監事會議 (利率決議);TWCPI = 台灣消費者物價指數
# 註:日期為依往年慣例推估的預定日,實際以官方公布為準。
# ---------------------------------------------------------------------------
DEFAULT_TW_EVENTS = [
    {"date": "2026-03-19", "type": "TWR", "title": "央行理監事聯席會議 (利率決議)", "time": "16:00", "impact": "critical"},
    {"date": "2026-06-18", "type": "TWR", "title": "央行理監事聯席會議 (利率決議)", "time": "16:00", "impact": "critical"},
    {"date": "2026-09-17", "type": "TWR", "title": "央行理監事聯席會議 (利率決議)", "time": "16:00", "impact": "critical"},
    {"date": "2026-12-17", "type": "TWR", "title": "央行理監事聯席會議 (利率決議)", "time": "16:00", "impact": "critical"},
    {"date": "2026-01-07", "type": "TWCPI", "title": "12 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-02-06", "type": "TWCPI", "title": "1 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-03-06", "type": "TWCPI", "title": "2 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-04-08", "type": "TWCPI", "title": "3 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-05-07", "type": "TWCPI", "title": "4 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-06-05", "type": "TWCPI", "title": "5 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-07-07", "type": "TWCPI", "title": "6 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-08-06", "type": "TWCPI", "title": "7 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-09-04", "type": "TWCPI", "title": "8 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-10-07", "type": "TWCPI", "title": "9 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-11-06", "type": "TWCPI", "title": "10 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
    {"date": "2026-12-04", "type": "TWCPI", "title": "11 月消費者物價指數 (CPI)", "time": "16:00", "impact": "high"},
]

DEFAULT_TW_WATCHLIST = [
    {"sym": "2330.TW", "name": "台積電"},
    {"sym": "2317.TW", "name": "鴻海"},
    {"sym": "2454.TW", "name": "聯發科"},
]


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def _file(name):
    return os.path.join(data_dir(), name)


def setup_logging():
    """設定 RotatingFileHandler 到 %APPDATA%/StockWallet/logs/app.log(1MB × 3)。

    冪等(重複呼叫只設定一次),失敗靜默不影響啟動。
    注意:嚴禁把 API 金鑰或其他機密寫入 log。
    """
    if getattr(setup_logging, "_done", False):
        return
    setup_logging._done = True
    try:
        logdir = os.path.join(data_dir(), "logs")
        os.makedirs(logdir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(logdir, "app.log"),
            maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.setLevel(logging.INFO)
        if not log.handlers:
            log.addHandler(handler)
    except Exception:
        pass


def format_labels(ts, fmt, gmtoffset=0):
    """把 UTC 秒數序列依交易所時區偏移格式化為 K 線標籤(純函式)。

    gmtoffset 為 Yahoo meta.gmtoffset(秒)。小時線需以交易所當地時區顯示
    (台股 09:00 而非 UTC 01:00);日線/月線 fmt 不含時間,偏移不跨日,結果不變。
    作法比照 _fetch_one 的 _sess_date:utc 秒數 + gmtoffset 後以 UTC 格式化。
    """
    off = gmtoffset or 0
    return [datetime.fromtimestamp(int(t) + off, tz=timezone.utc).strftime(fmt) for t in ts]


def normalize_ohlcv(payload):
    """統一 OHLCV 的 None 列處理(純函式,方便測試)。

    Yahoo 序列常含 None:停牌造成的中段 None、正在形成的當日 bar 尾端 None,
    或 close 有值但 volume 缺失。策略:
      - close 為 None 的 bar 整列剔除(ts/labels/open/high/low/close/volume 同步對齊刪除);
      - close 存在但 volume 為 None 時,volume 補 0。
    這讓 rsi / obv 等指標不會因單一 None 整條變成 None。
    有 error 或缺 close 欄位的 payload 原樣返回。
    """
    if payload.get("error") or "close" not in payload:
        return payload
    keep = [i for i, c in enumerate(payload["close"]) if c is not None]
    for k in ("ts", "labels", "open", "high", "low", "close", "volume"):
        arr = payload.get(k)
        if isinstance(arr, list):
            payload[k] = [arr[i] for i in keep if i < len(arr)]
    payload["volume"] = [0 if v is None else v for v in payload.get("volume", [])]
    return payload


WATCHLIST_DEFAULT_GROUP = "default"


def migrate_watchlist(data):
    """把觀察名單資料正規化為 v2 群組結構(純函式)。

    v2 結構:{"version":2,"groups":[{"id","name","items":[{sym,name}]}]}。
    - v1(扁平陣列 [{sym,name}])→ 單一「預設」群組;
    - v2 → 原樣(仍會正規化 items 並去重);
    - 空 / None / 非預期型別 → 空的預設群組。
    sym 全域去重(跨群組保留第一次出現);永遠保證存在 id="default" 的預設群組
    (供刪除群組時把 items 併回)。
    """
    if isinstance(data, dict) and data.get("version") == 2 and isinstance(data.get("groups"), list):
        groups = data["groups"]
    elif isinstance(data, list):
        groups = [{"id": WATCHLIST_DEFAULT_GROUP, "name": "預設", "items": data}]
    else:
        groups = []
    seen, out_groups, has_default = set(), [], False
    for g in groups:
        gid = g.get("id") or WATCHLIST_DEFAULT_GROUP
        has_default = has_default or gid == WATCHLIST_DEFAULT_GROUP
        items = []
        for it in (g.get("items") or []):
            sym = it.get("sym")
            if not sym or sym in seen:
                continue
            seen.add(sym)
            items.append({"sym": sym, "name": it.get("name") or sym})
        out_groups.append({"id": gid, "name": g.get("name") or "預設", "items": items})
    if not has_default:
        out_groups.insert(0, {"id": WATCHLIST_DEFAULT_GROUP, "name": "預設", "items": []})
    return {"version": 2, "groups": out_groups}


class QuoteRefresher(threading.Thread):
    """背景報價刷新器(daemon 執行緒)。

    UI 永不等網路:前端只讀快取(get_cache);抓取在此單一執行緒序列化,
    因此更新永不重疊。標的變更(set_symbols)或要求立即刷新(request_now)會喚醒
    執行緒立刻抓一輪,否則每 interval 秒抓一次。每輪抓取後呼叫 notify 推播前端。

    fetch(symbols)->dict 與 notify() 皆由外部注入(方便單元測試;正式使用時
    fetch=Api.get_quotes,notify=推播 evaluate_js)。
    """

    def __init__(self, fetch, notify, interval=120):
        super().__init__(daemon=True)
        self._fetch = fetch
        self._notify = notify
        self._interval = interval
        self._symbols = []
        self._cache = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()   # 標的變更 / 立即刷新時 set
        self._stop = threading.Event()

    def set_symbols(self, symbols):
        new = list(dict.fromkeys(symbols or []))   # 去重、保序
        with self._lock:
            changed = set(new) != set(self._symbols)
            self._symbols = new
        if changed:              # 集合真的變了才喚醒立即刷新,避免同一動作觸發雙重推送
            self._wake.set()

    def request_now(self):
        self._wake.set()

    def get_cache(self):
        with self._lock:
            return dict(self._cache)

    def stop(self):
        self._stop.set()
        self._wake.set()

    def run(self):
        while not self._stop.is_set():
            # 等到 interval 到期,或被 set_symbols/request_now 提前喚醒(clear 於抓取前,
            # 抓取期間新來的 wake 會保留到下一輪 wait,不會遺失喚醒)。
            self._wake.wait(self._interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                syms = list(self._symbols)
            if not syms:
                continue
            try:
                quotes = self._fetch(syms)
            except Exception as e:
                log.warning("QuoteRefresher fetch failed: %s", e)
                quotes = None
            if quotes:
                with self._lock:
                    self._cache.update(quotes)
            self._notify()   # 每輪抓取後通知(即使失敗),讓前端解除等待並渲染最新快取


def _event_key(e):
    return (e.get("date"), e.get("type"), e.get("title"), e.get("time"))


def merge_events(defaults, custom):
    """合併內建事件(defaults,隨程式碼更新)與使用者自訂事件(custom,存於檔案),
    標記 source 欄位並去重(純函式)。

    以 (date,type,title,time) 為鍵;內建優先,與內建重複的自訂項不重複列出。
    這讓內建事件不再被舊 events.json 快照凍結——它們永遠來自程式碼。
    """
    seen, out = set(), []
    for e in defaults:
        k = _event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append({**e, "source": "builtin"})
    for e in (custom or []):
        k = _event_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append({**e, "source": "custom"})
    return out


def migrate_events(old_events, defaults):
    """把舊 events.json 扁平清單裡「不在內建清單中」的項目挑出來當自訂事件(純函式)。

    以 (date,type,title,time) 比對內建;內建項不搬、重複項去重、移除殘留 source 欄位。
    """
    builtin_keys = {_event_key(e) for e in defaults}
    seen, custom = set(), []
    for e in (old_events or []):
        k = _event_key(e)
        if k in builtin_keys or k in seen:
            continue
        seen.add(k)
        custom.append({kk: vv for kk, vv in e.items() if kk != "source"})
    return custom


class Api:
    """暴露給前端 JS 呼叫的介面 (window.pywebview.api.*)"""

    def __init__(self):
        self._ohlcv_cache = {}   # (sym, timeframe) -> (fetched_at, payload)
        # requests.Session 非執行緒安全,ThreadPoolExecutor 各執行緒不可共用同一個,
        # 改用 threading.local() 持有每執行緒專屬的 Session(見 _http)。
        self._local = threading.local()
        self._crumb = None
        self._crumb_cookies = None          # 取得 crumb 時的 Yahoo cookies,注入其他執行緒 session
        self._crumb_lock = threading.Lock()
        self._history_cache = {}            # symbol -> (fetched_at, series);TTL WALLET_HISTORY_TTL
        self._history_lock = threading.Lock()
        self._refresher = None              # QuoteRefresher(背景報價推送),首次呼叫時 lazy 啟動

    def _http(self):
        """回傳當前執行緒專屬的 requests.Session(每執行緒一個,避免共用非執行緒安全物件)。
        新建 session 會注入取得 crumb 時的 Yahoo cookies,讓財報查詢在工作執行緒也能通過驗證。"""
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            if self._crumb_cookies is not None:
                for c in self._crumb_cookies:
                    s.cookies.set_cookie(copy.copy(c))
            self._local.session = s
        return s

    def _invalidate_history_cache(self):
        """交易新增/刪除/匯入時使錢包歷史日線快取整體失效
        (最早交易日可能改變,舊快取的序列起點不再涵蓋,必須重抓)。"""
        with self._history_lock:
            self._history_cache.clear()

    # ---- 事件 ----
    @staticmethod
    def _events_conf(market):
        """回傳 (舊檔名, 自訂檔名, 內建清單)。us / tw 各一組。"""
        if market == "tw":
            return "events_tw.json", "custom_events_tw.json", DEFAULT_TW_EVENTS
        return "events.json", "custom_events.json", DEFAULT_EVENTS

    def get_events(self, market="us"):
        old_name, custom_name, default = self._events_conf(market)
        self._migrate_events_file(old_name, custom_name, default)   # 首次啟動遷移舊檔(之後為 no-op)
        custom = self._load(custom_name, [])
        return {"today": date.today().isoformat(),
                "events": merge_events(default, custom)}

    def add_event(self, date_str, type_str, title, time_str, impact, market="us"):
        _, custom_name, _ = self._events_conf(market)
        custom = self._load(custom_name, [])
        custom.append({"date": date_str, "type": type_str, "title": title,
                       "time": time_str, "impact": impact})
        return self._save(custom_name, custom)

    def delete_event(self, date_str, title, market="us"):
        # 只允許刪除自訂事件;內建事件不在自訂檔內,filter 後自然保留。
        _, custom_name, _ = self._events_conf(market)
        custom = self._load(custom_name, [])
        custom = [e for e in custom if not (e.get("date") == date_str and e.get("title") == title)]
        return self._save(custom_name, custom)

    def _migrate_events_file(self, old_name, custom_name, default):
        """首次啟動遷移:舊 events.json 若存在,把非內建項搬到 custom_events.json,
        舊檔改名為 .bak。舊檔不存在時直接 no-op(之後每次呼叫都是 no-op)。"""
        old_path = _file(old_name)
        if not os.path.exists(old_path):
            return
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = None
        # 只在自訂檔尚不存在時才寫入,避免覆蓋使用者已編輯過的自訂事件
        if old is not None and not os.path.exists(_file(custom_name)):
            self._save(custom_name, migrate_events(old, default))
        try:
            os.replace(old_path, old_path + ".bak")   # os.replace 於 Windows 亦可覆蓋既有 .bak
        except Exception:
            pass

    # ---- 訊號提醒 ----
    def get_alerts(self):
        return self._load("alerts.json", [])

    def save_alerts(self, alerts):
        return self._save("alerts.json", alerts)

    # ---- 觀察名單 ----
    def get_watchlist(self, market="us"):
        fname = "watchlist_tw.json" if market == "tw" else "watchlist.json"
        default = DEFAULT_TW_WATCHLIST if market == "tw" else DEFAULT_WATCHLIST
        raw = self._load(fname, default)
        data = migrate_watchlist(raw)
        # 舊 v1 檔或預設清單:遷移後寫回 v2(已是 v2 則不重寫,避免無謂 I/O)
        if not (isinstance(raw, dict) and raw.get("version") == 2):
            self._save(fname, data)
        return data

    def save_watchlist(self, wl, market="us"):
        # 接受 v2 結構或舊扁平陣列,一律正規化為 v2 後存檔
        fname = "watchlist_tw.json" if market == "tw" else "watchlist.json"
        return self._save(fname, migrate_watchlist(wl))

    def _load(self, name, default):
        try:
            with open(_file(name), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, name, obj):
        try:
            with open(_file(name), "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- 報價 ----
    def get_quotes(self, symbols):
        out = {}
        symbols = list(dict.fromkeys(symbols or []))
        if not symbols:
            return out

        def fetch(sym):
            if sym == TW_VIX:
                return self._taifex_vix()
            if sym == TW_TXF:
                return self._taifex_txf()
            return self._fetch_one(sym)

        with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as ex:
            futs = {ex.submit(fetch, s): s for s in symbols}
            for f in as_completed(futs):
                out[futs[f]] = f.result()
        return out

    # ---- 背景報價推送(QuoteRefresher)----
    def _ensure_refresher(self):
        """首次呼叫時 lazy 啟動背景刷新器。此時前端已呼叫過 js_api,視窗必然存在,
        故之後的 evaluate_js 推播不會早於視窗建立。"""
        if self._refresher is None:
            self._refresher = QuoteRefresher(self.get_quotes, self._push_quotes)
            self._refresher.start()
        return self._refresher

    def _push_quotes(self):
        """通知前端有新報價(呼叫 window.onQuotesPush)。視窗未就緒/已關則靜默忽略。"""
        try:
            wins = getattr(webview, "windows", None)
            if wins:
                wins[0].evaluate_js("window.onQuotesPush&&window.onQuotesPush()")
        except Exception as e:
            log.debug("push_quotes failed: %s", e)

    def set_quote_symbols(self, symbols):
        """前端設定要追蹤的報價標的;變更會觸發背景立即刷新一輪。"""
        self._ensure_refresher().set_symbols(symbols or [])
        return {"ok": True}

    def request_refresh_now(self):
        """前端要求立即刷新(手動 ↻)。"""
        self._ensure_refresher().request_now()
        return {"ok": True}

    def get_quotes_cached(self):
        """前端即讀報價快取(不打網路)。刷新器尚未啟動時回空 dict。"""
        return self._refresher.get_cache() if self._refresher else {}

    # ---- TAIFEX 官方資料源 (台股 VIX / 台指期) ----
    @staticmethod
    def _is_decimal(tok):
        return "." in tok and tok.replace(".", "", 1).replace("-", "", 1).isdigit()

    def _taifex_vix(self):
        """台股波動率指數:讀取當月與前兩個月的官方每日檔,組出最新值、前一日收盤與走勢。"""
        res = {"price": None, "prev": None, "change": None, "changePct": None,
               "spark": [], "error": None}
        try:
            today = date.today()
            yms, y, m = [], today.year, today.month
            for _ in range(3):
                yms.append(f"{y}{m:02d}")
                m -= 1
                if m == 0:
                    m, y = 12, y - 1
            series = []      # [(date, vix)]  由舊到新
            last_prev_close = None
            for ym in reversed(yms):
                try:
                    r = self._http().get(TAIFEX_VIX_FILE.format(ym=ym), timeout=12, headers=HEADERS)
                    if r.status_code != 200:
                        continue
                    for line in r.content.decode("big5", "ignore").splitlines():
                        parts = [p.strip() for p in line.split("\t")]
                        if not parts or not (parts[0].isdigit() and len(parts[0]) == 8):
                            continue
                        decs = [p for p in parts[1:] if self._is_decimal(p)]
                        if not decs:
                            continue
                        series.append((parts[0], float(decs[0])))     # 當日 VIX
                        if len(decs) >= 2:
                            last_prev_close = float(decs[1])          # 前一交易日收盤
                except Exception:
                    continue
            if series:
                res["price"] = series[-1][1]
                res["prev"] = last_prev_close
                if last_prev_close:
                    res["change"] = res["price"] - last_prev_close
                    res["changePct"] = (res["price"] - last_prev_close) / last_prev_close * 100
                res["spark"] = [v for _, v in series[-30:]]
            else:
                res["error"] = "no data"
        except Exception as e:
            log.warning("_taifex_vix failed: %s", e)
            res["error"] = str(e)
        return res

    def _taifex_txf(self):
        """台指期:由 TAIFEX MIS 即時行情取臺股期貨 (TXF) 近月合約。"""
        import re
        res = {"price": None, "prev": None, "change": None, "changePct": None,
               "spark": [], "error": None}
        try:
            r = self._http().post(TAIFEX_MIS_QUOTE, data=json.dumps({"MarketType": "0", "Objects": ["TXF"]}),
                                  headers=TAIFEX_MIS_HEADERS, timeout=12)
            ql = (r.json().get("RtData", {}) or {}).get("QuoteList", []) or []
            # 近月合約:SymbolID 形如 TXF<月碼A-L><年尾數>-F (非價差、非現貨 -S)
            near = next((q for q in ql if re.match(r"^TXF[A-L]\d-F$", q.get("SymbolID", ""))), None)
            if not near:
                res["error"] = "no contract"
                return res
            last = self._f(near.get("CLastPrice") or None)
            ref = self._f(near.get("CRefPrice") or None)
            res["price"] = last
            if last is not None and ref:
                res["prev"] = ref
                res["change"] = last - ref
                res["changePct"] = (last - ref) / ref * 100
            if res["price"] is None:
                res["error"] = "no price"
        except Exception as e:
            log.warning("_taifex_txf failed: %s", e)
            res["error"] = str(e)
        return res

    def _fetch_one(self, sym):
        res = {"price": None, "prev": None, "change": None, "changePct": None,
               "spark": [], "market_date": None, "prev_date": None, "error": None}
        try:
            r = self._http().get(YAHOO_CHART.format(sym=sym), timeout=12, headers=HEADERS)
            r.raise_for_status()
            data = r.json()["chart"]["result"][0]
            meta = data.get("meta", {})
            ts = data.get("timestamp", []) or []
            gmt = meta.get("gmtoffset", 0) or 0
            # 交易日以「交易所當地時區」為準 (utc 秒數 + gmtoffset 後取日期)
            def _sess_date(t):
                return datetime.utcfromtimestamp(int(t) + gmt).strftime("%Y-%m-%d")
            raw = data["indicators"]["quote"][0].get("close", []) or []
            # 對齊時間戳與收盤,保留每筆交易日 (排除尚未產生的 None 當日 bar)
            pairs = [(ts[i], float(raw[i])) for i in range(min(len(ts), len(raw)))
                     if raw[i] is not None]
            closes = [c for _, c in pairs]
            if closes:
                live = meta.get("regularMarketPrice")
                price = float(live) if live is not None else closes[-1]
                res["price"] = price
                # 現價所屬交易日 (交易所當地時區)
                rmt = meta.get("regularMarketTime")
                md = _sess_date(rmt) if rmt else (_sess_date(pairs[-1][0]) if pairs else None)
                res["market_date"] = md
                # 前一交易日收盤 = 交易日 < 現價交易日 的最後一筆收盤。
                # 不可用陣列倒數第二筆:當日 daily bar 可能仍為 None (如台股盤中/剛收盤),
                # closes[-1] 其實已是昨收、closes[-2] 會抓到前天 → 當日損益失真。
                prev = prev_dt = None
                for t, c in pairs:
                    dt = _sess_date(t)
                    if md is None or dt < md:
                        prev, prev_dt = c, dt
                if prev is None:                      # 退路:meta.previousClose 或倒數第二筆
                    mp = meta.get("previousClose")
                    if mp is not None:
                        prev = float(mp)
                    elif len(closes) >= 2:
                        prev, prev_dt = closes[-2], _sess_date(pairs[-2][0])
                res["prev_date"] = prev_dt
                if prev:
                    res["prev"] = prev
                    res["change"] = price - prev
                    res["changePct"] = (price - prev) / prev * 100
                # 走勢線:最後一筆收盤日就是現價交易日時以現價取代該點,否則附加現價
                spark = closes[-30:]
                if live is not None and pairs:
                    if _sess_date(pairs[-1][0]) == md and len(spark) >= 1:
                        spark = spark[:-1] + [price]
                    else:
                        spark = (spark + [price])[-30:]
                res["spark"] = spark
            else:
                res["error"] = "no data"
        except Exception as e:
            log.warning("_fetch_one %s failed: %s", sym, e)
            res["error"] = str(e)
        return res

    # ---- 詳細頁 K 線 + 技術指標 ----
    def get_chart_detail(self, symbol, timeframe, overlays=None, panels=None,
                         start=None, end=None):
        """回傳價格線 + 使用者勾選的均線疊圖與副圖指標(於後端計算,前端只負責繪圖)。
        提供 start/end (YYYY-MM-DD) 時改用自訂區間。"""
        overlays = overlays or []
        panels = panels or []
        spec = analysis.resolve_fetch_spec(timeframe, start or None, end or None)
        if spec is None:
            return {"error": "unknown timeframe"}
        ohlcv = self._ohlcv(symbol, spec)
        if ohlcv.get("error"):
            return {"error": ohlcv["error"]}

        o, h, lo, c, v = ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
        result = {
            "labels": ohlcv["labels"],
            "open": o, "high": h, "low": lo, "close": c,
            "overlays": {},
            "panels": {},
            "meta": {"timeframe": timeframe, "bars": len(c),
                     "last": next((x for x in reversed(c) if x is not None), None)},
        }
        for name in overlays:
            if name.startswith("sma_"):
                try:
                    period = int(name.split("_")[1])
                except (IndexError, ValueError):
                    continue
                result["overlays"][name] = ta.sma(c, period)

        for name in panels:
            if name == "volume":
                up = [(c[i] is not None and o[i] is not None and c[i] >= o[i])
                      for i in range(len(c))]
                result["panels"]["volume"] = {"kind": "bar", "values": v, "up": up,
                                              "ma": ta.sma(v, 20)}
            elif name == "kd":
                k, d = ta.stochastic_kd(h, lo, c)
                result["panels"]["kd"] = {"kind": "lines",
                                          "series": {"K": k, "D": d},
                                          "guides": [20, 80]}
            elif name == "rsi":
                result["panels"]["rsi"] = {"kind": "lines",
                                           "series": {"RSI": ta.rsi(c)},
                                           "guides": [30, 70]}
            elif name == "macd":
                m, s, hist = ta.macd(c)
                result["panels"]["macd"] = {"kind": "macd",
                                            "series": {"MACD": m, "Signal": s},
                                            "hist": hist}
            elif name == "obv":
                result["panels"]["obv"] = {"kind": "lines",
                                           "series": {"OBV": ta.obv(c, v)}}
            elif name == "bollinger":
                ub, mid, lb = ta.bollinger(c)
                result["panels"]["bollinger"] = {"kind": "band",
                                                 "series": {"上軌": ub, "中軌": mid,
                                                            "下軌": lb, "收盤": c}}

        # 技術訊號:用完整(暖身)序列偵測最新狀態,不隨顯示範圍裁切。
        result["signals"] = sig.detect_all(o, h, lo, c, v)

        # 指標已用「暖身+可見」的完整序列算好,現在裁掉早於 visible_start 的暖身段,
        # 讓 MA60 等指標在整個顯示範圍都有值。
        self._slice_to_visible(result, ohlcv.get("ts", []), spec.get("visible_start"))
        return result

    @staticmethod
    def _slice_to_visible(result, ts, visible_start):
        if not visible_start or not ts:
            return
        vs = int(datetime(*map(int, visible_start.split("-")), tzinfo=timezone.utc).timestamp())
        i = next((k for k, t in enumerate(ts) if t >= vs), 0)
        if i <= 0:
            return
        result["labels"] = result["labels"][i:]
        for key in ("open", "high", "low", "close"):
            if key in result:
                result[key] = result[key][i:]
        for k in result["overlays"]:
            result["overlays"][k] = result["overlays"][k][i:]
        for pd in result["panels"].values():
            for field in ("values", "up", "ma", "hist"):
                if field in pd:
                    pd[field] = pd[field][i:]
            if "series" in pd:
                for sk in pd["series"]:
                    pd["series"][sk] = pd["series"][sk][i:]
        result["meta"]["bars"] = len(result["close"])
        result["meta"]["last"] = next((x for x in reversed(result["close"]) if x is not None), None)

    def _ohlcv(self, symbol, spec, ttl=90):
        key = (symbol, spec["key"])
        hit = self._ohlcv_cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        payload = {"error": None}
        try:
            r = self._http().get(
                YAHOO_CHART_Q.format(sym=symbol, query=spec["query"]),
                timeout=14, headers=HEADERS)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            meta = res.get("meta", {})
            gmt = meta.get("gmtoffset", 0) or 0        # 交易所時區偏移(秒),小時線標籤需用
            ts = res.get("timestamp", []) or []
            q = res["indicators"]["quote"][0]
            payload["ts"] = list(ts)
            payload["labels"] = format_labels(ts, spec["fmt"], gmt)
            payload["open"] = [self._f(x) for x in q.get("open", [])]
            payload["high"] = [self._f(x) for x in q.get("high", [])]
            payload["low"] = [self._f(x) for x in q.get("low", [])]
            payload["close"] = [self._f(x) for x in q.get("close", [])]
            payload["volume"] = [self._f(x) for x in q.get("volume", [])]
            normalize_ohlcv(payload)      # 剔除 close=None 的 bar、volume 補 0
        except Exception as e:
            log.warning("_ohlcv %s failed: %s", symbol, e)
            payload["error"] = str(e)
        self._ohlcv_cache[key] = (time.time(), payload)
        return payload

    @staticmethod
    def _f(x):
        return float(x) if x is not None else None

    def timeframes(self):
        return list(TIMEFRAMES.keys())

    # ---- 財報日期 (需 Yahoo crumb) ----
    def get_earnings(self, symbols):
        out = {}
        symbols = list(dict.fromkeys(symbols or []))
        if not symbols:
            return out
        if not self._ensure_crumb():
            return out

        def one(sym):
            try:
                r = self._http().get(YAHOO_SUMMARY.format(sym=sym, crumb=self._crumb),
                                     timeout=12, headers=HEADERS)
                if r.status_code != 200:
                    return sym, None
                ce = r.json()["quoteSummary"]["result"][0].get("calendarEvents", {})
                ed = (ce.get("earnings", {}) or {}).get("earningsDate", [])
                if ed:
                    return sym, {"date": ed[0].get("fmt"),
                                 "estimate": bool(ce["earnings"].get("isEarningsDateEstimate"))}
            except Exception as e:
                log.warning("get_earnings %s failed: %s", sym, e)
            return sym, None

        with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as ex:
            for sym, info in ex.map(one, symbols):
                if info:
                    out[sym] = info
        return out

    def _ensure_crumb(self):
        if self._crumb:
            return True
        with self._crumb_lock:                     # 只讓一條執行緒去抓 crumb,其餘等待後直接複用
            if self._crumb:
                return True
            try:
                s = self._http()
                s.get("https://fc.yahoo.com", timeout=10, headers=HEADERS)
                crumb = s.get(YAHOO_CRUMB, timeout=10, headers=HEADERS).text.strip()
                if crumb and "<" not in crumb and len(crumb) < 40:
                    self._crumb = crumb
                    # 存下取得 crumb 時的 cookies,供其他工作執行緒的新 session 注入(見 _http)
                    self._crumb_cookies = [copy.copy(c) for c in s.cookies]
                    return True
            except Exception as e:
                log.warning("_ensure_crumb failed: %s", e)
        return False

    # ---- AI 分析設定 ----
    def get_ai_config(self):
        cfg = self._load("ai_config.json", {})
        return {
            "provider": cfg.get("provider", "none"),
            "prompt": cfg.get("prompt", DEFAULT_AI_PROMPT),
            "keys": cfg.get("keys", {}),
            "models": analysis.resolve_models(cfg.get("models", {})),
        }

    def save_ai_config(self, cfg):
        return self._save("ai_config.json", cfg or {})

    def ai_analyze(self, provider, prompt, symbol, timeframe, start=None, end=None, force=False):
        """呼叫選定的 AI 供應商,回傳精簡的買賣建議與目標價。
        同一標的「每天只實際呼叫一次」:當天已評估過會回傳快取,force=True 才重新評估。"""
        if not provider or provider == "none":
            return {"ok": False, "error": "未啟用 AI 輸出"}
        cfg = self.get_ai_config()
        api_key = (cfg["keys"] or {}).get(provider, "").strip()
        if not api_key:
            return {"ok": False, "error": f"尚未設定 {provider} 的 API Key"}
        model = cfg["models"].get(provider, PROVIDER_MODELS.get(provider, ""))

        today = date.today().isoformat()
        cache = self._load("ai_cache.json", {})
        hit = cache.get(symbol)
        if (not force and hit and hit.get("date") == today
                and hit.get("provider") == provider):
            return {"ok": True, "text": hit["text"], "model": hit.get("model"),
                    "cached": True, "date": today}

        # 收集當前技術面數據作為上下文
        detail = self.get_chart_detail(
            symbol, timeframe,
            overlays=["sma_5", "sma_10", "sma_20", "sma_60"],
            panels=["kd", "rsi", "macd"], start=start, end=end)
        quote = self._fetch_one(symbol)
        context = analysis.build_context_text(symbol, quote, detail)
        full_prompt = f"{prompt}\n\n【最新技術面數據】\n{context}"

        try:
            url, headers, body = analysis.build_ai_request(provider, model, api_key, full_prompt)
            r = requests.post(url, headers=headers, json=body, timeout=40)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:180]}"}
            text = analysis.parse_ai_response(provider, r.json())
            cache[symbol] = {"date": today, "provider": provider, "text": text, "model": model}
            self._save("ai_cache.json", cache)
            return {"ok": True, "text": text, "model": model, "context": context,
                    "cached": False, "date": today}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---- 錢包 / 持倉 (SQLite) ----
    def _db(self):
        conn = sqlite3.connect(_file("wallet.db"))
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, name TEXT, side TEXT DEFAULT 'buy',
            quantity REAL NOT NULL,
            price REAL NOT NULL, date TEXT NOT NULL, created_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL, date TEXT NOT NULL,
            note TEXT, currency TEXT DEFAULT 'USD', created_at TEXT)""")
        # 遷移:若舊資料庫缺 side 欄位,自動補上
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
        if "side" not in cols:
            conn.execute("ALTER TABLE transactions ADD COLUMN side TEXT DEFAULT 'buy'")
            conn.execute("UPDATE transactions SET side='sell' WHERE quantity < 0")
            conn.execute("UPDATE transactions SET quantity=ABS(quantity)")
        # 遷移:舊 deposits 缺 currency 欄位,補上並預設為美金
        dcols = [r[1] for r in conn.execute("PRAGMA table_info(deposits)").fetchall()]
        if "currency" not in dcols:
            conn.execute("ALTER TABLE deposits ADD COLUMN currency TEXT DEFAULT 'USD'")
        return conn

    @staticmethod
    def _ccy_of(symbol):
        """由標的代號判斷計價幣別:.TW / .TWO 結尾為台股 (TWD),其餘視為美股 (USD)。"""
        s = (symbol or "").upper()
        return "TWD" if s.endswith(".TW") or s.endswith(".TWO") else "USD"

    def _fx_twd_per_usd(self):
        """美元兌台幣匯率 (1 USD = ? TWD),用於把台幣資產折合美金計算總計。"""
        try:
            p = self._fetch_one("TWD=X").get("price")
            return float(p) if p else None
        except Exception:
            return None

    def wallet_list(self):
        conn = self._db()
        try:
            rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def wallet_add(self, symbol, name, quantity, price, date_str, side="buy"):
        try:
            symbol = (symbol or "").strip().upper()
            q, p = abs(float(quantity)), float(price)
            side = side if side in ("buy", "sell") else "buy"
            if not symbol or p < 0 or not date_str:
                return {"ok": False, "error": "欄位不完整"}
            if q == 0:
                return {"ok": False, "error": "數量不可為 0"}
            conn = self._db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO transactions(symbol,name,side,quantity,price,date,created_at) VALUES(?,?,?,?,?,?,?)",
                        (symbol, name or symbol, side, q, p, date_str,
                         datetime.now().isoformat(timespec="seconds")))
            finally:
                conn.close()
            self._invalidate_history_cache()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def wallet_delete(self, tx_id):
        conn = self._db()
        try:
            with conn:
                conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        finally:
            conn.close()
        self._invalidate_history_cache()
        return {"ok": True}

    def wallet_holdings(self):
        """依幣別 (USD / TWD) 分別彙總持倉、損益與投入資金,並用即時匯率折算美金總計。
        金錢數學全部委派給 wallet.py 的純函式(enrich_holding / summarize_currency /
        combine_currencies),本方法只負責抓報價與匯率等 I/O。"""
        txs = self.wallet_list()
        for t in txs:
            t["currency"] = self._ccy_of(t["symbol"])
        holds = wl.aggregate_holdings(txs)["holdings"]
        quotes = self.get_quotes([h["symbol"] for h in holds]) if holds else {}

        enriched = []
        for h in holds:
            sym = h["symbol"]
            q = quotes.get(sym) or {}
            mdate = q.get("market_date")
            same_day = [t for t in txs
                        if t["symbol"] == sym and mdate and t.get("date") == mdate]
            e = wl.enrich_holding(h, q, same_day)
            e["currency"] = self._ccy_of(sym)
            enriched.append(e)

        deposits = self.deposit_list()
        for d in deposits:
            if not d.get("currency"):
                d["currency"] = "USD"

        ccy_blocks = {}
        for ccy in ("USD", "TWD"):
            c_holds = [h for h in enriched if h["currency"] == ccy]
            c_txs = [t for t in txs if t["currency"] == ccy]
            realized = wl.aggregate_holdings(c_txs)["total_realized_pnl"]
            deps = sum(float(d["amount"]) for d in deposits
                       if (d.get("currency") or "USD") == ccy)
            block = wl.summarize_currency(c_holds, realized, deps)
            block["day_date"] = next((h.get("market_date") for h in c_holds if h.get("market_date")), None)
            block["prev_date"] = next((h.get("prev_date") for h in c_holds if h.get("prev_date")), None)
            block["realized_detail"] = wl.realized_breakdown(c_txs)   # 各標的已實現損益(含已平倉)
            ccy_blocks[ccy] = block

        fx = self._fx_twd_per_usd()   # 1 USD = fx TWD
        total = wl.combine_currencies(ccy_blocks["USD"], ccy_blocks["TWD"], fx)
        return {"fx": fx, "transactions": txs, "deposits": deposits,
                "ccy": ccy_blocks, "total": total}

    def wallet_history(self):
        """回傳 {USD:{...}, TWD:{...}},各幣別的歷史錢包價值與每日損益分開計算。"""
        empty = {"dates": [], "total_value": [], "portfolio_value": [], "daily_pnl": []}
        txs = self.wallet_list()
        for t in txs:
            t["currency"] = self._ccy_of(t["symbol"])
        dates = [t["date"] for t in txs if t.get("date")]
        if not dates:
            return {"USD": dict(empty), "TWD": dict(empty)}
        p1 = int(datetime.strptime(min(dates), "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        p2 = int(datetime.now(tz=timezone.utc).timestamp())
        syms = list({t["symbol"] for t in txs})

        def fetch(sym):
            now = time.time()
            with self._history_lock:
                hit = self._history_cache.get(sym)
            if hit and now - hit[0] < WALLET_HISTORY_TTL:
                return sym, hit[1]
            try:
                r = self._http().get(
                    YAHOO_CHART_Q.format(sym=sym, query=f"period1={p1}&period2={p2}&interval=1d"),
                    timeout=14, headers=HEADERS)
                res = r.json()["chart"]["result"][0]
                ts = res.get("timestamp", []) or []
                closes = res["indicators"]["quote"][0].get("close", []) or []
                series = [(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), float(c))
                          for t, c in zip(ts, closes) if c is not None]
                with self._history_lock:
                    self._history_cache[sym] = (now, series)
                return sym, series
            except Exception as e:
                log.warning("wallet_history fetch %s failed: %s", sym, e)
                return sym, []

        prices = {}
        with ThreadPoolExecutor(max_workers=min(6, len(syms))) as ex:
            for sym, series in ex.map(fetch, syms):
                prices[sym] = series
        deps = self.deposit_list()
        for d in deps:
            if not d.get("currency"):
                d["currency"] = "USD"

        out = {}
        for ccy in ("USD", "TWD"):
            c_txs = [t for t in txs if t["currency"] == ccy]
            if not any(t.get("date") for t in c_txs):
                out[ccy] = dict(empty)
                continue
            c_prices = {s: v for s, v in prices.items() if self._ccy_of(s) == ccy}
            c_deps = [d for d in deps if (d.get("currency") or "USD") == ccy]
            out[ccy] = wl.build_history(c_txs, c_prices, c_deps)
        return out

    def deposit_list(self):
        conn = self._db()
        try:
            rows = conn.execute("SELECT * FROM deposits ORDER BY date DESC, id DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def deposit_add(self, amount, date_str, note="", side="deposit", currency="USD"):
        try:
            amt = float(amount)
            if amt <= 0 or not date_str:
                return {"ok": False, "error": "金額必須大於 0"}
            if side == "withdraw":
                amt = -amt
            currency = "TWD" if str(currency).upper() == "TWD" else "USD"
            conn = self._db()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO deposits(amount,date,note,currency,created_at) VALUES(?,?,?,?,?)",
                        (amt, date_str, note or "", currency,
                         datetime.now().isoformat(timespec="seconds")))
            finally:
                conn.close()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def deposit_delete(self, dep_id):
        conn = self._db()
        try:
            with conn:
                conn.execute("DELETE FROM deposits WHERE id=?", (dep_id,))
        finally:
            conn.close()
        return {"ok": True}

    def deposit_total(self):
        conn = self._db()
        try:
            row = conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM deposits").fetchone()
            return row["total"]
        finally:
            conn.close()

    # ---- 匯入 / 匯出 ----
    def export_data(self, sections):
        try:
            sections = sections or []
            data = {"app": APP_NAME, "version": 1,
                    "exported_at": datetime.now().isoformat(timespec="seconds")}
            if "transactions" in sections:
                data["transactions"] = self.wallet_list()
                data["deposits"] = self.deposit_list()
            if "holdings" in sections:
                data["holdings"] = wl.aggregate_holdings(self.wallet_list())["holdings"]
            if "watchlist" in sections:
                data["watchlist"] = self.get_watchlist()
            if "keys" in sections:
                data["keys"] = self.get_ai_config()["keys"]
            win = webview.windows[0]
            path = win.create_file_dialog(webview.SAVE_DIALOG,
                                          save_filename="stockwallet_backup.json",
                                          file_types=("JSON (*.json)",))
            if not path:
                return {"ok": False, "error": "已取消"}
            if isinstance(path, (list, tuple)):
                path = path[0]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def import_data(self, sections):
        try:
            sections = sections or []
            win = webview.windows[0]
            paths = win.create_file_dialog(webview.OPEN_DIALOG, file_types=("JSON (*.json)",))
            if not paths:
                return {"ok": False, "error": "已取消"}
            path = paths[0] if isinstance(paths, (list, tuple)) else paths
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            applied = []
            if "watchlist" in sections and "watchlist" in data:
                self.save_watchlist(data["watchlist"])
                applied.append("觀察名單")
            if "keys" in sections and "keys" in data:
                cfg = self.get_ai_config()
                self.save_ai_config({"provider": cfg["provider"], "prompt": cfg["prompt"],
                                     "keys": {**(cfg["keys"] or {}), **(data["keys"] or {})}})
                applied.append("API 金鑰")
            if "transactions" in sections and ("transactions" in data or "holdings" in data):
                self._replace_transactions(data.get("transactions"), data.get("holdings"))
                applied.append("錢包紀錄")
                if "deposits" in data:
                    conn = self._db()
                    try:
                        with conn:
                            conn.execute("DELETE FROM deposits")
                            now = datetime.now().isoformat(timespec="seconds")
                            for d in data["deposits"]:
                                conn.execute(
                                    "INSERT INTO deposits(amount,date,note,currency,created_at) VALUES(?,?,?,?,?)",
                                    (float(d.get("amount", 0)), d.get("date", ""),
                                     d.get("note", ""),
                                     "TWD" if str(d.get("currency", "USD")).upper() == "TWD" else "USD",
                                     d.get("created_at") or now))
                    finally:
                        conn.close()
            elif "holdings" in sections and "holdings" in data:
                self._replace_transactions(None, data.get("holdings"))
                applied.append("持有標的")
            self._invalidate_history_cache()   # 交易/持倉被取代,歷史日線快取失效
            return {"ok": True, "applied": applied}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _replace_transactions(self, transactions, holdings):
        conn = self._db()
        try:
            with conn:
                conn.execute("DELETE FROM transactions")
                now = datetime.now().isoformat(timespec="seconds")
                if transactions:
                    for t in transactions:
                        # 向下相容:若舊備份無 side,由 quantity 正負推導
                        raw_q = float(t.get("quantity", 0))
                        side = t.get("side") or ("buy" if raw_q >= 0 else "sell")
                        conn.execute(
                            "INSERT INTO transactions(symbol,name,side,quantity,price,date,created_at) VALUES(?,?,?,?,?,?,?)",
                            (t.get("symbol"), t.get("name"), side, abs(raw_q),
                             float(t.get("price", 0)), t.get("date"), t.get("created_at") or now))
                elif holdings:
                    today = date.today().isoformat()
                    for h in holdings:
                        conn.execute(
                            "INSERT INTO transactions(symbol,name,side,quantity,price,date,created_at) VALUES(?,?,?,?,?,?,?)",
                            (h.get("symbol"), h.get("name"), "buy", float(h.get("qty", 0)),
                             float(h.get("avg_cost", 0)), today, now))
        finally:
            conn.close()

    # ---- 標的查詢 ----
    def search_symbol(self, q):
        q = (q or "").strip()
        if not q:
            return []
        try:
            r = self._http().get(YAHOO_SEARCH.format(q=requests.utils.quote(q)),
                                 timeout=10, headers=HEADERS)
            r.raise_for_status()
            out = []
            for it in r.json().get("quotes", []):
                sym = it.get("symbol")
                if not sym:
                    continue
                out.append({
                    "sym": sym,
                    "name": it.get("shortname") or it.get("longname") or sym,
                    "exch": it.get("exchDisp") or "",
                    "type": it.get("quoteType") or "",
                })
            return out
        except Exception as e:
            log.warning("search_symbol %r failed: %s", q, e)
            return []

    # ---- 系統通知 ----
    def notify(self, title, msg):
        if not _HAS_NOTIFY:
            return {"ok": False, "error": "winotify not available"}
        try:
            icon = resource_path("icon.ico")
            kw = {"app_id": "Stock Wallet", "title": title, "msg": msg}
            if os.path.exists(icon):
                kw["icon"] = icon
            t = Notification(**kw)
            try:
                t.set_audio(audio.Default, loop=False)
            except Exception:
                pass
            t.show()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def clear_temp(self):
        # 1. Clear memory cache
        self._ohlcv_cache.clear()
        # 2. Clear AI cache
        try:
            p = _file("ai_cache.json")
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
        # 3. Clear pywebview EBWebView temp files (will not fail if locked, ignores errors)
        try:
            webview_dir = os.path.join(os.environ.get("APPDATA", ""), "pywebview", "EBWebView", "Default")
            if os.path.exists(webview_dir):
                import shutil
                for d in ["Cache", "Code Cache", "GPUCache"]:
                    dp = os.path.join(webview_dir, d)
                    if os.path.exists(dp):
                        shutil.rmtree(dp, ignore_errors=True)
        except Exception:
            pass
        return {"ok": True}

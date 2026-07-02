"""
純邏輯:圖表抓取區間解析 + AI 分析供應商的請求/回應組裝。
不做任何網路或檔案 I/O,方便單元測試。
"""
from datetime import date, datetime, timedelta, timezone

# 詳細頁時間範圍預設。visible_days = 要「顯示」的天數;實際抓取時會往前多抓
# WARMUP_DAYS,讓 MA60 等指標在第一根可見 K 棒就已暖身完成、能畫滿整個範圍。
TIMEFRAMES = {
    "時":   {"interval": "60m", "visible_days": 5,    "fmt": "%m/%d %H:%M"},
    "天":   {"interval": "1d",  "visible_days": 30,   "fmt": "%m/%d"},
    "月":   {"interval": "1mo", "visible_days": 1825, "fmt": "%Y/%m"},
    "六個月": {"interval": "1d",  "visible_days": 182,  "fmt": "%m/%d"},
    "年":   {"interval": "1d",  "visible_days": 365,  "fmt": "%m/%d"},
}

# 各 K 棒週期為了 ~60 根均線暖身,需往前多抓的日曆天數(抓多無妨,顯示時會裁掉)。
WARMUP_DAYS = {"60m": 40, "1d": 200, "1wk": 2000, "1mo": 10000}

PROVIDER_MODELS = {
    "claude": "claude-sonnet-5",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
}

# 已停用 / 淘汰的模型代號:載入設定時自動忽略,改用上方最新預設,避免呼叫失敗。
DEPRECATED_MODELS = {
    "gemini-1.0-pro", "gemini-pro", "gemini-1.5-flash", "gemini-1.5-pro",
    "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.0-pro",
}


def resolve_models(persisted):
    """以程式最新預設為底,套用使用者於 ai_config.json 的自訂 model,但略過已淘汰代號。"""
    models = dict(PROVIDER_MODELS)
    for provider, model in (persisted or {}).items():
        if model and model not in DEPRECATED_MODELS:
            models[provider] = model
    return models

DEFAULT_AI_PROMPT = (
    "你是專業金融分析師。以下提供某標的最新的技術面數據與市場資訊。\n"
    "請綜合技術面(均線多空排列、KD、RSI、MACD、成交量趨勢)與分析師評級,\n"
    "判斷目前是否適合買入,並推估合理的進出場目標價。\n"
    "請「只」用下列三行格式輸出,不要任何額外說明或理由:\n"
    "建議:買入 / 觀望 / 賣出\n"
    "買入目標價:$數字\n"
    "賣出目標價:$數字"
)


def _epoch(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def resolve_fetch_spec(timeframe, start=None, end=None, today=None):
    """回傳 {query, fmt, key, visible_start, interval}。
    query 會往前多抓 WARMUP_DAYS 以利指標暖身;visible_start 為要顯示的起始日期,
    呼叫端計算完指標後,再把早於 visible_start 的資料裁掉。
    有 start/end(YYYY-MM-DD)則走自訂區間,否則用預設 timeframe。"""
    today = today or date.today()
    if start and end:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        if e < s:
            s, e = e, s
        span = (e - s).days
        if span <= 7:
            interval, fmt = "60m", "%m/%d %H:%M"
        elif span <= 1100:
            interval = "1d"
            fmt = "%Y/%m/%d" if span > 300 else "%m/%d"
        else:
            interval, fmt = "1wk", "%Y/%m"
        visible_start = s
        fetch_start = s - timedelta(days=WARMUP_DAYS[interval])
        p1, p2 = _epoch(fetch_start), _epoch(e + timedelta(days=1))
        key = f"{start}~{end}~{interval}"
    else:
        tf = TIMEFRAMES.get(timeframe)
        if tf is None:
            return None
        interval, fmt = tf["interval"], tf["fmt"]
        visible_start = today - timedelta(days=tf["visible_days"])
        fetch_start = visible_start - timedelta(days=WARMUP_DAYS[interval])
        p1, p2 = _epoch(fetch_start), _epoch(today + timedelta(days=1))
        key = timeframe
    return {"query": f"period1={p1}&period2={p2}&interval={interval}",
            "fmt": fmt, "key": key, "visible_start": visible_start.isoformat(),
            "interval": interval}


def build_ai_request(provider, model, api_key, prompt, max_tokens=400):
    """回傳 (url, headers, json_body)。provider: claude / openai / gemini。"""
    if provider == "claude":
        return (
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": api_key, "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            {"model": model, "max_tokens": max_tokens,
             "messages": [{"role": "user", "content": prompt}]},
        )
    if provider == "openai":
        return (
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            {"model": model, "max_tokens": max_tokens, "temperature": 0.3,
             "messages": [{"role": "user", "content": prompt}]},
        )
    if provider == "gemini":
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            {"content-type": "application/json"},
            {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}},
        )
    raise ValueError(f"unknown provider: {provider}")


def parse_ai_response(provider, data):
    """從供應商回傳 JSON 取出文字內容。"""
    if provider == "claude":
        return data["content"][0]["text"].strip()
    if provider == "openai":
        return data["choices"][0]["message"]["content"].strip()
    if provider == "gemini":
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    raise ValueError(f"unknown provider: {provider}")


def _last(seq):
    for v in reversed(seq or []):
        if v is not None:
            return v
    return None


def build_context_text(symbol, quote, detail):
    """把即時報價 + 最新技術指標整理成給 AI 的精簡數據段落。"""
    lines = [f"標的代號:{symbol}"]
    price = (quote or {}).get("price")
    if price is not None:
        chg = quote.get("changePct")
        lines.append(f"現價:{price:.2f}" + (f"(當日 {chg:+.2f}%)" if chg is not None else ""))
    ov = (detail or {}).get("overlays", {})
    ma_bits = []
    for name, label in (("sma_5", "MA5"), ("sma_10", "MA10"),
                        ("sma_20", "MA20"), ("sma_60", "MA60")):
        v = _last(ov.get(name))
        if v is not None:
            ma_bits.append(f"{label}={v:.2f}")
    if ma_bits:
        lines.append("均線:" + "、".join(ma_bits))
    panels = (detail or {}).get("panels", {})
    if "kd" in panels:
        k = _last(panels["kd"]["series"].get("K"))
        d = _last(panels["kd"]["series"].get("D"))
        if k is not None and d is not None:
            lines.append(f"KD:K={k:.1f}、D={d:.1f}")
    if "rsi" in panels:
        r = _last(panels["rsi"]["series"].get("RSI"))
        if r is not None:
            lines.append(f"RSI(14)={r:.1f}")
    if "macd" in panels:
        m = _last(panels["macd"]["series"].get("MACD"))
        s = _last(panels["macd"]["series"].get("Signal"))
        if m is not None and s is not None:
            lines.append(f"MACD={m:.3f}、Signal={s:.3f}、柱={(m - s):+.3f}")
    return "\n".join(lines)

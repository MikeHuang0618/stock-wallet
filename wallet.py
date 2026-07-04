"""
錢包 / 持倉的純計算邏輯 — 不碰資料庫或網路,方便單元測試。

交易 (transaction) 欄位:{id, symbol, name, side, quantity, price, date}
  side='buy' 表示買進,side='sell' 表示賣出;quantity 一律為正數。
  若 side 缺失,則向下相容:以 quantity 正負號判斷方向。
持倉 (holding) 由交易彙總而來,採平均成本法。
"""
from collections import defaultdict

EPS = 1e-9


def _resolve_side(t):
    """從交易紀錄推導方向與正數量。若有 side 欄位就用它;否則向下相容由 quantity 正負判斷。"""
    side = t.get("side")
    q = float(t["quantity"])
    if side:
        return side, abs(q)
    return ("buy" if q >= 0 else "sell"), abs(q)


def _accumulate_positions(transactions):
    """把交易依平均成本法彙總成各標的部位(內部共用,不對外)。

    回傳 {symbol: {qty, cost, name, realized_pnl, last_date}}。賣出時以當下平均成本
    沖銷成本並累加已實現損益;淨數量歸零(平倉)時 qty/cost 歸零。
    aggregate_holdings 與 realized_breakdown 共用此彙總,避免重複實作損益數學。
    """
    order = sorted(transactions, key=lambda t: (t.get("date", ""), t.get("id", 0)))
    pos = {}
    for t in order:
        s = t["symbol"]
        side, q = _resolve_side(t)
        p = float(t["price"])
        e = pos.setdefault(s, {"qty": 0.0, "cost": 0.0, "name": t.get("name") or s,
                                "realized_pnl": 0.0, "last_date": t.get("date")})
        if t.get("name"):
            e["name"] = t["name"]
        if t.get("date"):
            e["last_date"] = t["date"]      # order 已依日期排序,最後一筆即最新交易日
        if side == "buy":
            e["qty"] += q
            e["cost"] += q * p
        else:
            avg = e["cost"] / e["qty"] if e["qty"] > EPS else 0.0
            sell = min(q, e["qty"]) if e["qty"] > 0 else 0.0
            e["realized_pnl"] += (p - avg) * sell
            e["cost"] -= avg * sell
            e["qty"] -= q
            if abs(e["qty"]) < EPS:
                e["qty"] = 0.0
                e["cost"] = 0.0
    return pos


def aggregate_holdings(transactions):
    """把交易彙總成目前持倉。已平倉(淨數量歸零)的標的不列入。
    採平均成本法:賣出時以當下平均成本沖銷成本。
    回傳 {"holdings": [...], "total_realized_pnl": float}。
    每筆 holding 含 realized_pnl(該標的已實現損益)。"""
    pos = _accumulate_positions(transactions)
    total_realized = sum(e["realized_pnl"] for e in pos.values())
    out = []
    for s, e in pos.items():
        if abs(e["qty"]) < EPS:
            continue
        avg = e["cost"] / e["qty"] if e["qty"] > EPS else 0.0
        out.append({"symbol": s, "name": e["name"], "qty": round(e["qty"], 8),
                    "avg_cost": avg, "cost_basis": e["cost"],
                    "realized_pnl": e["realized_pnl"]})
    return {"holdings": out, "total_realized_pnl": total_realized}


def realized_breakdown(transactions):
    """各標的的已實現損益明細(含已平倉標的——aggregate_holdings 會把它們丟棄)。

    回傳 [{symbol, name, realized_pnl, closed, last_date}],依 |realized_pnl| 降冪。
    只列出有已實現損益的標的(realized_pnl != 0);全買未賣 → 空清單。
    與 aggregate_holdings 共用 _accumulate_positions,損益數字保證一致。
    """
    pos = _accumulate_positions(transactions)
    out = []
    for s, e in pos.items():
        if abs(e["realized_pnl"]) < EPS:
            continue
        out.append({"symbol": s, "name": e["name"], "realized_pnl": e["realized_pnl"],
                    "closed": abs(e["qty"]) < EPS, "last_date": e.get("last_date")})
    out.sort(key=lambda x: abs(x["realized_pnl"]), reverse=True)
    return out


def enrich_holding(holding, quote, same_day_txs):
    """為單一持倉加上即時報價衍生欄位(純函式,不做 I/O)。

    holding: aggregate_holdings 產出的持倉 dict(含 qty / cost_basis)。
    quote:   即時報價 dict,可有 price / change / prev / market_date / prev_date。
    same_day_txs: 「該標的、且日期 == 報價 market_date」的交易清單,用於當日損益基準。

    當日損益採「開盤前基準」法,避免把當日買進前的漲跌算進當日損益:
        day_base = 昨收 × 當日開盤前持股 + 當日淨投入現金
        day_change = 現值 − day_base
    報價缺價(price=None)時,相關欄位回 None(絕不用 0 冒充)。
    """
    price = quote.get("price")
    prev = quote.get("prev")
    chg = quote.get("change")
    if prev is None and price is not None and chg is not None:
        prev = price - chg
    qty = holding["qty"]
    cost = holding["cost_basis"]
    mkt = price * qty if price is not None else None
    pnl = (mkt - cost) if mkt is not None else None
    pnl_pct = (pnl / cost * 100) if (pnl is not None and cost) else None

    dq = dcash = 0.0
    for t in same_day_txs:
        side, q = _resolve_side(t)
        signed = q if side == "buy" else -q
        dq += signed
        dcash += signed * float(t["price"])
    day_change = day_base = None
    if price is not None and prev is not None:
        qty_prev_close = qty - dq
        day_base = prev * qty_prev_close + dcash
        day_change = mkt - day_base

    return {**holding, "price": price, "market_value": mkt, "pnl": pnl,
            "pnl_pct": pnl_pct, "day_change": day_change, "day_base": day_base,
            "market_date": quote.get("market_date"), "prev_date": quote.get("prev_date")}


def summarize_currency(holdings, realized_pnl, deposits_amount):
    """把「單一幣別」的加值持倉彙總成錢包區塊(純函式)。

    portfolio_value = 存入資金 + 未實現損益 + 已實現損益
        (即「投入本金 + 總損益」的淨值定義;若未記錄存入資金,只反映損益)
    報酬率、當日損益率在分母 <= 0 時回 0,避免除以零。
    """
    cost = sum(h["cost_basis"] for h in holdings)
    value = sum(h["market_value"] for h in holdings if h["market_value"] is not None)
    unreal = value - cost
    pv = deposits_amount + unreal + realized_pnl
    day_change = sum(h["day_change"] for h in holdings if h.get("day_change") is not None)
    day_base = sum(h["day_base"] for h in holdings if h.get("day_base") is not None)
    return {
        "holdings": holdings, "total_cost": cost, "total_value": value,
        "total_pnl": unreal, "total_realized_pnl": realized_pnl,
        "total_deposits": deposits_amount, "portfolio_value": pv,
        "portfolio_return_pct": ((unreal + realized_pnl) / deposits_amount * 100)
        if deposits_amount > 0 else 0,
        "day_change": day_change,
        "day_change_pct": (day_change / day_base * 100) if day_base > 0 else 0,
    }


def combine_currencies(usd_block, twd_block, fx):
    """把 USD / TWD 兩個幣別區塊折算成美金總計(純函式)。

    fx = 1 USD 兌多少 TWD。
    資料新鮮度紀律:若 fx 不可得(None)且確實持有台幣資產,回傳 available=False、
    金額 None —— 絕不把台幣資產靜默折成 0 讓總資產憑空縮水。
    無台幣資產時 fx 缺失不影響,available=True。
    """
    twd_dep = twd_block["total_deposits"]
    twd_pv = twd_block["portfolio_value"]
    has_twd = abs(twd_dep) > EPS or abs(twd_pv) > EPS
    if fx is None and has_twd:
        return {"available": False, "deposits_usd": None,
                "portfolio_value_usd": None, "return_pct": None}
    conv = (lambda t: t / fx) if fx else (lambda t: 0.0)
    dep = usd_block["total_deposits"] + conv(twd_dep)
    pv = usd_block["portfolio_value"] + conv(twd_pv)
    return {"available": True, "deposits_usd": dep, "portfolio_value_usd": pv,
            "return_pct": ((pv - dep) / dep * 100) if dep > 0 else 0}


def build_history(transactions, prices_by_sym, deposits=None):
    """由交易 + 投入資金 + 各標的每日收盤價,算出每日持有錢包價值與每日交易損益。

    prices_by_sym: {symbol: [(date, close), ...]}(date 為 YYYY-MM-DD)
    每日損益採「按市值計算」:pnl[d] = 錢包價值[d] - 錢包價值[d-1] - 當日投入資金。
    回傳 {dates, total_value, daily_pnl}。
    """
    pmap = {}
    price_dates = set()
    for s, series in prices_by_sym.items():
        d = {dt: c for dt, c in series if c is not None}
        pmap[s] = d
        price_dates |= set(d)
    tx_dates = {t["date"] for t in transactions if t.get("date")}
    dep_dates = {d["date"] for d in (deposits or []) if d.get("date")}
    axis = sorted(price_dates | tx_dates | dep_dates)
    if not axis:
        return {"dates": [], "total_value": [], "daily_pnl": []}

    # 各標的沿時間軸前向填補收盤價(非交易日沿用前值)
    ff = {}
    for s in pmap:
        last, arr = None, []
        for dt in axis:
            if dt in pmap[s]:
                last = pmap[s][dt]
            arr.append(last)
        ff[s] = arr

    cashflow = {dt: 0.0 for dt in axis}
    for t in transactions:
        if t.get("date") in cashflow:
            side, q = _resolve_side(t)
            signed = q if side == "buy" else -q
            cashflow[t["date"]] += signed * float(t["price"])

    txs = sorted(transactions, key=lambda t: t.get("date", ""))
    hold = defaultdict(float)
    ti = 0
    values = []
    port_values = []

    dep_by_date = defaultdict(float)
    for d in (deposits or []):
        dep_by_date[d["date"]] += float(d["amount"])

    cum_dep = 0.0
    cum_inv = 0.0
    for idx, dt in enumerate(axis):
        cum_dep += dep_by_date[dt]
        cum_inv += cashflow[dt]
        while ti < len(txs) and txs[ti].get("date", "") <= dt:
            side, q = _resolve_side(txs[ti])
            hold[txs[ti]["symbol"]] += q if side == "buy" else -q
            ti += 1
        v = 0.0
        for s, q in hold.items():
            c = ff.get(s, [None] * len(axis))[idx]
            if c is not None:
                v += q * c
        values.append(v)
        cash_balance = cum_dep - cum_inv
        port_values.append(v + cash_balance)

    daily = []
    for i, dt in enumerate(axis):
        prev = values[i - 1] if i > 0 else 0.0
        daily.append(values[i] - prev - cashflow[dt])
    return {"dates": axis, "total_value": values, "portfolio_value": port_values, "daily_pnl": daily}

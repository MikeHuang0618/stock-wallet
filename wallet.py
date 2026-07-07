"""
錢包 / 持倉的純計算邏輯 — 不碰資料庫或網路,方便單元測試。

交易 (transaction) 欄位:{id, symbol, name, side, quantity, price, date, fee}
  side='buy'  買進、side='sell' 賣出;quantity 一律為正數。
  side='dividend'        現金股利:price 存「本次配息總金額」,quantity 固定 0。
  side='stock_dividend'  股票股利/配股:quantity 為配發股數,price=0,成本不變(攤低均價)。
  side='adjust'          拆股/持股調整:quantity 為股數增減(可正可負),price=0,成本不變。
  fee                    手續費 + 交易稅(選填,預設 0);買進進成本、賣出沖已實現損益。
  若 side 缺失,則向下相容:以 quantity 正負號判斷買/賣方向。
持倉 (holding) 由交易彙總而來,採平均成本法。
"""
import csv
import io
from collections import defaultdict
from datetime import date as _date

EPS = 1e-9

# 台股費率(標準未折)。使用者可於表單覆寫;此處僅供「預估」按鈕與具名常數,不魔法數字。
TW_TX_FEE_RATE = 0.001425    # 券商手續費率
TW_SELL_TAX_RATE = 0.003     # 證券交易稅(賣出方收取)

# 改變股數但不動成本的交易(配股、拆股/合股調整)——攤薄/濃縮平均成本。
_SHARE_ADJUST_SIDES = ("stock_dividend", "adjust")


def _resolve_side(t):
    """從交易紀錄推導方向與數量。

    buy/sell/dividend/stock_dividend 回傳正數量;adjust 保留正負號(拆股可增可減)。
    無 side 欄位時向下相容:以 quantity 正負判斷買/賣。
    """
    side = t.get("side")
    q = float(t["quantity"])
    if not side:
        return ("buy" if q >= 0 else "sell"), abs(q)
    if side == "adjust":
        return side, q          # 帶正負號:反向拆股(合股)為負
    return side, abs(q)


def estimate_tw_fee(price, quantity, side):
    """台股手續費 + 交易稅預估(供 UI「預估」按鈕填入,使用者可改)。

    買進 = 成交金額 × 手續費率;賣出 = 成交金額 ×(手續費率 + 證交稅率)。
    純函式、可測;實際費用以券商折扣為準,故僅作預設值不強制。
    """
    amount = abs(float(price)) * abs(float(quantity))
    rate = TW_TX_FEE_RATE + (TW_SELL_TAX_RATE if side == "sell" else 0.0)
    return round(amount * rate, 2)


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
        fee = float(t.get("fee") or 0.0)
        e = pos.setdefault(s, {"qty": 0.0, "cost": 0.0, "name": t.get("name") or s,
                                "realized_pnl": 0.0, "dividends": 0.0, "last_date": t.get("date")})
        if t.get("name"):
            e["name"] = t["name"]
        if t.get("date"):
            e["last_date"] = t["date"]      # order 已依日期排序,最後一筆即最新交易日
        if side == "buy":
            e["qty"] += q
            e["cost"] += q * p + fee        # 手續費計入取得成本(推高均價)
        elif side == "sell":
            avg = e["cost"] / e["qty"] if e["qty"] > EPS else 0.0
            sell = min(q, e["qty"]) if e["qty"] > 0 else 0.0
            e["realized_pnl"] += (p - avg) * sell - fee   # 賣出費用直接沖已實現損益
            e["cost"] -= avg * sell
            e["qty"] -= q
            if abs(e["qty"]) < EPS:
                e["qty"] = 0.0
                e["cost"] = 0.0
        elif side == "dividend":
            e["dividends"] += p             # price 即本次配息總金額;不動 qty/cost
        elif side in _SHARE_ADJUST_SIDES:
            e["qty"] += q                   # 配股/拆股:股數變動,成本不變 → 均價自動攤薄/濃縮
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
    total_dividends = sum(e["dividends"] for e in pos.values())
    out = []
    for s, e in pos.items():
        if abs(e["qty"]) < EPS:
            continue
        avg = e["cost"] / e["qty"] if e["qty"] > EPS else 0.0
        out.append({"symbol": s, "name": e["name"], "qty": round(e["qty"], 8),
                    "avg_cost": avg, "cost_basis": e["cost"],
                    "realized_pnl": e["realized_pnl"], "dividends": e["dividends"]})
    return {"holdings": out, "total_realized_pnl": total_realized,
            "total_dividends": total_dividends}


def realized_breakdown(transactions):
    """各標的的已實現損益明細(含已平倉標的——aggregate_holdings 會把它們丟棄)。

    回傳 [{symbol, name, realized_pnl, dividends, closed, last_date}],依
    |realized_pnl|+|dividends| 降冪。只列出有已實現損益或收過股息的標的;
    全買未賣且無配息 → 空清單。與 aggregate_holdings 共用 _accumulate_positions,
    損益/股息數字保證一致。
    """
    pos = _accumulate_positions(transactions)
    out = []
    for s, e in pos.items():
        if abs(e["realized_pnl"]) < EPS and abs(e["dividends"]) < EPS:
            continue
        out.append({"symbol": s, "name": e["name"], "realized_pnl": e["realized_pnl"],
                    "dividends": e["dividends"],
                    "closed": abs(e["qty"]) < EPS, "last_date": e.get("last_date")})
    out.sort(key=lambda x: abs(x["realized_pnl"]) + abs(x["dividends"]), reverse=True)
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


def summarize_currency(holdings, realized_pnl, deposits_amount, dividends_amount=0.0):
    """把「單一幣別」的加值持倉彙總成錢包區塊(純函式)。

    portfolio_value = 存入資金 + 未實現損益 + 已實現損益 + 累計現金股息
        (即「投入本金 + 總損益」的淨值定義;現金股利如同一筆不減持股的入金)
    報酬率、當日損益率在分母 <= 0 時回 0,避免除以零。
    dividends_amount 預設 0,舊呼叫端行為不變。
    """
    cost = sum(h["cost_basis"] for h in holdings)
    value = sum(h["market_value"] for h in holdings if h["market_value"] is not None)
    unreal = value - cost
    pv = deposits_amount + unreal + realized_pnl + dividends_amount
    day_change = sum(h["day_change"] for h in holdings if h.get("day_change") is not None)
    day_base = sum(h["day_base"] for h in holdings if h.get("day_base") is not None)
    return {
        "holdings": holdings, "total_cost": cost, "total_value": value,
        "total_pnl": unreal, "total_realized_pnl": realized_pnl,
        "total_dividends": dividends_amount,
        "total_deposits": deposits_amount, "portfolio_value": pv,
        "portfolio_return_pct": ((unreal + realized_pnl + dividends_amount) / deposits_amount * 100)
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

    # cashflow:僅買/賣影響持倉市值與投入現金,用於每日損益與淨投入。
    # div_by_date:現金股利,只進現金餘額(不影響持倉市值,故不列入 daily_pnl)。
    cashflow = {dt: 0.0 for dt in axis}
    div_by_date = defaultdict(float)
    for t in transactions:
        if t.get("date") in cashflow:
            side, q = _resolve_side(t)
            if side == "buy":
                cashflow[t["date"]] += q * float(t["price"])
            elif side == "sell":
                cashflow[t["date"]] -= q * float(t["price"])
            elif side == "dividend":
                div_by_date[t["date"]] += float(t["price"])

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
    cum_div = 0.0
    for idx, dt in enumerate(axis):
        cum_dep += dep_by_date[dt]
        cum_inv += cashflow[dt]
        cum_div += div_by_date[dt]
        while ti < len(txs) and txs[ti].get("date", "") <= dt:
            side, q = _resolve_side(txs[ti])
            sym = txs[ti]["symbol"]
            if side in ("buy", "stock_dividend"):
                hold[sym] += q
            elif side == "sell":
                hold[sym] -= q
            elif side == "adjust":
                hold[sym] += q          # 帶正負號:拆股增股 / 合股減股
            ti += 1                     # dividend 不改變持股
        v = 0.0
        for s, q in hold.items():
            c = ff.get(s, [None] * len(axis))[idx]
            if c is not None:
                v += q * c
        values.append(v)
        cash_balance = cum_dep - cum_inv + cum_div   # 現金 = 淨入金 − 淨投入 + 累計股息
        port_values.append(v + cash_balance)

    daily = []
    for i, dt in enumerate(axis):
        prev = values[i - 1] if i > 0 else 0.0
        daily.append(values[i] - prev - cashflow[dt])
    return {"dates": axis, "total_value": values, "portfolio_value": port_values, "daily_pnl": daily}


def _forward_fill(dates, by_date, before=0.0):
    """沿 dates 逐日前向填補 by_date(缺值沿用前值);首值出現前用 before。"""
    out, last = [], before
    for d in dates:
        if d in by_date and by_date[d] is not None:
            last = by_date[d]
        out.append(last)
    return out


def merge_snapshot_history(snapshots, recomputed, tol=0.01):
    """把「已落地的每日快照」(權威、不可變)與「回算補齊」(快照之前)合併成一條歷史。

    snapshots: [{date, market_value, portfolio_value}, ...](單一幣別,順序不限)。
    recomputed: build_history 的輸出(dates / total_value / portfolio_value / daily_pnl)。

    合併規則:快照最早日之前用回算,自快照最早日起改用快照 —— 因此下市/改代號
    導致回算失真時,已落地的過去區段不受影響(核心訴求:歷史是被記錄的事實)。
    reconcile_warning:若某日同時存在回算與快照且淨值相差 > tol(預設 1%),
    回報最早的分歧日供 UI 提示,絕不靜默覆蓋。daily_pnl 沿用回算值(次要指標)。
    """
    keys = ("dates", "total_value", "portfolio_value", "daily_pnl")
    if not snapshots:
        return {**{k: list(recomputed.get(k, [])) for k in keys}, "reconcile_warning": None}

    rc_dates = list(recomputed.get("dates", []))
    rc_tv = dict(zip(rc_dates, recomputed.get("total_value", [])))
    rc_pv = dict(zip(rc_dates, recomputed.get("portfolio_value", [])))
    rc_dp = dict(zip(rc_dates, recomputed.get("daily_pnl", [])))
    snaps = sorted(snapshots, key=lambda s: s["date"])
    snap_by_date = {s["date"]: s for s in snaps}
    first = snaps[0]["date"]

    merged_dates, seen = [], set()
    for d in [x for x in rc_dates if x < first] + [s["date"] for s in snaps]:
        if d not in seen:
            seen.add(d)
            merged_dates.append(d)

    total_value, portfolio_value, daily_pnl = [], [], []
    for d in merged_dates:
        if d < first:
            total_value.append(rc_tv.get(d))
            portfolio_value.append(rc_pv.get(d))
        else:
            s = snap_by_date.get(d)
            total_value.append(s["market_value"] if s else rc_tv.get(d))
            portfolio_value.append(s["portfolio_value"] if s else rc_pv.get(d))
        daily_pnl.append(rc_dp.get(d))

    warning = None
    for d in rc_dates:
        if d in snap_by_date:
            rpv, spv = rc_pv.get(d), snap_by_date[d]["portfolio_value"]
            if rpv is not None and spv is not None and abs(spv - rpv) / max(abs(rpv), 1.0) > tol:
                warning = {"date": d, "recomputed": rpv, "snapshot": spv}
            break
    return {"dates": merged_dates, "total_value": total_value,
            "portfolio_value": portfolio_value, "daily_pnl": daily_pnl,
            "reconcile_warning": warning}


def combine_history(usd_hist, twd_hist, fx_series):
    """把 USD / TWD 兩條錢包淨值歷史逐日折算成一條美金總淨值曲線(純函式)。

    usd_hist / twd_hist: {dates, portfolio_value}(build_history 或快照合併的輸出)。
    fx_series: {date: 1USD兌TWD} —— 沿日期軸前向填補;缺首值前無台幣曝險故不影響。

    某日若有台幣淨值 (>EPS) 但當日 fx 不可得 → 該日總計為 None(前端斷線顯示),
    絕不把台幣資產靜默折成 0(沿用 combine_currencies 的資料新鮮度紀律)。
    回傳 {dates, portfolio_value}(portfolio_value 以 USD 計,可能含 None)。
    """
    usd_pv = dict(zip(usd_hist.get("dates", []), usd_hist.get("portfolio_value", [])))
    twd_pv = dict(zip(twd_hist.get("dates", []), twd_hist.get("portfolio_value", [])))
    dates = sorted(set(usd_pv) | set(twd_pv))
    if not dates:
        return {"dates": [], "portfolio_value": []}

    usd_ff = _forward_fill(dates, usd_pv, before=0.0)
    twd_ff = _forward_fill(dates, twd_pv, before=0.0)
    fx_ff = _forward_fill(dates, {d: fx_series.get(d) for d in dates}, before=None)

    out = []
    for u, tw, fx in zip(usd_ff, twd_ff, fx_ff):
        if abs(tw) < EPS:
            out.append(u)                       # 無台幣曝險,匯率缺失也無妨
        elif fx:
            out.append(u + tw / fx)
        else:
            out.append(None)                    # 有台幣資產卻無匯率 → 不可折成 0
    return {"dates": dates, "portfolio_value": out}


def compute_xirr(cashflows, guess=0.1, min_days=30):
    """現金流的年化內部報酬率 (XIRR)。牛頓法為主,二分法為後備。

    cashflows: [(date, amount)] —— 入金為負(現金流出投資人)、出金/期末總值為正。
    無解、資料不足(不足一正一負)、期間 < min_days → 回 None(UI 顯示「—」),
    絕不回傳一個看似合理卻無意義的數字。日期以實際天數 / 365 折現。
    """
    flows = [(_parse_date(d), float(a)) for d, a in cashflows if a is not None]
    flows = [(d, a) for d, a in flows if d is not None]
    if len(flows) < 2:
        return None
    if not (any(a > 0 for _, a in flows) and any(a < 0 for _, a in flows)):
        return None
    t0 = min(d for d, _ in flows)
    span = (max(d for d, _ in flows) - t0).days
    if span < min_days:
        return None
    years = [((d - t0).days / 365.0, a) for d, a in flows]

    def npv(r):
        return sum(a / (1.0 + r) ** y for y, a in years)

    def dnpv(r):
        return sum(-y * a / (1.0 + r) ** (y + 1) for y, a in years)

    r = guess
    for _ in range(100):
        f = npv(r)
        d = dnpv(r)
        if abs(d) < EPS:
            break
        step = f / d
        r -= step
        if r <= -0.999999:              # 折現因子逼近奇異點,退回二分法
            break
        if abs(step) < 1e-8:
            return r
    # 後備:在 (-0.9999, 大正值) 上找變號區間再二分
    lo, hi = -0.9999, 10.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-9:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def _parse_date(s):
    """'YYYY-MM-DD' → date;無法解析回 None(不丟例外)。"""
    if isinstance(s, _date):
        return s
    try:
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return _date(y, m, d)
    except (ValueError, TypeError):
        return None


def summarize_periods(dates, portfolio_value, deposits=None, period="monthly"):
    """把淨值歷史依月/年切成期間彙總(純函式)。

    dates / portfolio_value: 逐日淨值曲線(可含 None,取每期最後一個非 None 為期末值)。
    deposits: [{date, amount}] —— 期間淨投入(入金正、出金負)。
    period: 'monthly' | 'yearly'。

    每期回傳:{period, start_value, end_value, net_deposit, pnl, return_pct}。
    pnl = 期末 − 期初 − 淨投入(把出入金排除,只留真實損益);
    return_pct 以「期初值 + 淨投入」為分母,分母 <= 0 時為 None。
    """
    def bucket(d):
        return d[:7] if period == "monthly" else d[:4]

    pairs = [(d, v) for d, v in zip(dates, portfolio_value) if d]
    if not pairs:
        return []
    dep_by_bucket = defaultdict(float)
    for dep in (deposits or []):
        if dep.get("date"):
            dep_by_bucket[bucket(dep["date"])] += float(dep["amount"])

    buckets = []
    for d, v in pairs:
        b = bucket(d)
        if not buckets or buckets[-1]["period"] != b:
            buckets.append({"period": b, "_first": None, "_last": None})
        cur = buckets[-1]
        if v is not None:
            if cur["_first"] is None:
                cur["_first"] = v
            cur["_last"] = v

    out, prev_end = [], None
    for cur in buckets:
        # 期初 = 上一期期末(連續淨值);第一期沒有前期,用自身當期首個淨值。
        start = prev_end if prev_end is not None else (cur["_first"] or 0.0)
        end = cur["_last"] if cur["_last"] is not None else start
        net_dep = dep_by_bucket.get(cur["period"], 0.0)
        pnl = end - start - net_dep
        base = start + net_dep
        out.append({"period": cur["period"], "start_value": start, "end_value": end,
                    "net_deposit": net_dep, "pnl": pnl,
                    "return_pct": (pnl / base * 100) if base > EPS else None})
        prev_end = end
    return out


def realized_by_year(transactions):
    """各年度已實現損益 + 現金股息彙總(供海外所得等年度回顧;僅呈現數字,不做稅務計算)。

    以交易日期年份分組,對「該年以前+當年」的交易做累積彙總後取差分,得到每年
    新增的已實現損益與股息。回傳 [{year, realized_pnl, dividends}],依年份升冪。
    """
    years = sorted({t["date"][:4] for t in transactions if t.get("date")})
    out, prev_r, prev_d = [], 0.0, 0.0
    for y in years:
        upto = [t for t in transactions if t.get("date") and t["date"][:4] <= y]
        agg = aggregate_holdings(upto)
        cr, cd = agg["total_realized_pnl"], agg["total_dividends"]
        out.append({"year": y, "realized_pnl": cr - prev_r, "dividends": cd - prev_d})
        prev_r, prev_d = cr, cd
    return out


# CSV 匯入的欄位別名(標頭一律轉小寫比對);中英券商格式共用。
_CSV_ALIASES = {
    "date": ("date", "日期", "成交日期", "交易日期", "trade date"),
    "symbol": ("symbol", "代號", "股票代號", "ticker", "code"),
    "side": ("side", "買賣", "類別", "別", "action", "type", "買賣別"),
    "quantity": ("quantity", "qty", "股數", "數量", "shares"),
    "price": ("price", "價格", "成交價", "單價"),
    "fee": ("fee", "費用", "手續費", "cost", "手續費及交易稅"),
    "name": ("name", "名稱", "股票名稱"),
}
_CSV_BUY = ("buy", "b", "買", "買進", "現買", "現股買進")
_CSV_SELL = ("sell", "s", "賣", "賣出", "現賣", "現股賣出")


def _normalize_date(s):
    """把 YYYY/MM/DD、YYYY.MM.DD 等統一成 YYYY-MM-DD;無法解析回 None。"""
    d = _parse_date(str(s).strip().replace("/", "-").replace(".", "-"))
    return d.isoformat() if d else None


def parse_csv_transactions(text):
    """把券商對帳單 CSV 文字解析成交易列(純函式,不碰檔案系統)。

    回傳 {"rows": [{date, symbol, side, quantity, price, fee, name}], "errors": [str]}。
    標頭以別名比對(中英不分大小寫);side 無法辨識時預設 buy;
    日期/代號/股數/價格任一缺失或非法 → 該列記入 errors 並跳過(fail loudly,不靜默吞)。
    """
    rows, errors = [], []
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {"rows": [], "errors": ["空的 CSV"]}
    idx = {}
    for i, col in enumerate(header):
        key = str(col).strip().lower()
        for field, aliases in _CSV_ALIASES.items():
            if key in aliases and field not in idx:
                idx[field] = i
    missing = [f for f in ("date", "symbol", "quantity", "price") if f not in idx]
    if missing:
        return {"rows": [], "errors": [f"缺少必要欄位:{', '.join(missing)}"]}

    def cell(row, field):
        i = idx.get(field)
        return row[i].strip() if i is not None and i < len(row) and row[i] is not None else ""

    for n, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        dt = _normalize_date(cell(row, "date"))
        sym = cell(row, "symbol").upper()
        try:
            qty = float(cell(row, "quantity").replace(",", ""))
            price = float(cell(row, "price").replace(",", ""))
        except ValueError:
            errors.append(f"第 {n} 列:股數/價格非數字,已跳過")
            continue
        if not dt or not sym:
            errors.append(f"第 {n} 列:日期或代號缺失,已跳過")
            continue
        raw_side = cell(row, "side").lower()
        side = "sell" if raw_side in _CSV_SELL else "buy"
        fee_txt = cell(row, "fee").replace(",", "")
        try:
            fee = abs(float(fee_txt)) if fee_txt else 0.0
        except ValueError:
            fee = 0.0
        rows.append({"date": dt, "symbol": sym, "side": side,
                     "quantity": abs(qty), "price": abs(price), "fee": fee,
                     "name": cell(row, "name")})
    return {"rows": rows, "errors": errors}

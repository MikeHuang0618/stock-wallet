"""CSV 匯入解析 parse_csv_transactions golden tests。欄位對應、日期正規化、fail-loudly。"""
import wallet as w


def test_parse_basic_english_header():
    text = "date,symbol,side,quantity,price,fee\n2026-01-02,AAPL,buy,10,150,1.5\n"
    r = w.parse_csv_transactions(text)
    assert r["errors"] == []
    row = r["rows"][0]
    assert row == {"date": "2026-01-02", "symbol": "AAPL", "side": "buy",
                   "quantity": 10.0, "price": 150.0, "fee": 1.5, "name": ""}


def test_parse_chinese_header_and_slash_date():
    text = "日期,代號,買賣,股數,價格\n2026/03/05,2330.TW,賣,1000,900\n"
    r = w.parse_csv_transactions(text)
    row = r["rows"][0]
    assert row["date"] == "2026-03-05"        # 斜線日期正規化為破折號
    assert row["symbol"] == "2330.TW"
    assert row["side"] == "sell"              # 「賣」→ sell
    assert row["quantity"] == 1000.0


def test_missing_required_column_reports_error():
    text = "date,symbol,quantity\n2026-01-02,AAPL,10\n"    # 缺 price
    r = w.parse_csv_transactions(text)
    assert r["rows"] == []
    assert any("price" in e for e in r["errors"])


def test_bad_number_row_skipped_not_silently_dropped():
    text = "date,symbol,side,quantity,price\n2026-01-02,AAPL,buy,ten,150\n2026-01-03,NVDA,buy,5,100\n"
    r = w.parse_csv_transactions(text)
    assert len(r["rows"]) == 1
    assert r["rows"][0]["symbol"] == "NVDA"
    assert len(r["errors"]) == 1              # 壞列記入 errors,不靜默吞掉


def test_thousands_separator_and_unknown_side_defaults_buy():
    text = "date,symbol,side,quantity,price\n2026-01-02,AAPL,?,\"1,000\",\"1,234.5\"\n"
    r = w.parse_csv_transactions(text)
    row = r["rows"][0]
    assert row["quantity"] == 1000.0
    assert row["price"] == 1234.5
    assert row["side"] == "buy"                # 無法辨識的 side 預設買進

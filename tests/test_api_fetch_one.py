import warnings

import api


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Session:
    def __init__(self, payload):
        self._p = payload

    def get(self, *a, **k):
        return _Resp(self._p)


def _chart(ts, closes, price, rmt, gmt=-14400):
    return {"chart": {"result": [{
        "meta": {"regularMarketPrice": price, "regularMarketTime": rmt, "gmtoffset": gmt},
        "timestamp": ts,
        "indicators": {"quote": [{"close": closes}]}}]}}


def _api_with(payload):
    a = api.Api()
    a._local.session = _Session(payload)
    return a


T15, T16 = 1760535000, 1760621400


def test_prev_close_is_last_session_before_market_date():
    a = _api_with(_chart([T15, T16], [100.0, 102.0], 103.0, T16 + 3600))
    q = a._fetch_one("AAPL")
    assert q["error"] is None
    assert q["price"] == 103.0 and q["prev"] == 100.0
    assert q["market_date"] == "2025-10-16" and q["prev_date"] == "2025-10-15"


def test_fetch_one_emits_no_deprecation_warning():
    a = _api_with(_chart([T15, T16], [100.0, 102.0], 103.0, T16 + 3600))
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        q = a._fetch_one("AAPL")
    assert q["error"] is None

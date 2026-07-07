"""每日快照合併 merge_snapshot_history golden tests。
核心訴求:快照(權威)覆蓋回算,過去區段在回算失真/資料消失時仍不變。"""
import pytest

import wallet as w

A = pytest.approx


def _recomputed():
    return {"dates": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "total_value": [1000, 1050, 1100],
            "portfolio_value": [1000, 1050, 1100],
            "daily_pnl": [0, 50, 50]}


def test_snapshots_take_authority_over_recompute():
    """01-01 快照之前用回算;01-02、01-03 有快照 → 用快照值。"""
    snaps = [{"date": "2026-01-02", "market_value": 9999, "portfolio_value": 9999},
             {"date": "2026-01-03", "market_value": 8888, "portfolio_value": 8888}]
    m = w.merge_snapshot_history(snaps, _recomputed())
    assert m["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert m["portfolio_value"] == [A(1000), A(9999), A(8888)]


def test_past_preserved_when_recompute_goes_empty():
    """標的下市/改代號使回算變空,但快照仍保留完整過去(不憑空消失)。"""
    snaps = [{"date": "2026-01-01", "market_value": 1000, "portfolio_value": 1000},
             {"date": "2026-01-02", "market_value": 1050, "portfolio_value": 1050}]
    empty = {"dates": [], "total_value": [], "portfolio_value": [], "daily_pnl": []}
    m = w.merge_snapshot_history(snaps, empty)
    assert m["dates"] == ["2026-01-01", "2026-01-02"]
    assert m["portfolio_value"] == [A(1000), A(1050)]


def test_reconcile_warning_when_boundary_diverges():
    """回算與快照在同一日淨值相差 > 1% → 回報最早分歧日,不靜默覆蓋。"""
    snaps = [{"date": "2026-01-02", "market_value": 9999, "portfolio_value": 9999}]
    m = w.merge_snapshot_history(snaps, _recomputed())
    assert m["reconcile_warning"]["date"] == "2026-01-02"
    assert m["reconcile_warning"]["recomputed"] == A(1050)
    assert m["reconcile_warning"]["snapshot"] == A(9999)


def test_no_warning_within_tolerance():
    snaps = [{"date": "2026-01-02", "market_value": 1050, "portfolio_value": 1050.5}]
    m = w.merge_snapshot_history(snaps, _recomputed())   # 0.5/1050 ≈ 0.05% < 1%
    assert m["reconcile_warning"] is None


def test_no_snapshots_returns_recompute_unchanged():
    m = w.merge_snapshot_history([], _recomputed())
    assert m["portfolio_value"] == [A(1000), A(1050), A(1100)]
    assert m["reconcile_warning"] is None

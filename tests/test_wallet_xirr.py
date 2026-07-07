"""XIRR(年化內部報酬率)golden tests。對照定義方程,涵蓋無解 / 資料不足 / 期間過短。"""
import pytest

import wallet as w

A = pytest.approx


def test_single_year_ten_percent():
    """一年 -100 → +110 → XIRR = 10%。"""
    r = w.compute_xirr([("2025-01-01", -100), ("2026-01-01", 110)])
    assert r == A(0.10, abs=1e-6)


def test_staggered_flows_satisfy_npv_zero():
    """兩筆錯期入金:求得的 r 使淨現值方程 ≈ 0(解的定義性檢查)。"""
    flows = [("2025-01-01", -100), ("2025-07-01", -100), ("2026-01-01", 210)]
    r = w.compute_xirr(flows)
    assert r is not None
    from datetime import date
    t0 = date(2025, 1, 1)
    npv = sum(a / (1 + r) ** ((date(*map(int, d.split("-"))) - t0).days / 365.0)
              for d, a in flows)
    assert npv == A(0.0, abs=1e-4)


def test_all_negative_flows_no_solution():
    assert w.compute_xirr([("2025-01-01", -100), ("2026-01-01", -50)]) is None


def test_insufficient_flows_returns_none():
    assert w.compute_xirr([("2025-01-01", -100)]) is None


def test_span_shorter_than_min_days_returns_none():
    """持有 < 30 天 → 年化數字無意義,回 None(UI 顯示「—」)。"""
    assert w.compute_xirr([("2026-01-01", -100), ("2026-01-10", 105)]) is None

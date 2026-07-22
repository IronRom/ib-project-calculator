"""Tests for 707/пр extrapolation rules: п.131 (ф.8.4/8.5) and п.133 (ф.8.6–8.8)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.conftest import make_db_returning, make_row
from app.services.calculator import _match_row, _a_only_price


# ── п.131: X below Xмин/2 → Кэ scaling ───────────────────────────────────────

def test_deep_low_extrapolation_applies_ke():
    """X=20 with Xмин=100: X < Xмин/2=50 → Кэ = 20/50 = 0.4."""
    rows = [make_row(x_min=100.0, x_max=500.0, a=17.7, b=0.234, x_unit="п.м")]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=311, x_value=20.0, x_unit="п.м")
    assert match is not None
    assert match.extrapolated
    assert abs(match.extrap_scale - 0.4) < 1e-9
    assert "ф.8.4" in match.note


def test_deep_low_ke_floor_0_1():
    """Кэ never drops below 0.1 (707/пр ф.8.5)."""
    rows = [make_row(x_min=100.0, x_max=500.0, a=17.7, b=0.234, x_unit="п.м")]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=311, x_value=1.0, x_unit="п.м")
    assert match is not None
    assert match.extrap_scale == 0.1


def test_shallow_low_uses_standard_formula():
    """X=60 with Xмин=100: X ≥ Xмин/2 → standard 0.4/0.6, no Кэ."""
    rows = [make_row(x_min=100.0, x_max=500.0, a=17.7, b=0.234, x_unit="п.м")]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=311, x_value=60.0, x_unit="п.м")
    assert match is not None
    assert match.extrapolated
    assert match.extrap_scale == 1.0


def test_above_max_no_ke():
    rows = [make_row(x_min=100.0, x_max=500.0, a=17.7, b=0.234, x_unit="п.м")]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=311, x_value=900.0, x_unit="п.м")
    assert match is not None
    assert match.extrapolated
    assert match.extrap_scale == 1.0


# ── п.133: a-only tables — interpolation / damped extrapolation ──────────────

def _a_only_rows():
    return [
        make_row(x_min=None, x_max=50.0, a=612.9, b=None, x_unit="м³"),
        make_row(x_min=50.0, x_max=300.0, a=800.0, b=None, x_unit="м³"),
    ]


def test_a_only_interpolation_between_points():
    """ф.8.6: X=175 between points (50, 612.9) and (300, 800) → linear."""
    price, row, note = _a_only_price(_a_only_rows(), 175.0)
    expected = 612.9 + (175.0 - 50.0) / (300.0 - 50.0) * (800.0 - 612.9)
    assert abs(price - expected) < 0.01
    assert "8.6" in note


def test_a_only_above_max_damped():
    """ф.8.8: X=400 above 300 → slope of last segment × 0.6."""
    price, row, note = _a_only_price(_a_only_rows(), 400.0)
    slope = (800.0 - 612.9) / (300.0 - 50.0)
    expected = 800.0 + slope * (400.0 - 300.0) * 0.6
    assert abs(price - expected) < 0.01
    assert "8.8" in note


def test_a_only_below_min_damped_with_floor():
    """ф.8.7: X below first point, damped 0.6, never below 0.1·a₁."""
    price, row, note = _a_only_price(_a_only_rows(), 10.0)
    slope = (800.0 - 612.9) / (300.0 - 50.0)
    expected = max(612.9 - slope * (50.0 - 10.0) * 0.6, 0.1 * 612.9)
    assert abs(price - expected) < 0.01
    assert "8.7" in note


def test_a_only_not_applied_to_mixed_tables():
    """Table with any b-carrying row → standard path."""
    rows = _a_only_rows() + [make_row(x_min=300.0, x_max=1000.0, a=784.3, b=1.446)]
    assert _a_only_price(rows, 2000.0) is None


def test_a_only_not_applied_to_unit_priced():
    """Rows without boundaries (unit-priced) → not enough points."""
    rows = [make_row(x_min=None, x_max=None, a=70.0, b=None)]
    assert _a_only_price(rows, 5.0) is None

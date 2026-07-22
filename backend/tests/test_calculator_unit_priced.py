"""Tests for unit-priced rows (b=NULL, no X range → a × count), п.м conversions,
per-book ПД/РД split and dropped-coefficient reporting."""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.conftest import make_db_returning, make_row
from app.services.calculator import (
    _match_row,
    _resolve_coeff_values,
    _stage_splits_for_book,
    _try_convert,
)


# ── Unit conversions: linear meters ───────────────────────────────────────────

def test_km_to_pm():
    assert _try_convert(0.3, "км", "п.м") == 300.0


def test_m_to_pm_one_to_one():
    assert _try_convert(300.0, "м", "п.м") == 300.0


def test_pm_to_km():
    assert _try_convert(300.0, "п.м", "км") == 0.3


# ── Unit-priced row matching (b=None, no range) ──────────────────────────────

def test_unit_priced_row_matches_with_count_x():
    """Row with b=None and no x range matches X given as item count."""
    rows = [make_row(x_min=None, x_max=None, a=70.0, b=None, x_unit="ячейка")]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=313, x_value=9.0, x_unit="шт.")
    assert match is not None
    assert match.x_effective == 9.0


# ── Per-book stage split ──────────────────────────────────────────────────────

def _book(pd=None, rd=None):
    b = MagicMock()
    b.pd_pct = pd
    b.rd_pct = rd
    return b


def test_stage_split_default_mu620():
    assert _stage_splits_for_book(_book(), "П+Р") == [("ПД", 0.4), ("РД", 0.6)]
    assert _stage_splits_for_book(_book(), "Р") == [("РД", 0.6)]


def test_stage_split_per_book_override():
    book = _book(pd=0.6, rd=0.4)
    assert _stage_splits_for_book(book, "П+Р") == [("ПД", 0.6), ("РД", 0.4)]
    assert _stage_splits_for_book(book, "Р") == [("РД", 0.4)]
    assert _stage_splits_for_book(book, "П") == [("ПД", 0.6)]


# ── Dropped coefficients are reported, not silently swallowed ─────────────────

def test_resolve_coeffs_reports_dropped():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    coeffs = [{"name": "overhaul", "value": 1.0}]
    resolved, dropped = _resolve_coeff_values(db, book_id=6, table_num=313, coefficients=coeffs)
    assert resolved == []
    assert dropped == ["overhaul"]


def test_resolve_coeffs_found_not_dropped():
    cond = MagicMock()
    cond.coeff_min = 1.2
    cond.coeff_max = 1.2
    cond.condition_short = "Реконструкция НС/ТП/РП"
    cond.table_num = 313
    cond.row_range = None
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [cond]
    coeffs = [{"name": "reconstruction", "value": 1.0}]
    resolved, dropped = _resolve_coeff_values(db, book_id=6, table_num=313, coefficients=coeffs)
    assert dropped == []
    assert len(resolved) == 1
    assert resolved[0]["value"] == 1.2


# ── Full word-form units must not fall into discrete 1:1 equivalence ─────────

def test_full_wordform_units_not_discrete():
    """«километр» → «кубических метров / секунду» must NOT convert 1:1."""
    assert _try_convert(1.5, "километр", "кубических метров / секунду") is None


def test_full_wordform_km_to_m():
    assert _try_convert(1.5, "километр", "метр") == 1500.0

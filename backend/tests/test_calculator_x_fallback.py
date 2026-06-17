"""Tests for X-fallback: when x_value is None, use minimum row."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests.conftest import make_db_returning, make_row
from app.services.calculator import _match_row


def test_x_none_returns_minimum_row():
    """When x_value is None, return the row with lowest x_min."""
    rows = [
        make_row(x_min=10.0, x_max=50.0, a=100.0, b=5.0, row_num="п.1"),
        make_row(x_min=50.0, x_max=200.0, a=300.0, b=3.0, row_num="п.2"),
    ]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=9, x_value=None, x_unit="шт")
    assert match is not None
    assert match.used_minimum is True
    assert match.row.row_num == "п.1"
    assert match.x_effective == 10.0


def test_x_none_row_without_x_min_gets_zero():
    """Row with x_min=None gets x_effective=0.0."""
    rows = [make_row(x_min=None, x_max=None, a=50.0, b=0.0)]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=9, x_value=None, x_unit="шт")
    assert match is not None
    assert match.used_minimum is True
    assert match.x_effective == 0.0


def test_x_none_empty_table_returns_none():
    """No rows → None even with x_value=None."""
    db = make_db_returning([])
    match = _match_row(db, book_version_id=1, table_num=9, x_value=None, x_unit="шт")
    assert match is None


def test_x_provided_not_used_minimum():
    """When x_value is given (not None), used_minimum must be False."""
    rows = [make_row(x_min=5.0, x_max=50.0, a=100.0, b=2.0)]
    db = make_db_returning(rows)
    match = _match_row(db, book_version_id=1, table_num=9, x_value=10.0, x_unit="шт")
    assert match is not None
    assert match.used_minimum is False

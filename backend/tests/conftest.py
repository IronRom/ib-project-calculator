"""Shared fixtures for calculator unit tests."""
from unittest.mock import MagicMock


def make_db_returning(rows: list) -> MagicMock:
    """Return a mock Session where any query chain ending in .all() returns rows."""
    db = MagicMock()
    # Handles both: .filter(a,b).all() and .filter(a,b).filter(c).all()
    q = db.query.return_value
    q.filter.return_value.filter.return_value.all.return_value = rows
    q.filter.return_value.all.return_value = rows
    return db


def make_row(
    x_min=None, x_max=None,
    a=10.0, b=2.0,
    row_num="п.1", x_unit="шт",
    description="Test row",
) -> MagicMock:
    """Minimal ReferenceRow mock."""
    row = MagicMock()
    row.x_min = x_min
    row.x_max = x_max
    row.a = a
    row.b = b
    row.row_num = row_num
    row.x_unit = x_unit
    row.description = description
    return row

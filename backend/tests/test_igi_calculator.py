"""Tests for igi_calculator.calculate_igi()."""
import sys
sys.path.insert(0, '/app')

import pytest
from unittest.mock import MagicMock, patch
from app.services.igi_calculator import calculate_igi


def _survey(items, *, complexity_category=2, k1=0.70, winter_pct=0.0, k2=1.0):
    return {
        "book_id": 9,
        "book_code": "НЗ-2025-МС281-ИГИ",
        "complexity_category": complexity_category,
        "k1": k1,
        "winter_pct": winter_pct,
        "k2": k2,
        "items": items,
    }


def _item(work_category, table_num, row_num, volume, b, x_unit="п.м", deleted=False):
    return {
        "work_category": work_category,
        "table_num": table_num,
        "row_num": row_num,
        "volume": volume,
        "b": b,
        "x_unit": x_unit,
        "deleted": deleted,
        "description": "Test item",
        "object_type_name": "Test",
    }


@patch("app.services.igi_calculator._get_survey_index")
@patch("app.services.igi_calculator._get_k1_for_table", return_value=None)
def test_field_item_applies_k1_and_winter(mock_k1, mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [_item("field", 14, "п.10", volume=100, b=2756)]
    survey = _survey(items, k1=0.70, winter_pct=0.29)

    positions, errors = calculate_igi([survey], db)

    assert not errors
    assert len(positions) == 1
    pos = positions[0]
    # cost = b * volume * k1 * (1 + winter_pct) * k2 * index
    # = 2756 * 100 * 0.70 * 1.29 * 1.0 * 1.0 = 248 857.2
    assert abs(pos["cost"] - 2756 * 100 * 0.70 * 1.29 * 1.0) < 1
    assert pos["work_category"] == "field"


@patch("app.services.igi_calculator._get_survey_index")
def test_lab_item_no_k1(mock_idx):
    mock_idx.return_value = (2.0, "II кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [_item("lab", 57, "п.1", volume=50, b=229, x_unit="одно определение")]
    survey = _survey(items, k1=0.70, winter_pct=0.29)

    positions, errors = calculate_igi([survey], db)

    assert not errors
    pos = positions[0]
    # lab: b * volume * index only (no k1, no winter)
    assert abs(pos["cost"] - 229 * 50 * 2.0) < 1


@patch("app.services.igi_calculator._get_survey_index")
def test_deleted_item_skipped(mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    items = [
        _item("field", 14, "п.10", volume=100, b=2756, deleted=True),
        _item("lab", 57, "п.1", volume=10, b=229, x_unit="одно определение"),
    ]
    survey = _survey(items)

    positions, errors = calculate_igi([survey], db)

    assert len(positions) == 1
    assert positions[0]["work_category"] == "lab"


@patch("app.services.igi_calculator._get_survey_index")
def test_report_auto_appended(mock_idx):
    mock_idx.return_value = (1.0, "I кв. 2024 г.", "Письмо МС")
    db = MagicMock()

    # One kameral item so that report cost lookup triggers
    items = [_item("kameral", 62, "п.2", volume=30, b=381, x_unit="один образец")]
    survey = _survey(items, complexity_category=2)

    # Mock the report lookup to return fixed cost
    with patch("app.services.igi_calculator._lookup_report_cost") as mock_report:
        mock_report.return_value = 200_000.0  # rubles at base level
        positions, errors = calculate_igi([survey], db)

    # positions = [kameral item, report auto-item]
    assert len(positions) == 2
    report_pos = positions[-1]
    assert report_pos["work_category"] == "report"
    assert report_pos["cost"] == 200_000.0 * 1.0  # × index

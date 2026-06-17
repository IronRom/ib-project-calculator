"""ИГИ (инженерно-геологические изыскания) calculation engine.

НЗ-2025-МС281-ИГИ — Приказ Минстроя РФ от 12.05.2025 № 281/пр.
Base prices: 01.01.2024 (руб).

Formula per work category:
  field:   b × volume × k1 × (1 + winter_pct) × k2 × index
  lab:     b × volume × index
  kameral: b × volume × index
  program: b × volume × index
  report:  auto-computed from total kameral cost via Table 65 lookup (see _lookup_report_cost)
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import PriceQuarterlyIndex, ReferenceRow

_CAT_ROW_RANGES = {1: (1, 7), 2: (8, 15), 3: (16, 24)}
_RE_ROW_NUM = re.compile(r'п\.(\d+)')


def _get_survey_index(db: Session) -> tuple[float, str, str]:
    """Return (index_value, period_label, source_ref) for survey work, base_year=2024.

    Survey index is global (not per-book).
    Looks up PriceQuarterlyIndex with work_type='survey', base_year=2024.
    Falls back to 1.0 if not configured.
    """
    rec = (
        db.query(PriceQuarterlyIndex)
        .filter(
            PriceQuarterlyIndex.base_year == 2024,
            PriceQuarterlyIndex.work_type == "survey",
        )
        .order_by(PriceQuarterlyIndex.year.desc(), PriceQuarterlyIndex.quarter.desc())
        .first()
    )
    if rec:
        roman = {1: "I", 2: "II", 3: "III", 4: "IV"}
        period = f"{roman.get(rec.quarter, str(rec.quarter))} квартал {rec.year} г."
        return float(rec.index_value), period, rec.source_ref
    return 1.0, "—", "Индекс изысканий к 2024 не задан"


def _lookup_report_cost(
    db: Session, book_version_id: int, kameral_total_rub: float, complexity_cat: int,
) -> float:
    """Lookup Таблица 65 НЗ-2025-МС281-ИГИ: cost of technical report.

    X = kameral_total_rub converted to тыс.руб.
    Returns cost in rubles at base year level (before index).

    Row structure in DB: x_min/x_max = тыс.руб thresholds, b = cost (руб).
    Step-lookup: returns b of the first row where x_max >= X (тыс.руб threshold).
    complexity_cat determines which row set (I → п.1-7, II → п.8-15, III → п.16-24).
    """
    kameral_thous = kameral_total_rub / 1000

    # Determine row_num range by complexity category
    # Cat I: п.1-п.7, Cat II: п.8-п.15, Cat III: п.16-п.24
    lo_p, hi_p = _CAT_ROW_RANGES.get(complexity_cat, (8, 15))

    rows: list[ReferenceRow] = (
        db.query(ReferenceRow)
        .filter(
            ReferenceRow.book_version_id == book_version_id,
            ReferenceRow.table_num == 65,
        )
        .all()
    )
    # Filter to complexity category rows by row_num parse
    cat_rows = []
    for r in rows:
        m = _RE_ROW_NUM.search(r.row_num or "")
        if m and lo_p <= int(m.group(1)) <= hi_p:
            cat_rows.append(r)

    if not cat_rows:
        return 0.0

    # Sort by x_max (thresholds are reference points)
    cat_rows.sort(key=lambda r: float(r.x_max) if r.x_max is not None else 1e12)

    # Find the right reference point: first row where x_max >= kameral_thous
    for r in cat_rows:
        if r.x_max is None or kameral_thous <= float(r.x_max):
            return float(r.b)

    # Above all thresholds: use last row
    return float(cat_rows[-1].b)


def calculate_igi(
    geological_surveys: list[dict[str, Any]],
    db: Session,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Calculate all geological survey blocks.

    Returns (positions, errors).
    Positions have same shape as PIR positions plus extra key 'work_category'.
    """
    positions: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, survey in enumerate(geological_surveys):
        book_version_id = survey.get("book_id")
        if not book_version_id:
            errors.append(f"ИГИ [survey #{i}]: не указан book_id справочника")
            continue

        book_code = survey.get("book_code", f"book#{book_version_id}")
        k1 = float(survey.get("k1", 0.70))
        winter_pct = float(survey.get("winter_pct", 0.0))
        k2 = float(survey.get("k2", 1.0))
        complexity_cat = int(survey.get("complexity_category", 2))

        index_val, idx_period, idx_just = _get_survey_index(db)

        kameral_total_base = 0.0  # running total for report lookup (at base level)

        items = [it for it in survey.get("items", []) if not it.get("deleted")]

        for item in items:
            work_cat = item.get("work_category", "field")
            b = float(item.get("b", 0))
            volume = float(item.get("volume", 0))
            x_unit = item.get("x_unit", "")
            table_num = item.get("table_num", 0)
            row_num = item.get("row_num", "")
            desc = item.get("description", "")
            otype_name = item.get("object_type_name", "")

            if work_cat == "field":
                cost = b * volume * k1 * (1 + winter_pct) * k2 * index_val
                coeff_note = (
                    f"К1={k1}"
                    + (f"; зима {int(winter_pct*100)}%" if winter_pct else "")
                    + (f"; К2={k2}" if k2 != 1.0 else "")
                )
            elif work_cat in ("lab", "kameral", "program"):
                cost = b * volume * index_val
                coeff_note = ""
                if work_cat == "kameral":
                    kameral_total_base += b * volume  # accumulate pre-index
            else:
                errors.append(f"ИГИ: неизвестная work_category '{work_cat}'")
                continue

            just = f"{book_code}, табл. {table_num}, {row_num}"
            if coeff_note:
                just += f" [{coeff_note}]"

            formula = f"{int(b)}×{volume}"
            if work_cat == "field":
                formula += f"×{k1}"
                if winter_pct:
                    formula += f"×{1 + winter_pct:.2f}"
                if k2 != 1.0:
                    formula += f"×{k2}"
            if index_val != 1.0:
                formula += f"×{index_val}"

            positions.append({
                "num": len(positions) + 1,
                "name": otype_name or desc,
                "row_description": desc,
                "unit": x_unit,
                "quantity": volume,
                "item_count": 1,
                "justification": just,
                "formula": formula,
                "cost": round(cost, 2),
                "cost_base": round(b * volume, 2),
                "book_code": book_code,
                "price_base_year": 2024,
                "price_index": index_val,
                "price_index_period": idx_period,
                "price_index_justification": idx_just,
                "table_num": table_num,
                "row_num": row_num,
                "used_minimum": False,
                "section_num": 0,
                "section_name": "ИГИ",
                "work_category": work_cat,
            })

        # Auto-append technical report if there are kameral items
        if kameral_total_base > 0:
            report_cost_base = _lookup_report_cost(db, book_version_id, kameral_total_base, complexity_cat)
            report_cost = report_cost_base * index_val
            if report_cost > 0:
                positions.append({
                    "num": len(positions) + 1,
                    "name": f"Технический отчёт ИГИ (кат.слож.{complexity_cat})",
                    "row_description": f"Табл.65 НЗ-2025-МС281-ИГИ, кат.слож.{complexity_cat}",
                    "unit": "один отчёт",
                    "quantity": 1,
                    "item_count": 1,
                    "justification": (
                        f"{book_code}, табл. 65, кат.слож.{complexity_cat}"
                        f" (камеральные: {round(kameral_total_base/1000, 1)} тыс.руб)"
                    ),
                    "formula": f"{int(report_cost_base)}×{index_val}",
                    "cost": round(report_cost, 2),
                    "cost_base": round(report_cost_base, 2),
                    "book_code": book_code,
                    "price_base_year": 2024,
                    "price_index": index_val,
                    "price_index_period": idx_period,
                    "price_index_justification": idx_just,
                    "table_num": 65,
                    "row_num": "",
                    "used_minimum": False,
                    "section_num": 0,
                    "section_name": "ИГИ",
                    "work_category": "report",
                })

    return positions, errors

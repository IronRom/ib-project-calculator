"""ИГИ (инженерно-геологические изыскания) calculation engine.

НЗ-2025-МС281-ИГИ — Приказ Минстроя РФ от 12.05.2025 № 281/пр.
Base prices: 01.01.2024 (руб).

Formula per work category:
  field:   (a + b × volume) × k1 × (1 + winter_pct) × k2 × index
  lab:     (a + b × volume) × index
  kameral: (a + b × volume) × index
  program: (a + b × volume) × index
  report:  auto-computed from total kameral cost via Table 65 lookup (see _lookup_report_cost)

K1 coefficient:
  Looked up per table_num from book_conditions (coeff_key="k1").
  Falls back to survey.k1 (default 0.70) when no DB entry for that table.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import BookCondition, PriceQuarterlyIndex, ReferenceBook, ReferenceRow

_CAT_ROW_RANGES = {1: (1, 7), 2: (8, 15), 3: (16, 24)}
_RE_ROW_NUM = re.compile(r'п\.(\d+)')


def _get_survey_index(db: Session, base_year: int = 2024) -> tuple[float, str, str]:
    """Return (index_value, period_label, source_ref) for survey work.

    Survey index is looked up by base_year from the book's price_base_year.
    Looks up PriceQuarterlyIndex with work_type='survey' and the given base_year.
    Falls back to 1.0 if not configured.
    """
    rec = (
        db.query(PriceQuarterlyIndex)
        .filter(
            PriceQuarterlyIndex.base_year == base_year,
            PriceQuarterlyIndex.work_type == "survey",
        )
        .order_by(PriceQuarterlyIndex.year.desc(), PriceQuarterlyIndex.quarter.desc())
        .first()
    )
    if rec:
        roman = {1: "I", 2: "II", 3: "III", 4: "IV"}
        period = f"{roman.get(rec.quarter, str(rec.quarter))} квартал {rec.year} г."
        return float(rec.index_value), period, rec.source_ref
    return 1.0, "—", f"Индекс изысканий к {base_year} не задан"


def _get_k1_for_table(
    db: Session, book_version_id: int, table_num: int
) -> Optional[float]:
    """Return per-table K1 from book_conditions, or None if not defined.

    Looks up BookCondition where coeff_key="k1" and table_num matches.
    Returns coeff_min as float when found; None means caller should use survey.k1 fallback.
    """
    rec = (
        db.query(BookCondition)
        .filter(
            BookCondition.book_version_id == book_version_id,
            BookCondition.table_num == table_num,
            BookCondition.coeff_key == "k1",
        )
        .first()
    )
    if rec and rec.coeff_min is not None:
        return float(rec.coeff_min)
    return None


def _lookup_report_cost(
    db: Session, book_version_id: int, kameral_total_rub: float, complexity_cat: int,
) -> float:
    """Lookup Таблица 65 НЗ-2025-МС281-ИГИ: cost of technical report.

    X = kameral_total_rub converted to тыс.руб.
    Returns cost in rubles at base year level (before index).

    Linear interpolation per НЗ п.121 примечание 1.
    Reference points stored as x_max (regular rows) or x_min (last "свыше" row).
    complexity_cat determines which row set (I → п.1-7, II → п.8-15, III → п.16-24).
    """
    kameral_thous = kameral_total_rub / 1000

    lo_p, hi_p = _CAT_ROW_RANGES.get(complexity_cat, (8, 15))

    rows: list[ReferenceRow] = (
        db.query(ReferenceRow)
        .filter(
            ReferenceRow.book_version_id == book_version_id,
            ReferenceRow.table_num == 65,
        )
        .all()
    )
    cat_rows = []
    for r in rows:
        m = _RE_ROW_NUM.search(r.row_num or "")
        if m and lo_p <= int(m.group(1)) <= hi_p:
            cat_rows.append(r)

    if not cat_rows:
        return 0.0

    # Build reference points: (X_тыс.руб, b_руб)
    # x_max = reference point for normal rows; x_min = reference for last "свыше" row
    ref_points: list[tuple[float, float]] = []
    for r in cat_rows:
        if r.x_max is not None:
            ref_points.append((float(r.x_max), float(r.b)))
        elif r.x_min is not None:
            ref_points.append((float(r.x_min), float(r.b)))

    if not ref_points:
        return 0.0

    ref_points.sort(key=lambda p: p[0])

    if kameral_thous <= ref_points[0][0]:
        return ref_points[0][1]
    if kameral_thous >= ref_points[-1][0]:
        return ref_points[-1][1]

    # Linear interpolation between adjacent reference points
    for i in range(len(ref_points) - 1):
        x0, b0 = ref_points[i]
        x1, b1 = ref_points[i + 1]
        if x0 <= kameral_thous <= x1:
            t = (kameral_thous - x0) / (x1 - x0)
            return b0 + t * (b1 - b0)

    return ref_points[-1][1]


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
        unfavorable_months = float(survey.get("unfavorable_months", 0.0))
        k2 = float(survey.get("k2", 1.0))
        complexity_cat = int(survey.get("complexity_category", 2))

        # НЗ п.21: ДЗнп = С_Пнп × ПДЗнп, С_Пнп = С_Пнз × (T_unfav/12)
        # winter_pct = ПДЗнп (Table 3 value, e.g. 0.29)
        # unfavorable_months = T_unfav from Приложение 1
        if unfavorable_months > 0:
            winter_factor = (unfavorable_months / 12.0) * winter_pct
        else:
            winter_factor = winter_pct  # legacy: treat as combined factor

        # Resolve price_base_year from the book record (fallback to 2024)
        book_rec = db.query(ReferenceBook).filter(ReferenceBook.id == book_version_id).first()
        price_base_year = (
            book_rec.price_base_year
            if book_rec and hasattr(book_rec, "price_base_year")
            else 2024
        )

        index_val, idx_period, idx_just = _get_survey_index(db, price_base_year)

        # Table 65 X = "общая стоимость камеральных работ из глав IV-VIII НЗ"
        # = lab (Гл.VII-VIII) + kameral processing (Гл.IV-VIII), excluding program (Гл.X)
        nonfield_total_base = 0.0  # accumulates lab + kameral at base level for Table 65

        items = [it for it in survey.get("items", []) if not it.get("deleted")]

        for item in items:
            work_cat = item.get("work_category", "field")
            a = float(item.get("a", 0))
            b = float(item.get("b", 0))
            volume = float(item.get("volume", 0))
            x_unit = item.get("x_unit", "")
            table_num = item.get("table_num", 0)
            row_num = item.get("row_num", "")
            desc = item.get("description", "")
            otype_name = item.get("object_type_name", "")

            # Base cost: a + b × volume (a=0 when not applicable)
            base = a + b * volume

            if work_cat == "field":
                # Per-table K1 from book_conditions; fall back to survey.k1
                table_k1 = _get_k1_for_table(db, book_version_id, table_num)
                effective_k1 = table_k1 if table_k1 is not None else k1

                cost = base * effective_k1 * (1 + winter_factor) * k2 * index_val
                coeff_note = (
                    f"К1={effective_k1}"
                    + (f"; зима {round(winter_factor * 100, 1)}%" if winter_factor else "")
                    + (f"; К2={k2}" if k2 != 1.0 else "")
                )
            elif work_cat in ("lab", "kameral", "program"):
                effective_k1 = k1  # not used, but keep variable consistent
                cost = base * index_val
                coeff_note = ""
                if work_cat in ("lab", "kameral"):
                    # Accumulate for Table 65 (technical report X parameter)
                    nonfield_total_base += base
            else:
                errors.append(f"ИГИ: неизвестная work_category '{work_cat}'")
                continue

            just = f"{book_code}, табл. {table_num}, {row_num}"
            if coeff_note:
                just += f" [{coeff_note}]"

            if a:
                formula = f"({int(a)}+{int(b)}×{volume})"
            else:
                formula = f"{int(b)}×{volume}"
            if work_cat == "field":
                formula += f"×{effective_k1}"
                if winter_factor:
                    formula += f"×{1 + winter_factor:.3f}"
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
                "cost_base": round(base, 2),
                "book_code": book_code,
                "price_base_year": price_base_year,
                "price_index": index_val,
                "price_index_period": idx_period,
                "price_index_justification": idx_just,
                "table_num": table_num,
                "row_num": row_num,
                "used_minimum": False,
                "section_num": 0,
                "section_name": "ИГИ",
                "work_category": work_cat,
                "_stage_embedded": True,  # ИГИ costs are not split by П/Р stage
            })

        # Auto-append technical report if there are lab/kameral items
        # НЗ п.121: X = общая стоимость камеральных работ из глав IV-VIII (lab + kameral, excl. program)
        if nonfield_total_base > 0:
            report_cost_base = _lookup_report_cost(db, book_version_id, nonfield_total_base, complexity_cat)
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
                        f" (лаб+камерал: {round(nonfield_total_base/1000, 1)} тыс.руб)"
                    ),
                    "formula": f"{int(report_cost_base)}×{index_val}",
                    "cost": round(report_cost, 2),
                    "cost_base": round(report_cost_base, 2),
                    "book_code": book_code,
                    "price_base_year": price_base_year,
                    "price_index": index_val,
                    "price_index_period": idx_period,
                    "price_index_justification": idx_just,
                    "table_num": 65,
                    "row_num": "",
                    "used_minimum": False,
                    "section_num": 0,
                    "section_name": "ИГИ",
                    "work_category": "report",
                    "_stage_embedded": True,  # ИГИ costs are not split by П/Р stage
                })

    return positions, errors

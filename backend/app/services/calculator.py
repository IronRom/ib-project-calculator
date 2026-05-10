"""Deterministic calculation engine — 2ПС ИР format."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import PriceIndex, ReferenceBook, ReferenceRow

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
STAGE_FACTORS = {"П": 0.6, "Р": 0.4, "П+Р": 1.0}


def _normalize_unit(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    u = re.sub(r"^1\s+", "", u)          # "1 тыс. м³/ч" → "тыс. м³/ч"
    u = re.sub(r"\s+", " ", u).lower()
    # Normalise common abbreviation variants
    u = u.replace("куб.", "м³").replace("m3", "м³").replace("м3", "м³")
    u = u.replace("/час", "/ч").replace("/час.", "/ч")
    u = u.replace("/сутки", "/сут").replace("/суток", "/сут")
    u = re.sub(r"пог\.?\s*", "", u)   # "пог. м" → "м"
    return u.strip()


# (from_unit_normalized, to_unit_normalized) → conversion function
UNIT_CONVERSIONS: dict[tuple[str, str], Callable[[float], float]] = {
    # water flow: volume per time
    ("тыс. м³/сут", "тыс. м³/ч"): lambda x: x / 24,
    ("тыс. м³/ч", "тыс. м³/сут"): lambda x: x * 24,
    ("м³/ч", "тыс. м³/ч"):        lambda x: x / 1000,
    ("тыс. м³/ч", "м³/ч"):        lambda x: x * 1000,
    ("м³/сут", "тыс. м³/сут"):    lambda x: x / 1000,
    ("тыс. м³/сут", "м³/сут"):    lambda x: x * 1000,
    ("м³/сут", "м³/ч"):           lambda x: x / 24,
    ("м³/ч", "м³/сут"):           lambda x: x * 24,
    ("м³/сут", "тыс. м³/ч"):      lambda x: x / 24_000,
    ("тыс. м³/ч", "м³/сут"):      lambda x: x * 24_000,
    # sludge
    ("т/сут", "т/г."):            lambda x: x * 365,
    ("т/г.", "т/сут"):            lambda x: x / 365,
    ("т/сут", "тыс. т/г."):       lambda x: x * 365 / 1000,
    ("тыс. т/г.", "т/сут"):        lambda x: x * 1000 / 365,
    # cross: м³/ч ↔ тыс. м³/сут
    ("м³/ч", "тыс. м³/сут"):     lambda x: x * 24 / 1000,
    ("тыс. м³/сут", "м³/ч"):     lambda x: x * 1000 / 24,
    # л/с → volume flow
    ("л/с", "м³/ч"):             lambda x: x * 3.6,
    ("л/с", "тыс. м³/ч"):        lambda x: x * 0.0036,
    ("л/с", "м³/сут"):           lambda x: x * 86.4,
    ("л/с", "тыс. м³/сут"):      lambda x: x * 0.0864,
    ("м³/ч", "л/с"):             lambda x: x / 3.6,
    ("тыс. м³/ч", "л/с"):        lambda x: x / 0.0036,
    # distance
    ("км", "м"):                  lambda x: x * 1000,
    ("м", "км"):                  lambda x: x / 1000,
}


@dataclass
class RowMatch:
    row: ReferenceRow
    x_effective: float          # x converted to row's unit
    extrapolated: bool
    x_boundary: Optional[float] # boundary value used for extrapolation
    note: str                   # human-readable conversion / extrapolation note


def _try_convert(x_value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Return converted value, or None if no conversion path exists."""
    fn = UNIT_CONVERSIONS.get((from_unit, to_unit))
    return fn(x_value) if fn is not None else None


def _match_row(
    db: Session,
    book_version_id: int,
    table_num: int,
    x_value: float,
    x_unit: str,
    object_type_id: Optional[int] = None,
) -> Optional[RowMatch]:
    q = db.query(ReferenceRow).filter(
        ReferenceRow.book_version_id == book_version_id,
        ReferenceRow.table_num == table_num,
    )
    if object_type_id is not None:
        q = q.filter(ReferenceRow.object_type_id == object_type_id)
    all_rows: list[ReferenceRow] = q.all()
    if not all_rows:
        return None

    x_unit_norm = _normalize_unit(x_unit)

    # Collect distinct units present in this table's rows
    row_units: list[str] = list({_normalize_unit(r.x_unit or "") for r in all_rows})

    # Build candidate (x_effective, note, matching_rows) tuples
    candidates: list[tuple[float, str, list[ReferenceRow]]] = []

    for row_unit in row_units:
        if x_unit_norm == row_unit or not x_unit_norm or not row_unit:
            x_eff = x_value
            note = ""
        else:
            x_eff = _try_convert(x_value, x_unit_norm, row_unit)
            if x_eff is None:
                continue
            note = f"{x_unit} → {row_unit}"

        rows_for_unit = [r for r in all_rows if _normalize_unit(r.x_unit or "") == row_unit]
        candidates.append((x_eff, note, rows_for_unit))

    if not candidates:
        return None

    # Pass 1: exact range match
    for x_eff, note, rows in candidates:
        for r in rows:
            x_min = float(r.x_min) if r.x_min is not None else None
            x_max = float(r.x_max) if r.x_max is not None else None
            if (x_min is None or x_eff >= x_min) and (x_max is None or x_eff <= x_max):
                return RowMatch(r, x_eff, False, None, note)

    # Pass 2: extrapolation — boundary row (МУ №620 Прил.1)
    for x_eff, note, rows in candidates:
        maxes = [(float(r.x_max), r) for r in rows if r.x_max is not None]
        mins  = [(float(r.x_min), r) for r in rows if r.x_min is not None]

        if maxes and x_eff > max(v for v, _ in maxes):
            bval, brow = max(maxes, key=lambda t: t[0])
            extrap_note = f"экстраполяция (X={x_eff:.4g} > {bval:.4g})"
            return RowMatch(brow, x_eff, True, bval, f"{note}; {extrap_note}" if note else extrap_note)

        if mins and x_eff < min(v for v, _ in mins):
            bval, brow = min(mins, key=lambda t: t[0])
            extrap_note = f"экстраполяция (X={x_eff:.4g} < {bval:.4g})"
            return RowMatch(brow, x_eff, True, bval, f"{note}; {extrap_note}" if note else extrap_note)

    return None


_PRICING_COEFFS = {"reconstruction", "overhaul"}   # always multiply (МУ №620 п.3.14)
_COMPLEX_COEFFS = {"asu", "seismic", "deepening", "fishery"}  # sum fractional parts


def _apply_coefficients(coefficients: list[dict]) -> tuple[float, str]:
    """МУ №620 п.3.14: compute combined factor and formula label."""
    pricing = 1.0
    complex_parts: list[tuple[str, float]] = []

    for c in coefficients:
        name = (c.get("name") or "").strip()
        value = float(c.get("value") or 1.0)
        if name in _PRICING_COEFFS and value != 1.0:
            pricing *= value
        elif name in _COMPLEX_COEFFS and value > 1.0:
            complex_parts.append((name, value - 1.0))

    complex_factor = 1.0 + sum(v for _, v in complex_parts)
    combined = pricing * complex_factor

    parts: list[str] = []
    if pricing != 1.0:
        parts.append(f"×{pricing:.3g}")
    if complex_parts:
        detail = "+".join(f"{v:.3g}({n})" for n, v in complex_parts)
        parts.append(f"×{complex_factor:.3g}[1+{detail}]")

    return combined, " ".join(parts)


_CODE_PREFIX = re.compile(r'^(сбцп|сбц|мрр)\s+', re.IGNORECASE)


def _normalize_code(code: str) -> str:
    return _CODE_PREFIX.sub('', code.strip()).lower()


def _find_active_book(db: Session, sbts_code: str) -> Optional[ReferenceBook]:
    """Find active book by code. Handles prefix variants on both sides (СБЦП/СБЦ/МРР)."""
    if not sbts_code:
        return None
    query_norm = _normalize_code(sbts_code)
    for book in db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all():
        if book.code.strip().lower() == sbts_code.strip().lower():
            return book  # exact
        if _normalize_code(book.code) == query_norm:
            return book  # prefix-normalized
    return None


def _fmt_number(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}".replace(",", " ")
    return f"{n:,.2f}".replace(",", " ")


def calculate(entities_dict: dict[str, Any], db: Session) -> dict[str, Any]:
    entities = entities_dict.get("entities", [])

    positions = []
    errors = []

    for entity in entities:
        sbts_code      = entity.get("sbts_code", "")
        table_num      = entity.get("sbts_table")
        object_type_id = entity.get("sbts_object_type_id")
        x_value        = float(entity.get("x_value") or 0.0)
        x_unit         = entity.get("x_unit", "")
        object_name    = entity.get("object_name", "")
        qty            = max(1, int(entity.get("quantity") or 1))

        if not table_num:
            errors.append(f"{object_name}: не определена таблица СБЦП")
            continue

        book = _find_active_book(db, sbts_code)
        if not book:
            errors.append(f"{object_name}: активный справочник «{sbts_code}» не найден")
            continue

        match = _match_row(db, book.id, table_num, x_value, x_unit, object_type_id)
        if not match:
            errors.append(
                f"{object_name}: строка для X={x_value} {x_unit} в таблице №{table_num} не найдена"
            )
            continue

        row = match.row
        a = float(row.a) if row.a is not None else 0.0
        b = float(row.b) if row.b is not None else 0.0

        # МУ №620 Прил.1 extrapolation
        if match.extrapolated and match.x_boundary is not None:
            x_calc = 0.4 * match.x_boundary + 0.6 * match.x_effective
        else:
            x_calc = match.x_effective

        # МУ №620 п.3.14: apply coefficients
        coefficients = entity.get("coefficients", [])
        coeff_factor, coeff_label = _apply_coefficients(coefficients)

        # Reference rows values are in тыс. руб. (base year 2001)
        unit_cost = (a + b * x_calc) * 1000
        cost = unit_cost * qty * coeff_factor

        row_unit = row.x_unit or x_unit or ""
        row_num  = row.row_num or ""

        justification = f"{book.code}, Таблица №{table_num}"
        if row_num:
            justification += f" {row_num}"
        if row.x_min is not None and row.x_max is not None:
            justification += f" (свыше {_fmt_number(float(row.x_min))} до {_fmt_number(float(row.x_max))})"
        elif row.x_max is not None:
            justification += f" (до {_fmt_number(float(row.x_max))})"
        elif row.x_min is not None:
            justification += f" (свыше {_fmt_number(float(row.x_min))})"
        if match.note:
            justification += f" [{match.note}]"

        a_rub, b_rub = a * 1000, b * 1000
        if b:
            formula = f"({_fmt_number(a_rub)} + {_fmt_number(b_rub)} × {match.x_effective})"
        else:
            formula = _fmt_number(a_rub)
        if match.extrapolated and match.x_boundary is not None:
            formula += f" × МУ620 (X_эфф={x_calc:.4g})"
        if coeff_label:
            formula += f" {coeff_label}"
            justification += f" | МУ №620 п.3.14: {coeff_label}"
        if qty > 1:
            formula += f" × {qty} шт."

        positions.append({
            "num":           len(positions) + 1,
            "name":          object_name,
            "row_description": row.description or "",
            "unit":          row_unit,
            "quantity":      match.x_effective,
            "item_count":    qty,
            "justification": justification,
            "formula":       formula,
            "cost":          round(cost, 2),
            "book_code":     book.code,
            "table_num":     table_num,
            "row_num":       row_num,
        })

    base_cost = sum(p["cost"] for p in positions)

    price_index = (
        db.query(PriceIndex)
        .filter(PriceIndex.index_type == "project")
        .order_by(PriceIndex.year.desc(), PriceIndex.quarter.desc())
        .first()
    )
    vat_rec = (
        db.query(PriceIndex)
        .filter(PriceIndex.index_type == "vat")
        .order_by(PriceIndex.year.desc())
        .first()
    )

    idx_value = float(price_index.index_value) if price_index else 1.0
    vat_rate  = float(vat_rec.index_value) if vat_rec else 22.0

    if price_index:
        roman = ROMAN.get(price_index.quarter, str(price_index.quarter))
        period           = f"{roman} квартал {price_index.year} г."
        idx_justification = price_index.source_ref
    else:
        period            = "—"
        idx_justification = "Индекс не задан"

    stage        = entities_dict.get("stage", "П+Р")
    stage_factor = STAGE_FACTORS.get(stage, 1.0)

    current_cost   = round(base_cost * idx_value, 2)
    cost_with_stage = round(current_cost * stage_factor, 2)
    vat_amount     = round(cost_with_stage * vat_rate / 100, 2)
    total_with_vat = round(cost_with_stage + vat_amount, 2)

    return {
        "positions":                positions,
        "base_cost":                round(base_cost, 2),
        "price_index":              idx_value,
        "price_index_period":       period,
        "price_index_justification": idx_justification,
        "stage":                    stage,
        "stage_factor":             stage_factor,
        "current_cost":             current_cost,
        "cost_with_stage":          cost_with_stage,
        "vat_rate":                 vat_rate,
        "vat_amount":               vat_amount,
        "total_with_vat":           total_with_vat,
        "errors":                   errors,
        "_price_index_id":          price_index.id if price_index else None,
    }

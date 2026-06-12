"""Deterministic calculation engine — 2ПС ИР format."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import PriceIndex, ReferenceBook, ReferenceRow

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
STAGE_FACTORS = {"П": 0.4, "Р": 0.6, "П+Р": 1.0}


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
    # Fallback: type_id gave no rows → retry without type filter
    if not all_rows and object_type_id is not None:
        all_rows = (
            db.query(ReferenceRow)
            .filter(
                ReferenceRow.book_version_id == book_version_id,
                ReferenceRow.table_num == table_num,
            )
            .all()
        )
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


_PRICING_COEFFS = {"reconstruction", "overhaul", "deepening"}  # always multiply; shown separately per step
_COMPLEX_COEFFS = {"asu", "seismic", "fishery"}  # sum fractional parts: 1+Σ(Ki-1)

_RE_ROW_N   = re.compile(r'п\.?\s*(\d+)', re.IGNORECASE)
_RE_RNG_SEG = re.compile(r'(\d+)(?:-(\d+))?')


def _row_in_range(row_num_str: Optional[str], row_range: Optional[str]) -> bool:
    """Return True if row_num falls within row_range (or no restriction exists).

    row_num_str: e.g. "п.10"
    row_range:   e.g. "пп.25-28" | "пп.1-4,13-15" | None
    """
    if not row_range:
        return True
    if not row_num_str:
        return True
    m = _RE_ROW_N.search(row_num_str)
    if not m:
        return True  # can't parse → don't filter
    n = int(m.group(1))
    # Strip prefix and iterate comma-separated segments
    segments = row_range.replace('пп.', '').replace('п.', '').strip()
    for seg in segments.split(','):
        seg = seg.strip()
        rm = _RE_RNG_SEG.match(seg)
        if not rm:
            continue
        lo = int(rm.group(1))
        hi = int(rm.group(2)) if rm.group(2) else lo
        if lo <= n <= hi:
            return True
    return False


def _resolve_coeff_values(
    db: Session, book_id: int, table_num: int, coefficients: list[dict],
    matched_row_num: Optional[str] = None,
) -> list[dict]:
    """Replace AI flag-values (1.0) with actual coeff_max from book_conditions.

    Lookup order: table-specific conditions first (filtered by row_range against
    the matched row), then table=None (global). Uses coeff_max (upper bound).

    matched_row_num: row_num of the DB row that was matched (e.g. "п.10").
    When provided, conditions whose row_range does NOT include this row are skipped.
    """
    from app.models import BookCondition

    resolved = []
    for c in coefficients:
        key = (c.get("name") or "").strip()
        if not key:
            continue

        # table-specific — get ALL candidates, pick first that covers matched row
        table_conds = (
            db.query(BookCondition)
            .filter(
                BookCondition.book_version_id == book_id,
                BookCondition.coeff_key == key,
                BookCondition.table_num == table_num,
            )
            .all()
        )
        cond = next(
            (tc for tc in table_conds if _row_in_range(matched_row_num, tc.row_range)),
            None,
        )

        # global fallback (row_range usually None → applies everywhere)
        if cond is None:
            global_conds = (
                db.query(BookCondition)
                .filter(
                    BookCondition.book_version_id == book_id,
                    BookCondition.coeff_key == key,
                    BookCondition.table_num.is_(None),
                )
                .all()
            )
            cond = next(
                (gc for gc in global_conds if _row_in_range(matched_row_num, gc.row_range)),
                None,
            )

        if cond is None or (cond.coeff_max is None and cond.coeff_min is None):
            continue  # no applicable condition → skip

        ai_value = float(c.get("value", 1.0))
        is_flag = abs(ai_value - 1.0) < 0.001

        if is_flag:
            # Standard path: AI flagged with 1.0, resolve from DB
            value = float(cond.coeff_max if cond.coeff_max is not None else cond.coeff_min)
        else:
            # AI pre-computed compound value (e.g. deepening 1.15^4); preserve it
            value = ai_value

        resolved.append({
            **c,
            "value": value,
            "condition_short": cond.condition_short or "",
            "_table_num": cond.table_num,
        })
    return resolved


def _apply_coefficients(coefficients: list[dict]) -> tuple[float, list[tuple[str, float, str]]]:
    """МУ №620 п.3.14: compute combined factor + list of (name, value, condition_short).

    Returns the factor and the resolved coefficient list for justification building.
    """
    pricing = 1.0
    complex_parts: list[tuple[str, float]] = []
    applied: list[tuple[str, float, str]] = []  # (name, resolved_value, condition_short)

    for c in coefficients:
        name = (c.get("name") or "").strip()
        value = float(c.get("value") or 1.0)
        short = c.get("condition_short", "")
        if name in _PRICING_COEFFS and value != 1.0:
            pricing *= value
            applied.append((name, value, short))
        elif name in _COMPLEX_COEFFS and value > 1.0:
            complex_parts.append((name, value - 1.0))
            applied.append((name, value, short))

    complex_factor = 1.0 + sum(v for _, v in complex_parts)
    combined = pricing * complex_factor
    return combined, applied


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
    """Space-separated thousands, period decimal — for justification text."""
    if n == int(n):
        return f"{int(n):,}".replace(",", " ")
    return f"{n:,.2f}".replace(",", " ")


def _fmt_ru(n: float) -> str:
    """Compact Russian format for formula: no spaces, comma decimal."""
    if n == int(n):
        return str(int(n))
    # Up to 5 significant digits, comma decimal, no trailing zeros
    s = f"{n:.5g}".replace(".", ",")
    return s


def _get_quarterly_index(db: Session, base_year: int):
    """Latest project index for a given price base year.

    Falls back to legacy PriceIndex(index_type='project') for base_year=2001
    when no PriceQuarterlyIndex record exists yet.
    """
    from app.models import PriceQuarterlyIndex
    rec = (
        db.query(PriceQuarterlyIndex)
        .filter(
            PriceQuarterlyIndex.base_year == base_year,
            PriceQuarterlyIndex.work_type == "project",
        )
        .order_by(PriceQuarterlyIndex.year.desc(), PriceQuarterlyIndex.quarter.desc())
        .first()
    )
    if rec:
        return rec
    if base_year == 2001:
        # Legacy fallback: old price_indices table
        old = (
            db.query(PriceIndex)
            .filter(PriceIndex.index_type == "project")
            .order_by(PriceIndex.year.desc(), PriceIndex.quarter.desc())
            .first()
        )
        return old
    return None


def calculate(entities_dict: dict[str, Any], db: Session) -> dict[str, Any]:
    entities = [e for e in entities_dict.get("entities", []) if not e.get("deleted", False)]

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

        # МУ №620 п.3.14: apply coefficients (resolve AI flag→actual DB value first)
        coefficients = _resolve_coeff_values(
            db, book.id, table_num, entity.get("coefficients", []),
            matched_row_num=row.row_num,
        )
        coeff_factor, applied_coeffs = _apply_coefficients(coefficients)

        # Per-book price index (base_year → current quarter)
        base_year = getattr(book, 'price_base_year', 2001) or 2001
        idx_rec = _get_quarterly_index(db, base_year)
        idx_value = float(idx_rec.index_value) if idx_rec else 1.0
        if idx_rec and hasattr(idx_rec, 'quarter'):
            roman_q = ROMAN.get(idx_rec.quarter, str(idx_rec.quarter))
            idx_period = f"{roman_q} квартал {idx_rec.year} г."
            idx_justification = idx_rec.source_ref
        else:
            idx_period = "—"
            idx_justification = f"Индекс к {base_year} не задан"

        # Reference rows in тыс. руб. at book's base year level
        unit_cost_base = (a + b * x_calc) * 1000   # base rubles (pre-index)
        cost_base = unit_cost_base * qty * coeff_factor
        cost = cost_base * idx_value                # current rubles

        row_unit = row.x_unit or x_unit or ""
        row_num  = row.row_num or ""

        # ── Justification (обоснование) ───────────────────────────────────────
        justification = f"{book.code}, табл. {table_num}"
        if row_num:
            justification += f", {row_num}"
        if row.x_min is not None and row.x_max is not None:
            justification += f" (свыше {_fmt_number(float(row.x_min))} до {_fmt_number(float(row.x_max))})"
        elif row.x_max is not None:
            justification += f" (до {_fmt_number(float(row.x_max))})"
        elif row.x_min is not None:
            justification += f" (свыше {_fmt_number(float(row.x_min))})"
        if match.note:
            justification += f" [{match.note}]"
        if match.extrapolated and match.x_boundary is not None:
            justification += f"; МУ №620 Прил.1 (X={_fmt_ru(match.x_effective)} {row_unit}, X_расч={_fmt_ru(x_calc)})"
        for _name, _val, _short in applied_coeffs:
            para = f"п. 2.{table_num}" if table_num else "п. 1"
            justification += f"; {para} ({_short} К={_fmt_ru(_val)})"

        # ── Formula (расчёт стоимости) ────────────────────────────────────────
        a_rub, b_rub = a * 1000, b * 1000
        x_formula = x_calc if (match.extrapolated and match.x_boundary is not None) else match.x_effective
        if b:
            formula = f"({_fmt_ru(a_rub)}+{_fmt_ru(b_rub)}*{_fmt_ru(x_formula)})"
        else:
            formula = _fmt_ru(a_rub)
        for _n, _v, _ in applied_coeffs:
            if _n in _PRICING_COEFFS and _v != 1.0:
                formula += f"×{_fmt_ru(_v)}"
        _complex_vals = [_v for _n, _v, _ in applied_coeffs if _n in _COMPLEX_COEFFS and _v > 1.0]
        if _complex_vals:
            _cf = 1.0 + sum(_v - 1.0 for _v in _complex_vals)
            formula += f"×{_fmt_ru(_cf)}"
        if idx_value != 1.0:
            formula += f"*{_fmt_ru(idx_value)}"
        if qty > 1:
            formula += f"*{qty}"

        positions.append({
            "num":                 len(positions) + 1,
            "name":                object_name,
            "row_description":     row.description or "",
            "unit":                row_unit,
            "quantity":            match.x_effective,
            "item_count":          qty,
            "justification":       justification,
            "formula":             formula,
            "cost":                round(cost, 2),
            "cost_base":           round(cost_base, 2),
            "book_code":           book.code,
            "price_base_year":     base_year,
            "price_index":         idx_value,
            "price_index_period":  idx_period,
            "price_index_justification": idx_justification,
            "table_num":           table_num,
            "row_num":             row_num,
        })

    # ── Aggregate ─────────────────────────────────────────────────────────────
    base_cost    = sum(p["cost_base"] for p in positions)
    current_cost = sum(p["cost"] for p in positions)

    # Build index summary keyed by base_year (for 2ПС and frontend display)
    index_summary: dict[int, dict] = {}
    for p in positions:
        by = p["price_base_year"]
        if by not in index_summary:
            index_summary[by] = {
                "base_year":    by,
                "index_value":  p["price_index"],
                "period":       p["price_index_period"],
                "justification": p["price_index_justification"],
            }

    # Backward-compat single-index fields (filled when all positions share one index)
    if len(index_summary) == 1:
        si = next(iter(index_summary.values()))
        price_index       = si["index_value"]
        price_index_period = si["period"]
        price_index_just  = si["justification"]
    else:
        price_index       = None
        price_index_period = "разные справочники"
        price_index_just  = "; ".join(
            f"к {s['base_year']}: {s['index_value']}" for s in index_summary.values()
        )

    vat_rec = (
        db.query(PriceIndex)
        .filter(PriceIndex.index_type == "vat")
        .order_by(PriceIndex.year.desc())
        .first()
    )
    vat_rate = float(vat_rec.index_value) if vat_rec else 22.0

    stage        = entities_dict.get("stage", "П+Р")
    stage_factor = STAGE_FACTORS.get(stage, 1.0)

    cost_with_stage = round(current_cost * stage_factor, 2)
    vat_amount      = round(cost_with_stage * vat_rate / 100, 2)
    total_with_vat  = round(cost_with_stage + vat_amount, 2)

    return {
        "positions":                 positions,
        "base_cost":                 round(base_cost, 2),
        "price_index":               price_index,
        "price_index_period":        price_index_period,
        "price_index_justification": price_index_just,
        "index_summary":             list(index_summary.values()),
        "stage":                     stage,
        "stage_factor":              stage_factor,
        "current_cost":              round(current_cost, 2),
        "cost_with_stage":           cost_with_stage,
        "vat_rate":                  vat_rate,
        "vat_amount":                vat_amount,
        "total_with_vat":            total_with_vat,
        "errors":                    errors,
    }

"""Deterministic calculation engine — 2ПС ИР format."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import AsutpFactorOption, AsutpModule, PriceIndex, ReferenceBook, ReferenceRow

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV"}
STAGE_FACTORS = {"П": 0.4, "Р": 0.6, "П+Р": 1.0}
# Default ПД/РД distribution — МУ №620 п.1.4. Overridden per book via
# reference_books.pd_pct / rd_pct (НЗ задают своё распределение).
DEFAULT_PD_PCT = 0.4
DEFAULT_RD_PCT = 0.6


def _stage_splits_for_book(book, stage: str) -> list[tuple[str, float]]:
    """When stage="П+Р", emit two positions per entity: ПД then РД.

    Percentages come from the book (pd_pct/rd_pct), falling back to МУ №620.
    """
    pd = float(book.pd_pct) if getattr(book, "pd_pct", None) is not None else DEFAULT_PD_PCT
    rd = float(book.rd_pct) if getattr(book, "rd_pct", None) is not None else DEFAULT_RD_PCT
    return {
        "П+Р": [("ПД", pd), ("РД", rd)],
        "П":   [("ПД", pd)],
        "Р":   [("РД", rd)],
    }.get(stage, [("", 1.0)])


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
    u = re.sub(r"\.\s*$", "", u)       # strip trailing abbreviation dot: "п.м." → "п.м"
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
    # distance (п.м ≡ м для линейных сооружений)
    ("км", "м"):                  lambda x: x * 1000,
    ("м", "км"):                  lambda x: x / 1000,
    ("км", "п.м"):                lambda x: x * 1000,
    ("п.м", "км"):                lambda x: x / 1000,
    ("м", "п.м"):                 lambda x: x,
    ("п.м", "м"):                 lambda x: x,
    # volume (строительный объём, ёмкость резервуаров)
    ("м³", "тыс. м³"):            lambda x: x / 1000,
    ("тыс. м³", "м³"):            lambda x: x * 1000,
}

# Long-form unit names (from reference_rows) → canonical abbreviations used in UNIT_CONVERSIONS
_UNIT_ALIASES: dict[str, str] = {
    "тысяч кубических метров / час":   "тыс. м³/ч",
    "тысяч кубических метров / сутки": "тыс. м³/сут",
    "тысяч кубических метров/час":     "тыс. м³/ч",
    "тысяч кубических метров/сутки":   "тыс. м³/сут",
    "кубических метров / час":         "м³/ч",
    "кубических метров / сутки":       "м³/сут",
    "кубических метров/час":           "м³/ч",
    "кубических метров/сутки":         "м³/сут",
    "кубический метр":                 "м³",
    "тонн / сутки":                    "т/сут",
    "тонн/сутки":                      "т/сут",
    "тонн в сутки":                    "т/сут",
    "метров":                          "м",
    "километров":                      "км",
    "погонных метров":                 "п.м",
    "погонный метр":                   "п.м",
    "тыс.м³/сут":                      "тыс. м³/сут",
    "тыс.м³/ч":                        "тыс. м³/ч",
    "м3/сут":                          "м³/сут",
    "м3/ч":                            "м³/ч",
    "тыс.м3/сут":                      "тыс. м³/сут",
    "тыс.м3/ч":                        "тыс. м³/ч",
    "тысяча кубических метров":        "тыс. м³",
    "тыс. кубических метров":          "тыс. м³",
    "тыс.м³":                          "тыс. м³",
    "тыс.м3":                          "тыс. м³",
    "квадратных метров":               "м²",
    "квадратный метр":                 "м²",
    "гектар":                          "га",
    "гектаров":                        "га",
    "километр":                        "км",
    "метр":                            "м",
    "погонный метр":                   "п.м",
    "кубических метров / секунду":     "м³/с",
    "кубических метров/секунду":       "м³/с",
    "м3/с":                            "м³/с",
}


def _canonical_unit(u: str) -> str:
    """Normalize unit to canonical abbreviation for conversion lookup."""
    return _UNIT_ALIASES.get(u.strip(), u.strip())


@dataclass
class RowMatch:
    row: ReferenceRow
    x_effective: float          # x converted to row's unit
    extrapolated: bool
    x_boundary: Optional[float] # boundary value used for extrapolation
    note: str                   # human-readable conversion / extrapolation note
    used_minimum: bool = False  # True when x_value was None and minimum row was used
    # 707/пр п.131 ф.8.4/8.5: X < Xмин/2 → цена на X=Xмин/2, умноженная на Кэ (≥0.1)
    extrap_scale: float = 1.0
    # 707/пр п.133 ф.8.6–8.8: a-only таблица → цена интер/экстраполирована напрямую (тыс.руб)
    override_price_thous: Optional[float] = None


# Physical units requiring actual dimensional conversion.
# Any unit NOT in this set is treated as a discrete count (штуки, ячейки, шкафы, etc.)
# and is 1:1 equivalent to any other discrete unit.
_PHYSICAL_UNITS: frozenset[str] = frozenset({
    "м³/сут", "тыс. м³/сут", "м³/ч", "тыс. м³/ч", "м³/с",
    "л/с", "т/сут", "т/г.", "тыс. т/г.", "км", "м", "п.м",
    "мвт", "квт", "гкал/ч", "мва", "ква",
    "м³", "тыс. м³", "га", "м²", "тыс. м²",
})

# Единица с «/» — это расход/интенсивность (физическая размерность), даже если её
# нет в словарях: полные словоформы из НЗ («кубических метров / секунду») не должны
# проваливаться в discrete-1:1 эквивалентность.
def _looks_physical(u: str) -> bool:
    ul = u.lower()
    return (
        ul in {p.lower() for p in _PHYSICAL_UNITS}
        or "/" in ul
        or any(w in ul for w in ("метр", "километр", "гектар", "тонн", "куб", "литр"))
    )


def _try_convert(x_value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Return converted value, or None if no conversion path exists.

    Discrete (non-physical) units like шт./ячейка/шкаф/пункт are all
    equivalent — return x_value unchanged (1:1).
    """
    from_c = _canonical_unit(from_unit)
    to_c   = _canonical_unit(to_unit)
    # Exact match after canonicalization
    if from_c == to_c:
        return x_value
    fn = UNIT_CONVERSIONS.get((from_c, to_c))
    if fn is not None:
        return fn(x_value)
    # Both units are discrete → 1:1 equivalence
    if not _looks_physical(from_c) and not _looks_physical(to_c):
        return x_value
    return None


def _match_row(
    db: Session,
    book_version_id: int,
    table_num: int,
    x_value: Optional[float],
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

    # ── X-fallback: use minimum row when X is unknown ─────────────────────
    if x_value is None:
        candidates_with_min = [r for r in all_rows if r.x_min is not None]
        min_row = min(candidates_with_min, key=lambda r: float(r.x_min)) \
                  if candidates_with_min else all_rows[0]
        x_eff = float(min_row.x_min) if min_row.x_min is not None else 0.0
        return RowMatch(min_row, x_eff, False, None, "", used_minimum=True)

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

    # Pass 2: extrapolation — boundary row (МУ №620 Прил.1 / 707/пр п.131, 133)
    def _join(base: str, extra: str) -> str:
        return f"{base}; {extra}" if base else extra

    for x_eff, note, rows in candidates:
        # 707/пр п.133 (ф.8.6–8.8): таблица только с параметром «а» —
        # интерполяция между опорными точками, экстраполяция со сглаживанием 0.6
        ao = _a_only_price(rows, x_eff)
        if ao is not None:
            price, brow, extrap_note = ao
            return RowMatch(
                brow, x_eff, True, None, _join(note, extrap_note),
                override_price_thous=price,
            )

        maxes = [(float(r.x_max), r) for r in rows if r.x_max is not None]
        mins  = [(float(r.x_min), r) for r in rows if r.x_min is not None]

        if maxes and x_eff > max(v for v, _ in maxes):
            bval, brow = max(maxes, key=lambda t: t[0])
            extrap_note = f"экстраполяция (X={x_eff:.4g} > {bval:.4g})"
            return RowMatch(brow, x_eff, True, bval, _join(note, extrap_note))

        if mins and x_eff < min(v for v, _ in mins):
            bval, brow = min(mins, key=lambda t: t[0])
            # 707/пр п.131 ф.8.4/8.5: X меньше половины минимального показателя →
            # цена на X=Xмин/2 (по ф.8.2), умноженная на Кэ = X/(0.5·Xмин), но не менее 0.1
            if bval > 0 and x_eff < 0.5 * bval:
                scale = max(0.1, x_eff / (0.5 * bval))
                extrap_note = (
                    f"707/пр п.131 ф.8.4 (X={x_eff:.4g} < Xмин/2={0.5 * bval:.4g}, "
                    f"Кэ={scale:.3g})"
                )
                return RowMatch(
                    brow, x_eff, True, bval, _join(note, extrap_note),
                    extrap_scale=scale,
                )
            extrap_note = f"экстраполяция (X={x_eff:.4g} < {bval:.4g})"
            return RowMatch(brow, x_eff, True, bval, _join(note, extrap_note))

    return None


def _a_only_price(
    rows: list[ReferenceRow], x_eff: float
) -> Optional[tuple[float, ReferenceRow, str]]:
    """707/пр п.133 (ф.8.6–8.8): price for tables carrying only parameter «а».

    Applies when EVERY row of the candidate set has b=NULL and at least two rows
    carry a boundary value (опорные точки = x_max, либо x_min для «свыше»-строк).
    Returns (price_thous, anchor_row, note) or None when not applicable.

    ф.8.6 — линейная интерполяция между соседними опорными точками;
    ф.8.7 — ниже минимальной точки: наклон первого сегмента × 0.6 (не ниже 0.1·a₁);
    ф.8.8 — выше максимальной: наклон последнего сегмента × 0.6.
    """
    pts: list[tuple[float, float, ReferenceRow]] = []
    for r in rows:
        if r.b is not None:
            return None  # смешанная таблица → стандартный путь
        xp = r.x_max if r.x_max is not None else r.x_min
        if xp is None or r.a is None:
            continue
        pts.append((float(xp), float(r.a), r))
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[0])
    xs = [p[0] for p in pts]
    avals = [p[1] for p in pts]

    if x_eff < xs[0]:
        slope = (avals[1] - avals[0]) / (xs[1] - xs[0]) if xs[1] != xs[0] else 0.0
        price = avals[0] - slope * (xs[0] - x_eff) * 0.6
        price = max(price, 0.1 * avals[0])
        return price, pts[0][2], f"707/пр п.133 ф.8.7 (X={x_eff:.4g} < {xs[0]:.4g})"

    if x_eff > xs[-1]:
        slope = (avals[-1] - avals[-2]) / (xs[-1] - xs[-2]) if xs[-1] != xs[-2] else 0.0
        price = avals[-1] + slope * (x_eff - xs[-1]) * 0.6
        return price, pts[-1][2], f"707/пр п.133 ф.8.8 (X={x_eff:.4g} > {xs[-1]:.4g})"

    for i in range(len(pts) - 1):
        if xs[i] <= x_eff <= xs[i + 1]:
            t = (x_eff - xs[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] != xs[i] else 0.0
            price = avals[i] + t * (avals[i + 1] - avals[i])
            return price, pts[i][2], "707/пр п.133 ф.8.6 (интерполяция)"

    return None


_PRICING_COEFFS = {"reconstruction", "overhaul", "deepening"}  # legacy: multiply; shown separately per step
_COMPLEX_COEFFS = {"asu", "seismic", "fishery"}  # legacy: sum fractional parts: 1+Σ(Ki-1)


def _coeff_mode(c: dict) -> str:
    """Combining mode for a resolved coefficient.

    Explicit book_conditions.apply_mode wins; legacy fallback by key name;
    unknown keys default to "multiply" — a resolved book condition must never
    be silently dropped.
    """
    mode = (c.get("_apply_mode") or "").strip().lower()
    if mode in ("multiply", "additive"):
        return mode
    name = (c.get("name") or "").strip()
    if name in _COMPLEX_COEFFS:
        return "additive"
    return "multiply"

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
) -> tuple[list[dict], list[str]]:
    """Replace AI flag-values (1.0) with actual coeff_max from book_conditions.

    Lookup order: table-specific conditions first (filtered by row_range against
    the matched row), then table=None (global). Uses coeff_max (upper bound).

    matched_row_num: row_num of the DB row that was matched (e.g. "п.10").
    When provided, conditions whose row_range does NOT include this row are skipped.

    Returns (resolved, dropped): dropped lists coeff keys the AI flagged but the
    reference book has no condition for — the caller MUST surface these loudly,
    a silently dropped coefficient means an underpriced position.
    """
    from app.models import BookCondition

    resolved = []
    dropped: list[str] = []
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
            dropped.append(key)  # no applicable condition → surface, don't hide
            continue

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
            "_apply_mode": getattr(cond, "apply_mode", None),
        })
    return resolved, dropped


def _apply_coefficients(coefficients: list[dict]) -> tuple[float, list[tuple[str, float, str, str]]]:
    """МУ №620 п.3.14: compute combined factor + applied coefficient list.

    Mode per coefficient — book_conditions.apply_mode, legacy fallback by key:
      multiply — ценообразующие, перемножаются (в т.ч. понижающие, K<1)
      additive — усложняющие, 1+Σ(Ki−1)

    Returns (factor, [(name, value, condition_short, mode), ...]).
    """
    pricing = 1.0
    complex_parts: list[float] = []
    applied: list[tuple[str, float, str, str]] = []

    for c in coefficients:
        name = (c.get("name") or "").strip()
        value = float(c.get("value") or 1.0)
        short = c.get("condition_short", "")
        mode = _coeff_mode(c)
        if value == 1.0 or not name:
            continue
        if mode == "additive":
            if value > 1.0:
                complex_parts.append(value - 1.0)
                applied.append((name, value, short, mode))
        else:
            pricing *= value
            applied.append((name, value, short, mode))

    complex_factor = 1.0 + sum(complex_parts)
    combined = pricing * complex_factor
    return combined, applied


_CODE_PREFIX    = re.compile(r'^(сбцп|сбц|мрр)\s+', re.IGNORECASE)
_CODE_TYPE_YEAR = re.compile(r'^(нз|сбцп|сбц|мрр)[\s\-]+(\d{4})', re.IGNORECASE)


def _normalize_code(code: str) -> str:
    return _CODE_PREFIX.sub('', code.strip()).lower()


def _find_active_book(db: Session, sbts_code: str) -> Optional[ReferenceBook]:
    """Find active book by code. Handles prefix variants and abbreviated codes.

    Matching order:
    1. Exact string match
    2. Prefix-normalized match (strips СБЦП/СБЦ/МРР prefix)
    3. Type+year fuzzy match: НЗ-2021-ЗС → НЗ-2021-МС847-СИТО when only one НЗ-2021 book exists
    """
    if not sbts_code:
        return None

    all_active = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    q_lower = sbts_code.strip().lower()
    query_norm = _normalize_code(sbts_code)

    for book in all_active:
        if book.code.strip().lower() == q_lower:
            return book  # exact
    for book in all_active:
        if _normalize_code(book.code) == query_norm:
            return book  # prefix-normalized

    # Fuzzy: match by type+year when abbreviation used (e.g. НЗ-2021-ЗС → НЗ-2021-МС847-СИТО)
    m = _CODE_TYPE_YEAR.match(sbts_code.strip())
    if m:
        q_type = m.group(1).lower()
        q_year = m.group(2)
        candidates = [
            b for b in all_active
            if (bm := _CODE_TYPE_YEAR.match(b.code.strip()))
            and bm.group(1).lower() == q_type
            and bm.group(2) == q_year
        ]
        if len(candidates) == 1:
            return candidates[0]

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


def _calculate_asutp_position(
    entity: dict[str, Any], book: ReferenceBook, db: Session, stage: str,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """СБЦП-2001-22 factor-based ASUTP calculation.

    Formula per module: Σ_баллов × S × K × stage_pct
    Total base: sum of modules (тыс.руб.)
    Final cost: total_base × Ki (stage already embedded)

    Unknown (factor, option) pairs are reported into `warnings` — a silently
    skipped factor means 0 баллов and an underpriced position.
    """
    asutp_factors: dict[str, str] = entity.get("asutp_factors") or {}
    asutp_k = float(entity.get("asutp_k") or 1.0)
    object_name = entity.get("object_name", "АСУТП")

    modules = (
        db.query(AsutpModule)
        .filter(AsutpModule.book_version_id == book.id)
        .order_by(AsutpModule.sort_order)
        .all()
    )
    if not modules:
        raise ValueError(f"Модули АСУТП не найдены для {book.code}")

    total_base_thous = 0.0
    module_results = []

    _MODULE_ATTR = {"ОР": "or", "ОО": "oo", "ИО": "io", "ТО": "to", "МО": "mo", "ПО": "po"}
    _unknown_opts: set[tuple[str, str]] = set()

    for mod in modules:
        score_attr = "score_" + _MODULE_ATTR.get(mod.module_code, mod.module_code.lower())

        if stage == "П":
            pct = mod.stage_p_min / 100
        elif stage == "П+Р":
            pct = 1.0
        else:  # Р (default)
            pct = mod.stage_r_min / 100

        total_score = 0
        for factor_code, option_code in sorted(asutp_factors.items()):
            opt = (
                db.query(AsutpFactorOption)
                .filter(
                    AsutpFactorOption.book_version_id == book.id,
                    AsutpFactorOption.factor_code == factor_code,
                    AsutpFactorOption.option_code == option_code,
                )
                .first()
            )
            if opt:
                total_score += getattr(opt, score_attr, None) or 0
            else:
                _unknown_opts.add((factor_code, option_code))

        s = float(mod.s_value)
        module_cost_thous = total_score * s * asutp_k * pct
        total_base_thous += module_cost_thous
        module_results.append({
            "module": mod.module_code, "score": total_score,
            "s": s, "pct": pct, "cost_thous": module_cost_thous,
        })

    if _unknown_opts and warnings is not None:
        pairs = ", ".join(f"{f}={o}" for f, o in sorted(_unknown_opts))
        warnings.append(
            f"{object_name}: недопустимые коды факторов АСУТП ({pairs}) — фактор даёт 0 баллов, "
            f"цена занижена. Проверьте формат кодов (Ф5→п.2.x, Ф9→п.6.x, Ф10→п.7.x)"
        )

    base_year = book.price_base_year or 2001
    idx_rec = _get_quarterly_index(db, base_year)
    idx_value = float(idx_rec.index_value) if idx_rec else 1.0

    cost_rub = total_base_thous * 1000 * idx_value

    if idx_rec and hasattr(idx_rec, 'quarter'):
        roman_q = ROMAN.get(idx_rec.quarter, str(idx_rec.quarter))
        idx_period = f"{roman_q} квартал {idx_rec.year} г."
        idx_just = idx_rec.source_ref
    else:
        idx_period = "—"
        idx_just = f"Индекс к {base_year} не задан"

    # Justification
    factors_str = "; ".join(f"{k}={v}" for k, v in sorted(asutp_factors.items()))
    justification = f"{book.code} (АСУТП): {factors_str}"
    if asutp_k != 1.0:
        justification += f"; К={_fmt_ru(asutp_k)}"

    # Formula: (ОР:score*S*pct% + ...) = base_thous * Ki
    parts = []
    for mr in module_results:
        if mr["pct"] > 0:
            parts.append(
                f"{mr['module']}:{mr['score']}*{_fmt_ru(mr['s'])}*{int(mr['pct']*100)}%"
                f"={_fmt_ru(mr['cost_thous'])}"
            )
    formula = (
        "(" + "; ".join(parts) + f")={_fmt_ru(total_base_thous)}тыс."
        f"*{_fmt_ru(idx_value)}"
    )

    return {
        "num":                       0,  # will be set by caller
        "name":                      object_name,
        "row_description":           "АСУТП (факторный метод, СБЦП-2001-22)",
        "unit":                      "система",
        "quantity":                  1.0,
        "item_count":                1,
        "justification":             justification,
        "formula":                   formula,
        "cost":                      round(cost_rub, 2),
        "cost_base":                 round(total_base_thous * 1000, 2),
        "book_code":                 book.code,
        "price_base_year":           base_year,
        "price_index":               idx_value,
        "price_index_period":        idx_period,
        "price_index_justification": idx_just,
        "table_num":                 None,
        "row_num":                   None,
        "used_minimum":              False,
        "section_num":               entity.get("section_num", 0),
        "section_name":              entity.get("section_name", ""),
        "_stage_embedded":           True,   # stage% already applied per-module
        "_asutp_modules":            module_results,
    }


def calculate(entities_dict: dict[str, Any], db: Session) -> dict[str, Any]:
    entities = [e for e in entities_dict.get("entities", []) if not e.get("deleted", False)]

    stage        = entities_dict.get("stage", "П+Р")
    stage_factor = STAGE_FACTORS.get(stage, 1.0)

    positions = []
    errors = []
    warnings: list[str] = []

    for entity in entities:
        sbts_code      = entity.get("sbts_code", "")
        table_num      = entity.get("sbts_table")
        object_type_id = entity.get("sbts_object_type_id")
        _x_raw         = entity.get("x_value")
        x_value        = float(_x_raw) if _x_raw is not None else None
        x_unit         = entity.get("x_unit", "")
        object_name    = entity.get("object_name", "")
        qty            = max(1, int(entity.get("quantity") or 1))

        book = _find_active_book(db, sbts_code)
        if not book:
            errors.append(f"{object_name}: активный справочник «{sbts_code}» не найден")
            continue

        # ── Survey books (изыскания) are priced by igi_calculator, not here ──
        # Their rows are in RUBLES (not тыс.руб) — pricing them through the
        # standard (a+b×X)×1000 path would inflate cost ×1000.
        if getattr(book, 'calc_method', 'standard') == 'survey':
            errors.append(
                f"{object_name}: «{book.code}» — справочник изысканий; позиция считается "
                f"в блоке «Изыскания» (ИГИ/ИГДИ/ИГФИ), не в основном расчёте ПИР"
            )
            continue

        # ── ASUTP factor-based path (no table_num needed) ────────────────────
        if getattr(book, 'calc_method', 'standard') == 'asutp':
            try:
                pos = _calculate_asutp_position(entity, book, db, stage, warnings=warnings)
                pos["num"] = len(positions) + 1
                positions.append(pos)
            except ValueError as exc:
                errors.append(f"{object_name}: {exc}")
            continue

        if not table_num:
            errors.append(f"{object_name}: не определена таблица СБЦП")
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

        # МУ №620 Прил.1 / 707/пр п.131 extrapolation
        if match.extrapolated and match.x_boundary is not None:
            if match.extrap_scale != 1.0:
                # 707/пр ф.8.4: цена считается в точке X=Xмин/2 (по ф.8.2), затем ×Кэ
                x_calc = 0.4 * match.x_boundary + 0.6 * (0.5 * match.x_boundary)
            else:
                x_calc = 0.4 * match.x_boundary + 0.6 * match.x_effective
        else:
            x_calc = match.x_effective

        # МУ №620 п.3.14: apply coefficients (resolve AI flag→actual DB value first)
        coefficients, dropped_coeffs = _resolve_coeff_values(
            db, book.id, table_num, entity.get("coefficients", []),
            matched_row_num=row.row_num,
        )
        coeff_factor, applied_coeffs = _apply_coefficients(coefficients)
        for _dk in dropped_coeffs:
            warnings.append(
                f"{object_name}: коэффициент «{_dk}» заявлен по ТЗ, но в справочнике "
                f"{book.code} (табл. {table_num}) нет условия — НЕ применён, цена может быть занижена"
            )

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

        # ── Unit-priced row detection ─────────────────────────────────────────
        # Row with b=NULL and no X range (x_min/x_max both NULL) is a per-item
        # price (цена за 1 шт/ячейку/пункт). X then means item count:
        # cost = a × X. Otherwise the range formula (a + b×X) applies.
        is_unit_priced = (
            row.b is None and row.x_min is None and row.x_max is None
            and match.override_price_thous is None
        )
        unit_count = 1.0
        if match.override_price_thous is not None:
            # 707/пр п.133: цена уже интер/экстраполирована по опорным точкам «а»
            unit_cost_base = match.override_price_thous * 1000
        elif is_unit_priced:
            unit_count = x_calc if (x_calc and x_calc > 0) else 1.0
            unit_cost_base = a * 1000 * unit_count      # base rubles (pre-index)
        else:
            # Reference rows in тыс. руб. at book's base year level
            unit_cost_base = (a + b * x_calc) * 1000    # base rubles (pre-index)
        # 707/пр п.131 ф.8.4/8.5: глубокая экстраполяция вниз → ×Кэ
        unit_cost_base *= match.extrap_scale
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
        if match.extrapolated and match.x_boundary is not None and match.extrap_scale == 1.0:
            justification += f"; МУ №620 Прил.1 (X={_fmt_ru(match.x_effective)} {row_unit}, X_расч={_fmt_ru(x_calc)})"
        for _name, _val, _short, _mode in applied_coeffs:
            # condition_short несёт собственную ссылку на пункт справочника
            label = _short or _name
            justification += f"; {label} (К={_fmt_ru(_val)})"
        if match.used_minimum:
            missing_hint = entity.get("x_value_missing_reason") or ""
            justification += f" [по мин. X={_fmt_ru(match.x_effective)}"
            if missing_hint:
                justification += f"; для точного расчёта: {missing_hint}"
            justification += "]"

        # ── Formula (расчёт стоимости) ────────────────────────────────────────
        a_rub, b_rub = a * 1000, b * 1000
        x_formula = x_calc if (match.extrapolated and match.x_boundary is not None) else match.x_effective
        if match.override_price_thous is not None:
            formula = _fmt_ru(match.override_price_thous * 1000)
        elif is_unit_priced and unit_count != 1.0:
            formula = f"{_fmt_ru(a_rub)}*{_fmt_ru(unit_count)}"
        elif b:
            formula = f"({_fmt_ru(a_rub)}+{_fmt_ru(b_rub)}*{_fmt_ru(x_formula)})"
        else:
            formula = _fmt_ru(a_rub)
        if match.extrap_scale != 1.0:
            formula += f"×{_fmt_ru(match.extrap_scale)}"
        for _n, _v, _s, _m in applied_coeffs:
            if _m == "multiply" and _v != 1.0:
                formula += f"×{_fmt_ru(_v)}"
        _complex_vals = [_v for _n, _v, _s, _m in applied_coeffs if _m == "additive" and _v > 1.0]
        if _complex_vals:
            _cf = 1.0 + sum(_v - 1.0 for _v in _complex_vals)
            formula += f"×{_fmt_ru(_cf)}"
        if idx_value != 1.0:
            formula += f"*{_fmt_ru(idx_value)}"
        if qty > 1:
            formula += f"*{qty}"

        stage_splits = _stage_splits_for_book(book, stage)
        for stage_label, stage_pct in stage_splits:
            sect_pct = 1.0
            if stage_label == "ПД":
                sect_pct = float(entity.get("pd_sections_pct") or 1.0)
            elif stage_label == "РД":
                sect_pct = float(entity.get("rd_sections_pct") or 1.0)

            combined_pct = stage_pct * sect_pct
            pos_cost_base = round(cost_base * combined_pct, 2)
            pos_cost = round(cost * combined_pct, 2)

            stage_formula = formula
            if stage_pct != 1.0:
                stage_formula += f"*{_fmt_ru(stage_pct)}"
            if sect_pct != 1.0:
                stage_formula += f"*{_fmt_ru(sect_pct)}"

            positions.append({
                "num":                 len(positions) + 1,
                "name":                object_name,
                "row_description":     row.description or "",
                "unit":                row_unit,
                "quantity":            match.x_effective,
                "item_count":          qty,
                "justification":       justification,
                "formula":             stage_formula,
                "cost":                pos_cost,
                "cost_base":           pos_cost_base,
                "book_code":           book.code,
                "price_base_year":     base_year,
                "price_index":         idx_value,
                "price_index_period":  idx_period,
                "price_index_justification": idx_justification,
                "table_num":           table_num,
                "row_num":             row_num,
                "used_minimum":        match.used_minimum,
                "section_num":         entity.get("section_num", 0),
                "section_name":        stage_label or entity.get("section_name", ""),
                "stage_label":         stage_label,
                "stage_pct":           combined_pct,
            })

    # ── ИГИ geological surveys ────────────────────────────────────────────────
    geological_surveys = entities_dict.get("geological_surveys", [])
    if geological_surveys:
        from app.services.igi_calculator import calculate_igi
        igi_positions, igi_errors = calculate_igi(geological_surveys, db)
        # Renumber to follow PIR positions
        for p in igi_positions:
            p["num"] = len(positions) + 1
            positions.append(p)
        errors.extend(igi_errors)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    base_cost    = sum(p["cost_base"] for p in positions)
    current_cost = sum(p["cost"] for p in positions)

    # Stage % is now embedded per-position (П+Р → two rows); no double-apply needed
    _standard_cost = current_cost
    _asutp_cost    = 0.0

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

    # ── Index freshness check — stale/missing index silently distorts КП price ──
    from datetime import date as _date
    _today = _date.today()
    _cur_q = (_today.month - 1) // 3 + 1
    for _by in index_summary:
        _rec = _get_quarterly_index(db, _by)
        if _rec is None:
            warnings.append(
                f"Индекс пересчёта к базе {_by} г. не задан — позиции выведены в базовом уровне цен!"
            )
        elif (_rec.year, _rec.quarter) < (_today.year, _cur_q):
            warnings.append(
                f"Индекс к базе {_by} г. устарел: {ROMAN.get(_rec.quarter, _rec.quarter)} кв. {_rec.year} г., "
                f"текущий квартал — {ROMAN.get(_cur_q, _cur_q)} кв. {_today.year} г. Проверьте письма Минстроя."
            )

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

    # stage_factor kept for backwards-compat but always 1.0 (embedded in positions)
    cost_with_stage = round(current_cost, 2)
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
        "stage_factor":              1.0,
        "current_cost":              round(current_cost, 2),
        "cost_with_stage":           cost_with_stage,
        "vat_rate":                  vat_rate,
        "vat_amount":                vat_amount,
        "total_with_vat":            total_with_vat,
        "errors":                    errors,
        "warnings":                  warnings,
    }

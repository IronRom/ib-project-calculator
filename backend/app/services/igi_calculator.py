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

_RE_ROW_NUM = re.compile(r'п\.(\d+)')
_RE_RNG_SEG = re.compile(r'(\d+)(?:-(\d+))?')


def _auto_table_config(
    db: Session, book_version_id: int, kind: str, complexity_cat: int,
):
    """Universal авто-позиция config (техотчёт / программа) from book_conditions.

    Conventions per survey book (kind = 'report' | 'program'):
      coeff_key='{kind}_table'   → coeff_min = номер таблицы стоимости
      coeff_key='{kind}_cat_{n}' → row_range = строки категории/группы ('пп.8-15')
      coeff_key='{kind}_base'    → coeff_min: 1 = камеральные+лабораторные (default),
                                   2 = полевые(×К1)+лабораторные+камеральные,
                                   3 = только камеральные (НЗ-281 табл.65:
                                       «при общей стоимости камеральных работ»,
                                       прим.2 — программа не учитывается)

    Дискриминатор колонки таблицы (когда один пункт даёт несколько цен —
    напр. СБЦ-2001 табл.53: «обоснование предпроектной документации» и
    «обоснование проекта (ТЭО)») хранится в row_range записи '<kind>_table'.

    Returns (table_num, (lo_row, hi_row) | None, base_mode, disc) where
    base_mode is 'nonfield' | 'all' | 'kameral'; table_num is None when not
    configured (auto-item skipped).
    """
    rep = (
        db.query(BookCondition)
        .filter(
            BookCondition.book_version_id == book_version_id,
            BookCondition.coeff_key == f"{kind}_table",
        )
        .first()
    )
    if not rep or rep.coeff_min is None:
        return None, None, "nonfield", ""
    table_num = int(rep.coeff_min)
    disc = (rep.row_range or "").strip()

    cat = (
        db.query(BookCondition)
        .filter(
            BookCondition.book_version_id == book_version_id,
            BookCondition.coeff_key == f"{kind}_cat_{complexity_cat}",
        )
        .first()
    )
    rng = None
    if cat and cat.row_range:
        m = _RE_RNG_SEG.search(cat.row_range.replace("пп.", "").replace("п.", ""))
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            rng = (lo, hi)

    base_rec = (
        db.query(BookCondition)
        .filter(
            BookCondition.book_version_id == book_version_id,
            BookCondition.coeff_key == f"{kind}_base",
        )
        .first()
    )
    base_code = int(base_rec.coeff_min) if (base_rec and base_rec.coeff_min is not None) else 1
    base_mode = {2: "all", 3: "kameral"}.get(base_code, "nonfield")
    return table_num, rng, base_mode, disc


def _report_config(db: Session, book_version_id: int, complexity_cat: int):
    """Back-compat wrapper: (table_num, cat_range) for the тех.отчёт table."""
    table_num, rng, _, _ = _auto_table_config(db, book_version_id, "report", complexity_cat)
    return table_num, rng

_SURVEY_LABEL_MAP = [
    # порядок важен: ИГДИ/ИГФИ/ИЭИ до ИГИ (подстроки); сверка регистронезависимая,
    # коды книг пишутся и «ИГДИ», и «игди»
    ("игди",  "Инженерно-геодезические изыскания"),
    ("игфи",  "Инженерно-геофизические изыскания"),
    ("гидромет", "Инженерно-гидрометеорологические изыскания"),
    ("игми", "Инженерно-гидрометеорологические изыскания"),
    # комбинированные книги (ИГИ-ИЭИ) используем как экологические — геология
    # покрыта отдельной книгой НЗ
    ("иэи",   "Инженерно-экологические изыскания"),
    ("экол",  "Инженерно-экологические изыскания"),
    ("геолог", "Инженерно-геологические изыскания"),
    ("иги",   "Инженерно-геологические изыскания"),
    ("геодез", "Инженерно-геодезические изыскания"),
    ("геофиз", "Инженерно-геофизические изыскания"),
]

def _fmt_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _survey_label(book_code: str) -> str:
    code = (book_code or "").lower()
    for keyword, label in _SURVEY_LABEL_MAP:
        if keyword in code:
            return label
    return "Инженерные изыскания"


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
    pricing_method: str = "mu620",
) -> float:
    """Cost of the technical report from the book's report table.

    Table number and category row ranges come from book_conditions
    (report_table / report_cat_N) — see _report_config. Returns 0.0 when the
    book has no report table configured.

    X = kameral_total_rub converted to тыс.руб.
    Returns cost in rubles at base year level (before index).
    Linear interpolation between reference points (например НЗ-281 п.121 прим.1).
    Reference points stored as x_max (regular rows) or x_min (last "свыше" row).
    """
    kameral_thous = kameral_total_rub / 1000

    report_table, cat_range, _, disc = _auto_table_config(
        db, book_version_id, "report", complexity_cat)
    if report_table is None:
        return 0.0
    return _interpolate_cost_table(db, book_version_id, report_table, cat_range,
                                  kameral_thous, pricing_method, disc)


_RE_BOUND_TO = re.compile(r"до\s+([\d\s.,]+)", re.IGNORECASE)
_RE_BOUND_OVER = re.compile(r"св\.?\s*([\d\s.,]+)", re.IGNORECASE)


def _bound_from_text(text: str) -> Optional[float]:
    """Верхняя граница интервала из описания строки («Св. 2 до 5 тыс. руб.» → 5,
    «Св. 20 тыс. руб.» → 20). Нужна для таблиц, где диапазон не разложен в
    x_min/x_max (СБЦ-2001)."""
    def _num(raw: str) -> Optional[float]:
        cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".").rstrip(".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    m = _RE_BOUND_TO.search(text)
    if m:
        return _num(m.group(1))
    m = _RE_BOUND_OVER.search(text)
    if m:
        return _num(m.group(1))
    return None


def _interpolate_cost_table(
    db: Session, book_version_id: int, table_num: int,
    cat_range, x_thous: float, pricing_method: str = "mu620", disc: str = "",
) -> float:
    """Интерполяция/экстраполяция по опорным точкам таблицы стоимости (руб).

    Внутри интервала — линейная интерполяция (707/пр п.133 ф.8.6).
    Вне интервала для книг 707/пр — ф.8.7 (ниже минимума) и ф.8.8 (выше
    максимума): наклон крайнего сегмента × 0,6. Без этого техотчёт при малой
    базе брался по цене первой строки таблицы и оказывался в разы дороже самих
    работ (эталон Инфостроя ф.8.7 применяет: ЛС-02 «134 685 − (203 793−134 685)
    /(50 000−20 000)×(20 000−17 255)×0,6»). Для не-707/пр книг (СБЦ-2001:
    «показатели интервала применяются без интерполяции») крайняя точка
    сохраняется как раньше.
    """
    rows: list[ReferenceRow] = (
        db.query(ReferenceRow)
        .filter(
            ReferenceRow.book_version_id == book_version_id,
            ReferenceRow.table_num == table_num,
        )
        .all()
    )
    if disc:
        narrowed = [r for r in rows if disc.lower() in (r.description or "").lower()]
        if narrowed:
            rows = narrowed

    if cat_range is not None:
        lo_p, hi_p = cat_range
        cat_rows = []
        for r in rows:
            m = _RE_ROW_NUM.search(r.row_num or "")
            if m and lo_p <= int(m.group(1)) <= hi_p:
                cat_rows.append(r)
    else:
        cat_rows = rows

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
        else:
            # СБЦ-2001: границы интервала живут в описании («Св. 2 до 5 тыс. руб.»)
            bound = _bound_from_text(r.description or "")
            if bound is not None:
                ref_points.append((bound, float(r.b or r.a or 0)))

    if not ref_points:
        return 0.0

    ref_points.sort(key=lambda p: p[0])

    is_707 = (pricing_method or "mu620") == "707pr"
    if x_thous <= ref_points[0][0]:
        if is_707 and len(ref_points) > 1:
            (x1, b1), (x2, b2) = ref_points[0], ref_points[1]
            if x2 != x1:
                # ф.8.7: Ц = а1 − (а2−а1)/(Х2−Х1) × (Х1−Х) × 0,6
                price = b1 - (b2 - b1) / (x2 - x1) * (x1 - x_thous) * 0.6
                return max(price, 0.0)
        return ref_points[0][1]
    if x_thous >= ref_points[-1][0]:
        if is_707 and len(ref_points) > 1:
            (xp, bp), (xm, bm) = ref_points[-2], ref_points[-1]
            if xm != xp:
                # ф.8.8: Ц = амакс + (амакс−апред)/(Хмакс−Хпред) × (Х−Хмакс) × 0,6
                return bm + (bm - bp) / (xm - xp) * (x_thous - xm) * 0.6
        return ref_points[-1][1]

    # Linear interpolation between adjacent reference points
    for i in range(len(ref_points) - 1):
        x0, b0 = ref_points[i]
        x1, b1 = ref_points[i + 1]
        if x0 <= x_thous <= x1:
            t = (x_thous - x0) / (x1 - x0)
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
        survey_section = _survey_label(book_code)
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

        # Bases for auto-items (техотчёт, программа):
        #   lab_base / kameral_base — лабораторные и камеральные по показателям затрат
        #   field_pz_base           — полевые × К1 (без ДЗ/зимы/К2/индекса) — для книг,
        #                             где X отчёта/программы = полевые + камеральные
        lab_base = 0.0
        kameral_base = 0.0
        field_pz_base = 0.0
        # текущие (проиндексированные) суммы для процентных позиций
        cur_cost = {"field": 0.0, "lab": 0.0, "kameral": 0.0, "percent": 0.0}

        items = [it for it in survey.get("items", []) if not it.get("deleted")]

        for item in items:
            work_cat = item.get("work_category", "field")
            a = float(item.get("a", 0))
            b = float(item.get("b", 0))
            volume = float(item.get("volume", 0))
            k_item = float(item.get("k", 1.0) or 1.0)
            x_unit = item.get("x_unit", "")
            table_num = item.get("table_num", 0)
            row_num = item.get("row_num", "")
            desc = item.get("description", "")
            otype_name = item.get("object_type_name", "")

            # ── Процентная позиция (МРР гл.3: транспорт табл.2.2,
            # организация/ликвидация табл.2.3, отчёт «% от камеральных») ──
            if work_cat == "percent":
                pct = float(item.get("pct", 0))
                pbase = item.get("percent_base", "field")
                if pbase == "field+percent":
                    base_sum = cur_cost["field"] + cur_cost["percent"]
                else:
                    base_sum = cur_cost.get(pbase, 0.0)
                # Ступенчатая шкала (СБЦ-2001 табл.4/62/87): процент зависит от
                # стоимости работ-базы в БАЗОВОМ уровне цен книги
                scale = item.get("pct_scale")
                if scale:
                    base_ref = base_sum / index_val if index_val else base_sum
                    for step in scale:
                        if float(step["lo"]) <= base_ref < float(step["hi"]):
                            pct = float(step["pct"])
                            desc = step.get("label") or desc
                            otype_name = step.get("label") or otype_name
                            break
                    else:
                        last = scale[-1]
                        pct = float(last["pct"])
                        desc = last.get("label") or desc
                        otype_name = last.get("label") or otype_name
                cost = base_sum * pct / 100.0
                counts_as = item.get("counts_as") or "percent"
                cur_cost[counts_as] = cur_cost.get(counts_as, 0.0) + cost
                if counts_as == "kameral":
                    kameral_base += cost / index_val if index_val else 0.0
                positions.append({
                    "num": len(positions) + 1,
                    "name": otype_name or desc,
                    "row_description": desc,
                    "unit": "%",
                    "quantity": pct,
                    "item_count": 1,
                    "justification": (
                        f"{book_code}, табл. {table_num} {row_num} "
                        f"({pct}% от {pbase}: {round(base_sum, 2)} руб)"
                    ).strip(),
                    "formula": f"{_fmt_money(base_sum)}×{pct}%",
                    "cost": round(cost, 2),
                    "cost_base": round(cost / index_val, 2) if index_val else 0,
                    "book_code": book_code,
                    "price_base_year": price_base_year,
                    "price_index": index_val,
                    "price_index_period": idx_period,
                    "price_index_justification": idx_just,
                    "table_num": table_num,
                    "row_num": row_num,
                    "used_minimum": False,
                    "section_num": 0,
                    "section_name": survey_section,
                    "work_category": "percent",
                    "_stage_embedded": True,
                })
                continue

            # Base cost: (a + b × volume) × k (множитель примечаний таблицы)
            base = (a + b * volume) * k_item

            if work_cat == "field":
                # Per-table K1 from book_conditions; fall back to survey.k1
                table_k1 = _get_k1_for_table(db, book_version_id, table_num)
                effective_k1 = table_k1 if table_k1 is not None else k1

                cost = base * effective_k1 * (1 + winter_factor) * k2 * index_val
                field_pz_base += base * effective_k1
                cur_cost["field"] += cost
                coeff_note = (
                    f"К1={effective_k1}"
                    + (f"; зима {round(winter_factor * 100, 1)}%" if winter_factor else "")
                    + (f"; К2={k2}" if k2 != 1.0 else "")
                )
            elif work_cat in ("lab", "kameral", "program"):
                effective_k1 = k1  # not used, but keep variable consistent
                cost = base * index_val
                coeff_note = ""
                # Accumulate for Table 65 (technical report X parameter)
                if work_cat == "lab":
                    lab_base += base
                    cur_cost["lab"] += cost
                elif work_cat == "kameral":
                    kameral_base += base
                    cur_cost["kameral"] += cost
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
            if k_item != 1.0:
                formula += f"×{k_item}"
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
                "section_name": survey_section,
                "work_category": work_cat,
                "_stage_embedded": True,  # ИГИ costs are not split by П/Р stage
            })

        # Auto-append технический отчёт и программу (если в book_conditions
        # заданы report_table / program_table). База X зависит от книги:
        # 'nonfield' — лаб+камеральные (НЗ-281 п.121, ИГФИ табл.52);
        # 'all' — полевые(×К1)+камеральные (ИГДИ табл.80/81, ИГФИ табл.53).
        for kind, label in (("report", "Технический отчёт"), ("program", "Программа изысканий")):
            auto_table, cat_range, base_mode, disc = _auto_table_config(
                db, book_version_id, kind, complexity_cat
            )
            if auto_table is None:
                continue
            if base_mode == "kameral":
                base_x = kameral_base
            elif base_mode == "all":
                base_x = lab_base + kameral_base + field_pz_base
            else:  # 'nonfield'
                base_x = lab_base + kameral_base
            if base_x <= 0:
                continue
            auto_cost_base = _interpolate_cost_table(
                db, book_version_id, auto_table, cat_range, base_x / 1000,
                getattr(book_rec, "pricing_method", "mu620") or "mu620", disc,
            )
            auto_cost = auto_cost_base * index_val
            if auto_cost <= 0:
                continue
            base_note = {
                "all": "полевые+лаб+камеральные",
                "kameral": "камеральные",
            }.get(base_mode, "лаб+камеральные")
            positions.append({
                "num": len(positions) + 1,
                "name": f"{label} ({survey_section.lower()}, кат.слож.{complexity_cat})",
                "row_description": f"Табл.{auto_table} {book_code}",
                "unit": "один отчёт" if kind == "report" else "программа",
                "quantity": 1,
                "item_count": 1,
                "justification": (
                    f"{book_code}, табл. {auto_table}"
                    f" ({base_note}: {round(base_x / 1000, 1)} тыс.руб, интерполяция)"
                ),
                "formula": f"{int(auto_cost_base)}×{index_val}",
                "cost": round(auto_cost, 2),
                "cost_base": round(auto_cost_base, 2),
                "book_code": book_code,
                "price_base_year": price_base_year,
                "price_index": index_val,
                "price_index_period": idx_period,
                "price_index_justification": idx_just,
                "table_num": auto_table,
                "row_num": "",
                "used_minimum": False,
                "section_num": 0,
                "section_name": survey_section,
                "work_category": "report" if kind == "report" else "program",
                "_stage_embedded": True,  # изыскания не делятся по П/Р
            })

    return positions, errors

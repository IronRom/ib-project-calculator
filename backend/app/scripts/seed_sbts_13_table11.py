"""Seed СБЦП 81-2001-13 — Table 11 only (Трансформаторные подстанции и РУ).

Source: СБЦП 81-2001-13, стр. 67-68.
All prices: тыс.руб. at 01.01.2001 level. b=0 for all rows (fixed price per unit).

Run inside container:
  docker exec ib-project-calculator-backend-1 python /app/app/scripts/seed_sbts_13_table11.py
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import BookCondition, BookObjectType, ReferenceBook, ReferenceRow

TABLE_NUM = 11

# ── Object types for Table 11 ─────────────────────────────────────────────────
# Each group becomes one BookObjectType. All rows share a single group type
# (the calculator picks the exact row by matching with the entity).
# To allow exact-row lookup without X range matching, each row IS its own type.

OBJECT_TYPES = [
    # (id_key, name)
    ("substation_1",  "Мачтовая однотрансформаторная подстанция до 1×160 кВА"),
    ("substation_2",  "Закрытая двухтрансформаторная подстанция без РУ ВН до 2×630 кВА"),
    ("substation_3",  "Закрытая двухтрансформаторная подстанция с РУ ВН до 2×630 кВА (до 6 ячеек)"),
    ("substation_4",  "Открытая двухтрансформаторная подстанция до 2×4000 кВА (до 16 ячеек)"),
    ("substation_5",  "Закрытая двухтрансформаторная подстанция до 2×4000 кВА (до 16 ячеек)"),
    ("rp_6",          "РП 6-20 кВ двухсекционный открытый (до 16 ячеек)"),
    ("rp_7",          "РП 6-20 кВ двухсекционный закрытый (до 16 ячеек)"),
    ("rp_8",          "РП 6-20 кВ двухсекционный совмещённый с подстанцией до 2×630 кВА (до 16 ячеек)"),
    # Релейная защита
    ("rza_9",         "РЗА. Радиальная секц. сеть простой конфигурации (до 5 выключателей)"),
    ("rza_10",        "РЗА. Разветвл. секц. сеть, 2 источника питания (до 10 выключателей)"),
    ("rza_11",        "РЗА. Разветвл. секц. сеть, 2 источника питания (свыше 10 выключателей)"),
    ("rza_12",        "РЗА. Разветвл. секц. сеть, >2 источников питания (до 10 выключателей)"),
    # Линейная автоматика до 20 кВ
    ("la_13",         "Линейная автоматика. Радиальная секц. сеть простой конфигурации (до 5 выкл.)"),
    ("la_14",         "Линейная автоматика. Разветвл. секц. сеть, 2 источника питания (до 10 выкл.)"),
    ("la_15",         "Линейная автоматика. Разветвл. секц. сеть, до 2 источников (свыше 10 выкл.)"),
    ("la_16",         "Линейная автоматика. Разветвл. секц. сеть, >2 источников (свыше 10 выкл.)"),
    # Расчёт токов КЗ до 20 кВ
    ("tkz_17",        "ТКЗ. Радиальная секц. сеть простой конфигурации (до 5 выключателей)"),
    ("tkz_18",        "ТКЗ. Разветвл. секц. сеть, 2 источника питания (до 10 выключателей)"),
    ("tkz_19",        "ТКЗ. Разветвл. секц. сеть, до 2 источников (свыше 10 выключателей)"),
    ("tkz_20",        "ТКЗ. Разветвл. секц. сеть, >2 источников (свыше 10 выключателей)"),
    # Дооборудование РУ
    ("ru_21",         "Дооборудование РУ 6-20 кВ шкафами (>6 ячеек) или реконструкция шкафов"),
]

# ── Reference rows: (type_key, row_num, a, x_unit) ───────────────────────────
# b=0 for all — fixed price per unit. x_min/x_max=null (no range).
# X parameter = 1 unit always; quantity field handles multiple.
ROWS = [
    # Трансформаторные подстанции
    ("substation_1",  "п.1",  8.25,   "подстанция"),
    ("substation_2",  "п.2",  59.07,  "подстанция"),
    ("substation_3",  "п.3",  85.47,  "подстанция"),
    ("substation_4",  "п.4",  156.59, "подстанция"),
    ("substation_5",  "п.5",  223.08, "подстанция"),
    # Распределительные пункты
    ("rp_6",          "п.6",  104.94, "пункт"),
    ("rp_7",          "п.7",  157.25, "пункт"),
    ("rp_8",          "п.8",  263.18, "пункт"),
    # Релейная защита
    ("rza_9",         "п.9",  4.79,   "линия"),
    ("rza_10",        "п.10", 9.41,   "линия"),
    ("rza_11",        "п.11", 11.88,  "линия"),
    ("rza_12",        "п.12", 15.84,  "линия"),   # ← used in НС7 example
    # Линейная автоматика
    ("la_13",         "п.13", 4.13,   "линия"),
    ("la_14",         "п.14", 8.25,   "линия"),
    ("la_15",         "п.15", 11.88,  "линия"),
    ("la_16",         "п.16", 17.66,  "линия"),
    # Расчёт токов КЗ
    ("tkz_17",        "п.17", 2.64,   "линия"),
    ("tkz_18",        "п.18", 5.28,   "линия"),
    ("tkz_19",        "п.19", 10.07,  "линия"),
    ("tkz_20",        "п.20", 13.53,  "линия"),
    # Дооборудование РУ
    ("ru_21",         "п.21", 20.79,  "шкаф"),
]

# ── Book conditions (from chapter 2.8 of СБЦП-2001-13) ───────────────────────
# Per table 11, п.2.8.1:
CONDITIONS = [
    # Single-transformer / single-section → coefficient 0.5 (global for table 11)
    {
        "table_num": TABLE_NUM, "coeff_key": "single_transformer",
        "condition_short": "Однотрансф./односекционные РУ (п.2.8.1 СБЦП-13) → К=0,5",
        "condition_text_full": (
            "СБЦП 81-2001-13 п.2.8.1: для однотрансформаторных подстанций и "
            "односекционных распределительных устройств применяется коэффициент 0,5"
        ),
        "effect_type": "multiplier_range",
        "coeff_min": 0.5, "coeff_max": 0.5,
    },
    # Two-section closed RP combined with substation → 0.8
    {
        "table_num": TABLE_NUM, "coeff_key": "combined_rp_substation",
        "condition_short": "Двухсекц. закрытый РП совмещён с ТП (п.2.8.1) → К=0,8",
        "condition_text_full": (
            "СБЦП 81-2001-13 п.2.8.1: для двухсекционных закрытых РП, "
            "совмещённых с одной трансформаторной подстанцией → К=0,8"
        ),
        "effect_type": "multiplier_range",
        "coeff_min": 0.8, "coeff_max": 0.8,
    },
    # Extra cells beyond п.6/7/8 → +5% each additional cell
    {
        "table_num": TABLE_NUM, "coeff_key": "extra_cells",
        "condition_short": "Каждая доп. ячейка сверх п.6-8 (п.2.8.2 СБЦП-13) → +5%",
        "condition_text_full": (
            "СБЦП 81-2001-13 п.2.8.2: для РП с количеством ячеек сверх указанных "
            "в п.6, 7, 8 таблицы 11, за каждую последующую ячейку прибавляется 5% стоимости"
        ),
        "effect_type": "additive",
        "coeff_min": 0.05, "coeff_max": 0.05,
    },
]


def main():
    db = SessionLocal()
    try:
        # 1. Upsert book
        book = db.query(ReferenceBook).filter(
            ReferenceBook.code == "СБЦП 81-2001-13"
        ).first()
        if not book:
            book = ReferenceBook(
                code="СБЦП 81-2001-13",
                official_name=(
                    "Справочник базовых цен на проектные работы в строительстве. "
                    "Объекты нефтеперерабатывающей и нефтехимической промышленности"
                ),
                version=1,
                status="consistent",
                is_active=True,
                price_base_year=2001,
                calc_method="standard",
            )
            db.add(book)
            db.flush()
            print(f"Created book СБЦП 81-2001-13 id={book.id}")
        else:
            book.status = "consistent"
            book.is_active = True
            print(f"Updated book СБЦП 81-2001-13 id={book.id}")

        book_id = book.id

        # 2. Seed object types
        existing_types = {
            t.name: t
            for t in db.query(BookObjectType).filter(
                BookObjectType.book_version_id == book_id,
                BookObjectType.table_num == TABLE_NUM,
            )
        }
        type_id_map: dict[str, int] = {}

        for key, name in OBJECT_TYPES:
            if name in existing_types:
                type_id_map[key] = existing_types[name].id
            else:
                ot = BookObjectType(
                    book_version_id=book_id,
                    name=name,
                    table_num=TABLE_NUM,
                )
                db.add(ot)
                db.flush()
                type_id_map[key] = ot.id
                print(f"  + type [{TABLE_NUM}] {name[:60]}")

        # 3. Seed reference rows
        existing_rows = {
            (r.object_type_id, r.row_num)
            for r in db.query(ReferenceRow).filter(
                ReferenceRow.book_version_id == book_id,
                ReferenceRow.table_num == TABLE_NUM,
            )
        }

        for type_key, row_num, a, x_unit in ROWS:
            ot_id = type_id_map[type_key]
            if (ot_id, row_num) not in existing_rows:
                db.add(ReferenceRow(
                    book_version_id=book_id,
                    object_type_id=ot_id,
                    table_num=TABLE_NUM,
                    row_num=row_num,
                    x_min=None,
                    x_max=None,
                    x_unit=x_unit,
                    a=a,
                    b=0,
                ))
                print(f"  + row {row_num}: a={a} {x_unit}")

        # 4. Seed book conditions
        existing_cond_keys = {
            c.coeff_key
            for c in db.query(BookCondition).filter(
                BookCondition.book_version_id == book_id,
                BookCondition.table_num == TABLE_NUM,
            )
            if c.coeff_key
        }
        for cdata in CONDITIONS:
            if cdata["coeff_key"] not in existing_cond_keys:
                db.add(BookCondition(
                    book_version_id=book_id,
                    table_num=cdata["table_num"],
                    coeff_key=cdata["coeff_key"],
                    condition_short=cdata["condition_short"],
                    condition_text_full=cdata["condition_text_full"],
                    effect_type=cdata["effect_type"],
                    coeff_min=cdata["coeff_min"],
                    coeff_max=cdata["coeff_max"],
                ))
                print(f"  + condition {cdata['coeff_key']}: {cdata['coeff_min']}")

        db.commit()
        print(f"\nDone. СБЦП-2001-13 table {TABLE_NUM} seeded.")

        # 5. Verification: reproduce real НС7 example
        from app.services.calculator import calculate
        entities = {
            "stage": "Р",
            "entities": [{
                "sbts_code": "СБЦП 81-2001-13",
                "object_name": "РЗА НС7 (5 линий)",
                "category": "overhaul",
                "object_type": "РЗА. Разветвл. секц. сеть, >2 источников питания (до 10 выключателей)",
                "address": "г. Екатеринбург, НС7",
                "sbts_table": TABLE_NUM,
                "sbts_object_type_id": type_id_map["rza_12"],
                "x_value": 1.0,
                "x_unit": "линия",
                "quantity": 5,
                "coefficients": [],
            }]
        }
        result = calculate(entities, db)
        if result["errors"]:
            print(f"\nVerification FAILED: {result['errors']}")
        else:
            # Stage is applied at aggregate level, not per position
            cost_with_stage = result["cost_with_stage"]
            expected = 337_392.0  # 15.84 * 1000 * 5 * 7.1 * 0.60
            match = abs(cost_with_stage - expected) < 2.0
            print(f"\nVerification: cost_with_stage={cost_with_stage:,.2f} expected={expected:,.2f} match={match}")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        import traceback; traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

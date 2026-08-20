"""Типовой состав изысканий (автосборка) — данными книги, а не эвристикой.

Конвенция book_conditions (движок: calculator._autoitems_from_conditions):
    coeff_key  = 'autoitem_<work_category>'  (field | lab | kameral | program)
    table_num  = номер таблицы книги
    row_range  = номер строки, опционально с дискриминатором «п.4|полев»
    coeff_min  = объём по умолчанию (УСЛОВНЫЙ — правится во вкладке «Изыскания»)
    condition_short = как называть позицию в смете

Строка адресуется (таблица, пункт) + вид работ (маркер «(полевые)»/
«(камеральные)» в имени типа) + категория сложности («[II]» в описании), чего
достаточно и для НЗ (одна строка на пункт), и для СБЦ-2001 (шесть строк на
пункт). Строка с единицей «%» становится процентной позицией автоматически.

СОСТАВЫ ВЫВЕРЕНЫ по эталонной смете Инфостроя «(ПС) Реконструкция ФГБУ СЛО
Россия, 1-я Рейсовая» 14.04.2026 — каждая позиция ниже стоит в ЛС-01…ЛС-04
эталона, ставки сверены встроенными spot-check'ами.

Объёмы по умолчанию — типовой минимум для площадочного объекта ~1 га
(площадка застроенная, II категория сложности): их всё равно уточняет
пользователь, но состав и ставки уже верные.

Запуск:
    docker exec <backend> sh -c "PYTHONPATH=/app python /app/scripts/seed_survey_autoitems.py"
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal                # noqa: E402
from app.models import BookCondition, ReferenceBook  # noqa: E402

# code → [(work_category, table_num, row_num, volume, name)]
COMPOSITION: dict[str, list[tuple[str, int, str, float, str]]] = {
    # ── Геодезия. Эталон ЛС-01 ────────────────────────────────────────────────
    "НЗ-2024-МС812-ИГДИ": [
        ("field", 7, "п.8", 3,
         "Создание пунктов плановой опорной геодезической сети (спутниковые "
         "определения, 2 разряд)"),
        ("field", 11, "п.2", 3,
         "Создание нивелирных пунктов высотной опорной сети (нивелирование II класса)"),
        ("field", 18, "п.15", 1,
         "Топографическая съёмка 1:1000, застроенная территория, II категория"),
        ("kameral", 16, "п.1", 3,
         "Камеральная обработка измерений плановой опорной сети"),
        ("kameral", 16, "п.2", 3,
         "Камеральная обработка измерений нивелирной сети"),
        ("kameral", 48, "п.17", 1,
         "Создание инженерно-топографических планов 1:1000, застроенная территория"),
    ],
    # ── Геология. Эталон ЛС-02 ────────────────────────────────────────────────
    "НЗ-2025-МС281-ИГИ": [
        ("field", 12, "п.6", 1, "Рекогносцировочное обследование, II категория"),
        ("field", 14, "п.2", 30,
         "Проходка инженерно-геологических скважин колонковым бурением "
         "(d ≤ 160 мм, глубина ≤ 15 м)"),
        ("field", 56, "п.1", 5, "Приёмка, регистрация и консервация образца грунта"),
        ("field", 56, "п.2", 5, "Отбор проб из образца грунта (физические свойства)"),
        ("field", 56, "п.3", 5, "Описание образца грунта"),
        ("lab", 57, "п.1", 5, "Определение влажности грунта высушиванием"),
        ("kameral", 33, "п.2", 30,
         "Камеральная обработка результатов проходки скважин, II категория"),
        ("kameral", 62, "п.1", 5,
         "Камеральная обработка лабораторных определений физических свойств"),
        ("program", 66, "п.2", 1,
         "Программа инженерно-геологических изысканий, II категория"),
    ],
    # ── Гидрометеорология. Эталон ЛС-03 ───────────────────────────────────────
    "СБЦ-2001-ГИДРОМЕТ": [
        ("field", 43, "п.2", 1, "Рекогносцировочное обследование бассейна реки"),
        ("field", 48, "п.2", 1, "Определение скорости и направления течения"),
        ("kameral", 43, "п.2", 1,
         "Рекогносцировочное обследование бассейна реки (камеральные работы)"),
        ("kameral", 69, "п.1", 1,
         "Составление климатической характеристики района изысканий"),
        ("kameral", 64, "п.2", 1,
         "Записка «Характеристика естественного режима русла реки»"),
        ("kameral", 51, "п.1", 1,
         "Таблица гидрологической изученности бассейна реки"),
        # программа гидромета — по таблице 53 (цена от стоимости камеральных
        # работ), посев ниже через program_table/program_base/дискриминатор
    ],
    # ── Экология. Эталон ЛС-04 ────────────────────────────────────────────────
    "СБЦ-2001-ИГИ-ИЭИ": [
        ("field", 9, "п.2", 1,
         "Инженерно-геологическая, гидрогеологическая рекогносцировка"),
        ("field", 10, "п.3", 1,
         "Маршрутные наблюдения при составлении инженерно-экологической карты"),
        ("field", 11, "п.2", 1, "Описание точек наблюдений"),
        ("field", 60, "п.7", 6,
         "Отбор точечных проб почво-грунтов на загрязнённость"),
        ("field", 60, "п.10", 3,
         "Отбор проб почво-грунтов для бактериологического анализа"),
        ("field", 91, "п.1", 2, "Измерение плотности потока радона на участке"),
        ("field", 92, "п.2", 10, "Радиационное обследование участка"),
        ("lab", 91, "п.4|полев", 6,
         "Спектрометрия (альфа-, бета-, гамма) лабораторно с пробоподготовкой"),
        ("kameral", 9, "п.2", 1,
         "Рекогносцировка (камеральная обработка)"),
        ("kameral", 11, "п.2", 1,
         "Описание точек наблюдений (камеральная обработка)"),
        ("kameral", 91, "п.1", 2,
         "Измерение потока радона (камеральная обработка)"),
        ("kameral", 92, "п.2", 10,
         "Радиационное обследование участка (камеральная обработка)"),
        ("kameral", 86, "п.6", 1,
         "Камеральная обработка химических и бактериологических анализов "
         "(% от лабораторных)"),
        ("kameral", 81, "п.1", 1, "Составление программы производства работ"),
    ],
}

# Параметры блока изысканий по умолчанию: coeff_key='autoblock_<param>'.
# СБЦ-2001 табл.2 общих указаний: полевые работы в неблагоприятный период года
# 6–7,5 мес — К=1,3 (эталон применяет его ко ВСЕМ полевым СБЦ: ЛС-03 «18×(1,3)»,
# ЛС-04 «27×(1,3)»). Для НЗ период учитывается процентом ДЗнп (см. surcharges).
BLOCK_PARAMS: dict[str, dict[str, float]] = {
    "СБЦ-2001-ГИДРОМЕТ": {"winter_pct": 0.3},
    "СБЦ-2001-ИГИ-ИЭИ": {"winter_pct": 0.3},
}

# Авто-позиции «цена от стоимости работ» (техотчёт/программа):
# coeff_key='<kind>_table' → coeff_min=таблица, row_range=дискриминатор колонки,
# '<kind>_base' → 1 лаб+камеральные | 2 полевые+лаб+камеральные | 3 камеральные.
COST_TABLES: dict[str, list[tuple[str, int, int, str]]] = {
    # СБЦ-2001 гидромет п.5 табл.53: цена программы от стоимости камеральных
    # работ, колонка «Обоснование проекта (ТЭО)» (прим.1: одностадийное
    # проектирование считается по ценам проекта)
    "СБЦ-2001-ГИДРОМЕТ": [("program", 53, 3, "ТЭО")],
}

# Ставки эталона: (код книги, таблица, строка, ожидаемое a или b)
SPOT_CHECKS = [
    ("НЗ-2024-МС812-ИГДИ", 7, "п.8", 35837),      # ЛС-01 п.1.1
    ("НЗ-2024-МС812-ИГДИ", 11, "п.2", 58208),     # ЛС-01 п.1.2
    ("НЗ-2024-МС812-ИГДИ", 18, "п.15", 25899),    # ЛС-01 п.1.3
    ("НЗ-2024-МС812-ИГДИ", 16, "п.1", 1714),      # ЛС-01 п.2.1
    ("НЗ-2024-МС812-ИГДИ", 48, "п.17", 1013),     # ЛС-01 п.2.3 (a)
    ("НЗ-2025-МС281-ИГИ", 14, "п.2", 3237),       # ЛС-02 п.1.2
    ("НЗ-2025-МС281-ИГИ", 56, "п.1", 459),        # ЛС-02 п.2.1
    ("НЗ-2025-МС281-ИГИ", 66, "п.2", 51681),      # ЛС-02 п.4.1 (программа)
    ("СБЦ-2001-ГИДРОМЕТ", 69, "п.1", 201),        # ЛС-03 п.2.1
    ("СБЦ-2001-ГИДРОМЕТ", 64, "п.2", 1966),       # ЛС-03 п.2.3
    ("СБЦ-2001-ИГИ-ИЭИ", 91, "п.1", 535),         # ЛС-04 п.1.7 (полевые)
    ("СБЦ-2001-ИГИ-ИЭИ", 81, "п.1", 200),         # ЛС-04 п.3.7 (программа)
]


def main() -> None:
    from app.services.calculator import _pick_survey_row

    db = SessionLocal()
    total = 0
    for code, rows in COMPOSITION.items():
        book = (db.query(ReferenceBook)
                .filter(ReferenceBook.code == code, ReferenceBook.is_active.is_(True))
                .first())
        if not book:
            print(f"  ! книга {code} не найдена/неактивна — пропуск")
            continue
        # перезаливаем состав целиком: правки состава — через повторный запуск
        (db.query(BookCondition)
         .filter(BookCondition.book_version_id == book.id,
                 BookCondition.coeff_key.ilike("autoitem_%"))
         .delete(synchronize_session=False))
        missing = []
        for work_cat, table_num, row_num, volume, name in rows:
            row, _ = _pick_survey_row(db, book, table_num, row_num, work_cat, 2)
            if row is None:
                missing.append(f"т.{table_num} {row_num}")
                continue
            db.add(BookCondition(
                book_version_id=book.id,
                coeff_key=f"autoitem_{work_cat}",
                table_num=table_num,
                row_range=row_num,
                coeff_min=volume,
                condition_short=name,
                effect_type="multiplier_range",
            ))
            total += 1
        for param, value in BLOCK_PARAMS.get(code, {}).items():
            key = f"autoblock_{param}"
            (db.query(BookCondition)
             .filter(BookCondition.book_version_id == book.id,
                     BookCondition.coeff_key == key)
             .delete(synchronize_session=False))
            db.add(BookCondition(
                book_version_id=book.id, coeff_key=key, coeff_min=value,
                effect_type="multiplier_range",
                condition_short=f"Параметр блока изысканий по умолчанию: {param}={value}"))
        for kind, table_num, base_code, disc in COST_TABLES.get(code, []):
            for key, val, rng in ((f"{kind}_table", table_num, disc),
                                  (f"{kind}_base", base_code, None)):
                (db.query(BookCondition)
                 .filter(BookCondition.book_version_id == book.id,
                         BookCondition.coeff_key == key)
                 .delete(synchronize_session=False))
                db.add(BookCondition(
                    book_version_id=book.id, coeff_key=key, coeff_min=val,
                    row_range=rng, effect_type="multiplier_range",
                    condition_short=f"{kind}: {key}={val}"
                                    + (f" ({rng})" if rng else "")))
        db.flush()
        note = f" (не найдены: {', '.join(missing)})" if missing else ""
        print(f"  ✓ {code}: {len(rows) - len(missing)} позиций состава{note}")
    db.commit()

    for code, table_num, row_num, expected in SPOT_CHECKS:
        book = (db.query(ReferenceBook)
                .filter(ReferenceBook.code == code, ReferenceBook.is_active.is_(True))
                .first())
        if not book:
            continue
        work_cat = "kameral" if "кам" in row_num else "field"
        row, _ = _pick_survey_row(db, book, table_num, row_num, work_cat, 2)
        assert row is not None, f"spot-check: {code} т.{table_num} {row_num} не найдена"
        got = {float(row.a or 0), float(row.b or 0)}
        assert any(abs(g - expected) < 0.51 for g in got), \
            f"spot-check провален: {code} т.{table_num} {row_num} = {got}, эталон {expected}"
    print(f"Готово: {total} позиций типового состава, spot-check'и по эталону пройдены")
    db.close()


if __name__ == "__main__":
    main()

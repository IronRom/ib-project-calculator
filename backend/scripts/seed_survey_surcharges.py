"""Процентные надбавки изысканий (ДЗ / транспорт / орг-ликвидация / отчёт-%).

Конвенция (движок: calculator._survey_surcharge_items → igi_calculator
work_category='percent'):
    coeff_key  = 'surcharge_<slug>'
    coeff_min  = процент
    coeff_max  = номер таблицы книги (для обоснования)
    row_range  = база начисления: field | lab | kameral | field+percent
    condition_short = наименование позиции в смете

ИСТОЧНИКИ (проверены по первоисточникам, значения сверены с эталонной сметой
Инфостроя «Реконструкция ФГБУ СЛО Россия, 1-я Рейсовая» от 14.04.2026):

НЗ-2024-МС812-ИГДИ (приказ 812/пр):
  · п.28 табл.3 — ДЗвнеш: до 200 км, Сппз до 250 тыс.руб → 13,2 % от полевых
    (эталон ЛС-01 п.1.4: (134 389+218 280+32 374)×13,2 % = 50 826 руб)
  · п.19 табл.2 — ДЗнп: неблагоприятный период 6,0–6,9 мес → 29 % от полевых
    (эталон ЛС-01 п.1.5: ×29 % = 111 662 руб)

НЗ-2025-МС281-ИГИ (приказ 281/пр):
  · п.29 табл.4 — ДЗпроезд1 (состав без статического зондирования): до 200 км,
    Сппз до 300 тыс.руб → 19,7 % от полевых
    (эталон ЛС-02 п.1.3: (10 928+107 630)×19,7 % = 23 356 руб)
  · п.21 табл.3 — ДЗнп 6,0–6,9 мес → 29 % от полевых
    (эталон ЛС-02 п.1.4: ×29 % = 34 382 руб)

СБЦ-2001 (Справочник базовых цен на инженерные изыскания, общие указания):
  · п.9 табл.4 — внутренний транспорт: до 5 км, полевые до 5 тыс.руб → 8,75 %
  · п.13 — организация и ликвидация работ на объекте: 6 % от полевых,
    включая внутренний транспорт (база field+percent)
  · гидромет: п.17 табл.62 — техотчёт в % от камеральных: изученная
    территория, камеральные до 500 руб → 55 %
  · экология/геология: табл.87 — техотчёт в % от камеральных: II категория
    сложности, камеральные до 5 тыс.руб → 21 %

Значения — минимальные условия (ближний участок, малый объём): состав
автосборки условный, точные проценты пользователь правит во вкладке
«Изыскания». Запуск:
    docker exec <backend> sh -c "PYTHONPATH=/app python /app/scripts/seed_survey_surcharges.py"
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal              # noqa: E402
from app.models import BookCondition, ReferenceBook  # noqa: E402

# code → [(slug, pct, base, table_num, condition_short)] — порядок важен:
# организация/ликвидация считается от полевых + транспорт, поэтому идёт после
# транспорта и до процента отчёта.
SURCHARGES: dict[str, list[tuple[str, float, str, int, str]]] = {
    "НЗ-2024-МС812-ИГДИ": [
        ("transport", 13.2, "field", 3,
         "ДЗвнеш — внешний транспорт (НЗ-812 п.28 табл.3): до 200 км, "
         "Сппз до 250 тыс.руб — 13,2 % полевых"),
        ("unfavorable", 29.0, "field", 2,
         "ДЗнп — полевые работы в неблагоприятный период года "
         "(НЗ-812 п.19 табл.2): 6,0–6,9 мес — 29 % полевых"),
    ],
    "НЗ-2025-МС281-ИГИ": [
        ("proezd", 19.7, "field", 4,
         "ДЗпроезд1 — проезд (НЗ-281 п.29 табл.4, состав без статического "
         "зондирования): до 200 км, Сппз до 300 тыс.руб — 19,7 % полевых"),
        ("unfavorable", 29.0, "field", 3,
         "ДЗнп — полевые работы в неблагоприятный период года "
         "(НЗ-281 п.21 табл.3): 6,0–6,9 мес — 29 % полевых"),
    ],
    "СБЦ-2001-ГИДРОМЕТ": [
        ("transport", 8.75, "field", 4,
         "Расходы по внутреннему транспорту (СБЦ-2001 общие указания п.9 "
         "табл.4): до 5 км, полевые до 5 тыс.руб — 8,75 %"),
        ("orgliq", 6.0, "field+percent", 0,
         "Расходы по организации и ликвидации работ на объекте "
         "(СБЦ-2001 общие указания п.13) — 6 % полевых с транспортом"),
        ("report", 55.0, "kameral", 62,
         "Составление технического отчёта (СБЦ-2001 гидромет п.17 табл.62): "
         "изученная территория, камеральные до 500 руб — 55 % камеральных"),
    ],
    "СБЦ-2001-ИГИ-ИЭИ": [
        ("transport", 8.75, "field", 4,
         "Расходы по внутреннему транспорту (СБЦ-2001 общие указания п.9 "
         "табл.4): до 5 км, полевые до 5 тыс.руб — 8,75 %"),
        ("orgliq", 6.0, "field+percent", 0,
         "Расходы по организации и ликвидации работ на объекте "
         "(СБЦ-2001 общие указания п.13) — 6 % полевых с транспортом"),
        ("report", 21.0, "kameral", 87,
         "Составление технического отчёта (СБЦ-2001 табл.87): II категория "
         "сложности, камеральные до 5 тыс.руб — 21 % камеральных"),
    ],
}


def main() -> None:
    db = SessionLocal()
    total = 0
    for code, rows in SURCHARGES.items():
        book = (db.query(ReferenceBook)
                .filter(ReferenceBook.code == code, ReferenceBook.is_active.is_(True))
                .first())
        if not book:
            print(f"  ! книга {code} не найдена/неактивна — пропуск")
            continue
        for slug, pct, base, table_num, short in rows:
            key = f"surcharge_{slug}"
            rec = (db.query(BookCondition)
                   .filter(BookCondition.book_version_id == book.id,
                           BookCondition.coeff_key == key)
                   .first())
            if rec is None:
                rec = BookCondition(book_version_id=book.id, coeff_key=key)
                db.add(rec)
            rec.condition_short = short
            rec.effect_type = "multiplier_range"
            rec.coeff_min = pct
            rec.coeff_max = table_num or None
            rec.row_range = base
            rec.table_num = None
            total += 1
        print(f"  ✓ {code}: {len(rows)} надбавок")
    db.commit()

    # ── spot-check: проценты, подтверждённые эталоном ─────────────────────────
    checks = [
        ("НЗ-2024-МС812-ИГДИ", "surcharge_transport", 13.2),
        ("НЗ-2024-МС812-ИГДИ", "surcharge_unfavorable", 29.0),
        ("НЗ-2025-МС281-ИГИ", "surcharge_proezd", 19.7),
        ("НЗ-2025-МС281-ИГИ", "surcharge_unfavorable", 29.0),
        ("СБЦ-2001-ГИДРОМЕТ", "surcharge_orgliq", 6.0),
        ("СБЦ-2001-ИГИ-ИЭИ", "surcharge_transport", 8.75),
    ]
    for code, key, expected in checks:
        book = (db.query(ReferenceBook)
                .filter(ReferenceBook.code == code, ReferenceBook.is_active.is_(True))
                .first())
        if not book:
            continue
        rec = (db.query(BookCondition)
               .filter(BookCondition.book_version_id == book.id,
                       BookCondition.coeff_key == key)
               .first())
        assert rec is not None and abs(float(rec.coeff_min) - expected) < 1e-6, \
            f"spot-check провален: {code}/{key} ожидалось {expected}"
    print(f"Готово: {total} условий, spot-check'и пройдены")
    db.close()


if __name__ == "__main__":
    main()

"""Seed book_conditions for СБЦП 81-2001-17.

Run inside the backend container:
  docker exec ib-project-calculator-backend-1 python3 -m app.scripts.seed_sbts_conditions

Idempotent: deletes and re-inserts conditions for the target book.
"""
from decimal import Decimal
from app.database import SessionLocal
from app.models import BookCondition, ReferenceBook

# ---------------------------------------------------------------------------
# Condition data: (table_num, row_range, condition_short, effect_type, coeff_min, coeff_max, coeff_key)
# table_num=None → book-wide (general) condition
# ---------------------------------------------------------------------------
CONDITIONS = [
    # ─── ОБЩИЕ (book-wide) ──────────────────────────────────────────────────
    (None, None, "Масштаб геодезических планов 1:500 или 1:200 (к разделу ИГИ)", "multiplier_range", 1.1, 1.2, None),
    (None, None, "Территория проектирования в горной местности", "multiplier_range", 1.2, 1.3, None),
    (None, None, "Объект в городе с населением > 500 тыс. чел. (столица)", "multiplier_range", 1.1, 1.2, None),
    (None, None, "Необходимость разработки раздела ОВОС / экологической экспертизы", "multiplier_range", 1.1, 1.15, None),
    (None, None, "Применение неметаллических (полимерных) труб при отсутствии аналогов", "multiplier_range", 1.05, 1.1, None),
    (None, None, "Территория со сложными инженерно-геологическими условиями (просадочность, набухание, карст)", "multiplier_range", 1.1, 1.2, None),
    (None, None, "Сейсмика 7-8 баллов МСК", "multiplier_range", 1.1, 1.15, "seismic"),
    (None, None, "Сейсмика 9 баллов МСК и выше", "multiplier_range", 1.15, 1.25, "seismic"),
    (None, None, "Реконструкция (общий коэффициент реконструкции)", "multiplier_range", 1.1, 1.3, "reconstruction"),
    (None, None, "Капитальный ремонт (общий коэффициент)", "multiplier_range", 1.05, 1.15, "overhaul"),
    (None, None, "Сброс в водоём рыбохозяйственного значения I-II категории", "multiplier_range", 1.05, 1.1, "fishery"),
    (None, None, "Разработка специальных технических условий (СТУ)", "multiplier_range", 1.1, 1.2, None),
    (None, None, "Стадия П (проектная документация)", "flag", 0.6, 0.6, None),
    (None, None, "Стадия Р (рабочая документация)", "flag", 0.4, 0.4, None),
    (None, None, "Стадия П+Р (проектная + рабочая документация)", "flag", 1.0, 1.0, None),

    # ─── ТАБЛИЦА 1: НС I-го подъёма (поверхностный водозабор) ───────────────
    (1, None, "Микропроцессорные контроллеры / АСУ / АСДКУ", "multiplier_range", 1.04, 1.06, "asu"),
    (1, None, "Подача воды из нескольких разнородных источников (2 и более)", "multiplier_range", 1.1, 1.15, None),
    (1, None, "Забор воды в условиях значительных колебаний уровня (>5 м)", "multiplier_range", 1.1, 1.15, None),
    (1, None, "Плавучий водозаборный ковш / понтонный водозабор", "multiplier_range", 1.1, 1.2, None),
    (1, None, "Насосная станция в подземном исполнении (заглубление > 10 м)", "multiplier_range", 1.1, 1.2, "deepening"),
    (1, None, "Насосная станция совмещённого типа (со встроенными очистными узлами)", "multiplier_range", 1.1, 1.15, None),
    (1, None, "Реконструкция НС I-го подъёма", "multiplier_range", 1.15, 1.25, "reconstruction"),
    (1, None, "Перекачка агрессивных вод (коррозионные среды)", "multiplier_range", 1.1, 1.15, None),
    (1, None, "Регулируемый электропривод (частотные преобразователи)", "multiplier_range", 1.07, 1.12, None),

    # ─── ТАБЛИЦА 2: Водозаборы из подземных источников ──────────────────────
    (2, None, "Скважины в сложных гидрогеологических условиях (напорные горизонты, плывуны)", "multiplier_range", 1.1, 1.2, None),
    (2, None, "Необходимость испытания скважин (откачка, восстановление уровня)", "multiplier_range", 1.05, 1.1, None),

    # ─── ТАБЛИЦА 3: Водоводы ─────────────────────────────────────────────────
    (3, None, "Прокладка в горной местности или по крутым склонам", "multiplier_range", 1.15, 1.25, None),
    (3, None, "Прокладка в условиях плотной городской застройки (стеснённые условия)", "multiplier_range", 1.1, 1.2, None),
    (3, None, "Пересечение автодорог I-II категории, железных дорог (≥ 2 пересечения)", "multiplier_range", 1.1, 1.15, None),
    (3, None, "Прокладка методом ГНБ (горизонтальное направленное бурение)", "multiplier_range", 1.3, 1.5, None),
    (3, None, "Прокладка в скальных грунтах (категория V и выше)", "multiplier_range", 1.15, 1.25, None),
    (3, None, "Заглубление трубопровода > 3 м от поверхности", "multiplier_range", 1.1, 1.15, None),
    (3, None, "Пересечение водных преград (дюкер, надводный переход) — суммарно > 3", "multiplier_range", 1.1, 1.2, None),
    (3, "п.22-24", "Камеры переключения (к позициям камер)", "multiplier_range", 1.0, 1.0, None),
    (3, None, "Трубопровод из нержавеющей стали или сплавов (нетипичный материал)", "multiplier_range", 1.1, 1.15, None),
    (3, None, "Реконструкция водовода с частичной заменой труб", "multiplier_range", 1.15, 1.25, "reconstruction"),
    (3, None, "Микропроцессорные контроллеры / телеметрия / АСУ на водоводе", "multiplier_range", 1.04, 1.06, "asu"),
    (3, None, "Протяжённость одной нитки > 30 км", "multiplier_range", 1.05, 1.1, None),

    # ─── ТАБЛИЦА 4: Водопроводные ОС (хлораторные, озонирование, УФ и др.) ──
    (4, None, "Многоступенчатая очистка (более 2 ступеней обработки)", "multiplier_range", 1.1, 1.2, None),
    (4, None, "Применение озонирования или УФ-обеззараживания", "multiplier_range", 1.1, 1.15, None),
    (4, None, "Микропроцессорные контроллеры / АСУ", "multiplier_range", 1.04, 1.06, "asu"),
    (4, None, "Обезжелезивание, деманганация, умягчение (дополнительные процессы)", "multiplier_range", 1.1, 1.15, None),
    (4, None, "Реконструкция водопроводных ОС", "multiplier_range", 1.15, 1.25, "reconstruction"),
    (4, None, "Заглубление основных сооружений > 10 м", "multiplier_range", 1.1, 1.2, "deepening"),
    (4, None, "Применение реагентов повышенной опасности (жидкий хлор)", "multiplier_range", 1.05, 1.1, None),
    (4, None, "Разработка специальных мер защиты водоёма рыбохозяйственного значения", "multiplier_range", 1.05, 1.1, "fishery"),

    # ─── ТАБЛИЦА 5: НС II-го подъёма (п.1-9) и Резервуары (п.10+) ───────────
    (5, "п.1-9", "Микропроцессорные контроллеры / АСУ / АСДКУ (к НС II)", "multiplier_range", 1.09, 1.11, "asu"),
    (5, "п.1-9", "Регулируемый электропривод на НС II-го подъёма", "multiplier_range", 1.07, 1.12, None),
    (5, "п.1-9", "Заглубление НС II-го подъёма > 10 м", "multiplier_range", 1.1, 1.2, "deepening"),
    (5, "п.1-9", "Реконструкция НС II-го подъёма", "multiplier_range", 1.15, 1.25, "reconstruction"),
    (5, "п.1-9", "Подача в несколько разнородных зон давления", "multiplier_range", 1.1, 1.15, None),
    (5, "п.10+", "Реконструкция резервуаров чистой воды (РЧВ)", "multiplier_range", 1.1, 1.2, "reconstruction"),
    (5, "п.10+", "Устройство антикоррозионного покрытия внутри РЧВ (нетиповое)", "multiplier_range", 1.05, 1.1, None),

    # ─── ТАБЛИЦА 6 ───────────────────────────────────────────────────────────
    (6, None, "Строительство водонапорных башен нетиповых конструкций", "multiplier_range", 1.1, 1.2, None),
    (6, None, "Реконструкция водонапорных башен", "multiplier_range", 1.1, 1.2, "reconstruction"),

    # ─── ТАБЛИЦА 8: Коллекторы канализационные (+ ГНБ п.13+) ────────────────
    (8, "п.1-12", "Прокладка в скальных грунтах (категория V и выше)", "multiplier_range", 1.15, 1.25, None),
    (8, "п.1-12", "Прокладка в стеснённых условиях городской застройки", "multiplier_range", 1.1, 1.2, None),
    (8, "п.1-12", "Заглубление коллектора > 6 м", "multiplier_range", 1.1, 1.2, None),
    (8, "п.1-12", "Пересечение автодорог I-II категории или ж/д путей (≥ 2)", "multiplier_range", 1.1, 1.15, None),
    (8, "п.1-12", "Дюкеры, переходы через водные преграды", "multiplier_range", 1.1, 1.2, None),
    (8, "п.13+", "Прокладка методом ГНБ в сложных грунтах (суглинок, скала)", "multiplier_range", 1.15, 1.25, None),
    (8, "п.1-12", "Реконструкция канализационных коллекторов", "multiplier_range", 1.15, 1.25, "reconstruction"),
    (8, "п.1-12", "Применение нетиповых материалов труб (базальт, ВЧШГ)", "multiplier_range", 1.05, 1.1, None),
    (8, "п.1-12", "Телеинспекция коллектора в составе ПД", "multiplier_range", 1.05, 1.1, None),
    (8, "п.1-12", "Микропроцессорные контроллеры / телеметрия на сети КНС-коллектор", "multiplier_range", 1.04, 1.06, "asu"),
    (8, "п.1-12", "Территория проектирования в горной местности", "multiplier_range", 1.15, 1.25, None),

    # ─── ТАБЛИЦА 9: КНС ──────────────────────────────────────────────────────
    (9, None, "Глубина подводящего коллектора более 4 м (каждые 1,5 м)", "multiplier_range", 1.1, 1.15, None),
    (9, None, "КНС опускным способом (кессонный метод)", "multiplier_range", 1.2, 1.25, None),
    (9, None, "Перекачка агрессивных сточных вод", "multiplier_range", 1.2, 1.25, None),
    (9, None, "Перекачка взрывоопасных сточных вод", "multiplier_range", 1.1, 1.15, None),
    (9, None, "Микропроцессорные контроллеры / АСУ / АСДКУ", "multiplier_range", 1.18, 1.2, "asu"),
    (9, None, "Регулируемый электропривод насосов [п.3-7]", "multiplier_range", 1.14, 1.2, None),

    # ─── ТАБЛИЦА 10: ОС (очистка сточных вод) ───────────────────────────────
    (10, None, "Сброс в водоём рыбохозяйственного значения I кат. (нормы ПДК — рыбохоз.)", "multiplier_range", 1.1, 1.15, "fishery"),
    (10, None, "Глубокое доочищение (доп. ступень: мембраны, озон, УФ)", "multiplier_range", 1.1, 1.2, None),
    (10, None, "Физико-химическая очистка (вместо биологической / в дополнение)", "multiplier_range", 1.1, 1.15, None),
    (10, None, "Микропроцессорные контроллеры / АСУ на КОС", "multiplier_range", 1.04, 1.08, "asu"),
    (10, None, "Реконструкция КОС (действующие сооружения)", "multiplier_range", 1.15, 1.3, "reconstruction"),
    (10, None, "Заглубление подземных сооружений КОС > 10 м", "multiplier_range", 1.1, 1.2, "deepening"),
    (10, None, "Раздельная канализация (ливневые + хозфекальные стоки в одном проекте)", "multiplier_range", 1.1, 1.15, None),
    (10, None, "Более 3 очередей строительства / секций", "multiplier_range", 1.05, 1.1, None),
    (10, None, "Биологическая очистка с удалением азота и фосфора (нутриенты)", "multiplier_range", 1.05, 1.1, None),
    (10, None, "Обеззараживание ультрафиолетом (УФ-установки)", "multiplier_range", 1.05, 1.1, None),
    (10, None, "Рекультивация иловых площадок в составе проекта", "multiplier_range", 1.05, 1.1, None),

    # ─── ТАБЛИЦА 11: Обработка осадка ────────────────────────────────────────
    (11, None, "Термическая сушка осадка (высокотемпературные процессы)", "multiplier_range", 1.1, 1.2, None),
]


def seed(book_code: str = "81-2001-17") -> None:
    db = SessionLocal()
    try:
        book = (
            db.query(ReferenceBook)
            .filter(ReferenceBook.is_active == True)
            .filter(ReferenceBook.code.ilike(f"%{book_code}%"))
            .first()
        )
        if not book:
            print(f"Active book with code '{book_code}' not found.")
            return

        print(f"Seeding conditions for: {book.code} (id={book.id})")

        deleted = db.query(BookCondition).filter(BookCondition.book_version_id == book.id).delete()
        print(f"  Deleted {deleted} existing conditions")

        for row in CONDITIONS:
            table_num, row_range, condition_short, effect_type, c_min, c_max, coeff_key = row
            db.add(BookCondition(
                book_version_id=book.id,
                table_num=table_num,
                row_range=row_range,
                condition_short=condition_short,
                effect_type=effect_type,
                coeff_min=Decimal(str(c_min)) if c_min is not None else None,
                coeff_max=Decimal(str(c_max)) if c_max is not None else None,
                coeff_key=coeff_key,
            ))

        db.commit()
        print(f"  Inserted {len(CONDITIONS)} conditions.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

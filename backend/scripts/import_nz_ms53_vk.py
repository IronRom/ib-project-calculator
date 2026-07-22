"""
Import НЗ-2025-МС53-ВК (Приказ Минстроя № 53/пр от 03.02.2025)
«Нормативные затраты на проектирование объектов водоснабжения, водоотведения и водоочистки»

Key details:
- Base year: 01.01.2024, values stored in тыс.руб AS-IS (system convention:
  reference_rows хранит тыс.руб, calculate() умножает на 1000)
- Tables named 3.1 – 3.17 → store table_num as integer (3.14 → 14)
- ПД=40%, РД=60% (same as our STAGE_SPLITS system)
- Standard a+b×X formula
"""
import sys
sys.path.insert(0, '/app')

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from app.database import SessionLocal
from app.models import ReferenceBook, ReferenceRow, BookObjectType
from app.services.reference_parser import parse_reference_pdf, rebuild_object_types

PDF_PATH = '/app/scripts/nz_ms53_vk_2025.pdf'
BOOK_CODE = 'НЗ-2025-МС53-ВК'
BOOK_NAME = 'Нормативные затраты на работы по подготовке проектной документации для строительства, реконструкции и капитального ремонта объектов водоснабжения, водоотведения и водоочистки. Приказ Минстроя России от 03.02.2025 № 53/пр'
BASE_YEAR = 2024

CUSTOM_PROMPT = """Ты извлекаешь данные из страницы НЗ (Нормативных затрат) на проектирование объектов водоснабжения, водоотведения и водоочистки. Приказ Минстроя РФ № 53/пр от 03.02.2025.

СТРУКТУРА ДОКУМЕНТА:
- Главы I и II — методология (текст). Строк с ценами НЕТ → rows: []
- Глава III — таблицы с параметрами цен: Таблица 3.1 ... Таблица 3.17
- Подтаблицы (3.1.1, 3.2.1 и т.п.) — коэффициенты, НЕ строки с a и b → rows: []
- Приложение — таблицы относительной стоимости разделов → rows: []

НОМЕР ТАБЛИЦЫ:
- "Таблица 3.14" → table_num: 14
- "Таблица 3.1" → table_num: 1
- "Таблица 3.17" → table_num: 17
- Продолжение таблицы 3.X → table_num: X (целое число после точки)
- Подтаблицы 3.X.Y → ПРОПУСТИ (верни rows: [])

ФОРМАТ СТРОК (только для основных таблиц 3.1–3.17):
- Колонка 1: № п/п (число)
- Колонка 2: Наименование объекта
- Колонка 3: Натуральный показатель «Х» (единица измерения)
- Колонка 4: Границы интервалов натурального показателя (от X до Y)
- Колонка 5: параметр «a» (тыс. руб.)
- Колонка 6: параметр «b» (тыс. руб.)

Верни JSON строго в формате:
{
  "table_num": <целое число X из "Таблица 3.X", или null>,
  "official_name": "<название НЗ если видно на первой странице, иначе null>",
  "rows": [
    {
      "row_num": "п.1",
      "description": "Полное описание объекта с диапазоном X",
      "x_min": <число или null>,
      "x_max": <число или null>,
      "x_unit": "тысяч кубических метров / час",
      "a": <число или null>,
      "b": <число или null>
    }
  ]
}

ПРАВИЛА row_num:
- Берётся из колонки 1 с префиксом "п.": 1 → "п.1", 6 → "п.6"
- Подпункты: 1.1 → "п.1.1", 6.1 → "п.6.1"

ПРАВИЛА description:
- Полное описание включая тип объекта И диапазон из колонки 4
- Для строк-продолжений (тот же объект, следующий интервал) — повтори название объекта
- Пример: "Водозаборное сооружение ковшовое производительностью тыс.куб.м/час: от 1 до 4 включительно"

ПРАВИЛА x_min/x_max (из колонки 4):
- "от 0,1 до 1 включительно" → x_min=0.1, x_max=1
- "от 1 до 4 включительно" → x_min=1, x_max=4
- "свыше 25 до 50" → x_min=25, x_max=50
- "до 2000 включительно" → x_min=null, x_max=2000
- "свыше 3050" → x_min=3050, x_max=null
- Запятые в числах → точки: 0,1 → 0.1

ПРАВИЛА a и b:
- Значения в тыс.руб — возвращай КАК ЕСТЬ (без умножения)
- ВНИМАНИЕ К ДЕСЯТИЧНЫМ ЗАПЯТЫМ: запятая — десятичный разделитель, пробел — разделитель тысяч.
  "3 757,979" → 3757.979;  "580,61" → 580.61 (НЕ 58061 и НЕ 580610);  "65,69" → 65.69
  Параметр «б» почти всегда МЕНЬШЕ параметра «а» той же строки — если получилось наоборот
  на порядки, перепроверь позицию запятой.
- Прочерк или пусто → null

Если на странице нет таблиц 3.1–3.17 с параметрами a и b → rows: [].
Верни ТОЛЬКО JSON, без markdown и пояснений."""


def run():
    db = SessionLocal()
    try:
        # Reuse existing book record (keeps id → hints/conditions/pd_pct survive);
        # only rows and object types are wiped and re-imported.
        book = db.query(ReferenceBook).filter(ReferenceBook.code == BOOK_CODE).first()
        if book:
            logger.info(f"Reusing existing {BOOK_CODE} id={book.id} — clearing rows/types")
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).update({'object_type_id': None})
            db.flush()
            db.query(BookObjectType).filter(BookObjectType.book_version_id == book.id).delete()
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).delete()
            book.parse_prompt = CUSTOM_PROMPT
            book.pdf_path = PDF_PATH
            book.price_base_year = BASE_YEAR
            db.commit()
        else:
            book = ReferenceBook(
                code=BOOK_CODE,
                official_name=BOOK_NAME,
                version=1,
                status='requires_validation',
                is_active=False,
                price_base_year=BASE_YEAR,
                parse_prompt=CUSTOM_PROMPT,
                pdf_path=PDF_PATH,
            )
            db.add(book)
            db.commit()
            db.refresh(book)
            logger.info(f"Created book id={book.id}")

        logger.info("Parsing PDF (52 pages)...")
        def on_progress(page, total, msg):
            if page % 5 == 0 or page == total:
                logger.info(f"  {msg}")

        rows, official_name = parse_reference_pdf(PDF_PATH, CUSTOM_PROMPT, on_progress=on_progress)
        logger.info(f"Parsed {len(rows)} rows")

        if official_name:
            book.official_name = official_name
            db.add(book)

        inserted = skipped = 0
        for r in rows:
            a_raw = r.get('a')
            b_raw = r.get('b')
            if a_raw is None and b_raw is None:
                skipped += 1
                continue
            row = ReferenceRow(
                book_version_id=book.id,
                table_num=r['table_num'],
                row_num=r.get('row_num'),
                description=r.get('description'),
                x_min=r.get('x_min'),
                x_max=r.get('x_max'),
                x_unit=r.get('x_unit'),
                a=float(a_raw) if a_raw is not None else None,   # тыс.руб as-is
                b=float(b_raw) if b_raw is not None else None,   # тыс.руб as-is
                notes=r.get('notes'),
            )
            db.add(row)
            inserted += 1

        db.commit()
        logger.info(f"Inserted {inserted} rows, skipped {skipped}")

        # Null out before rebuild (safe pattern)
        db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).update({'object_type_id': None})
        db.flush()
        n_types = rebuild_object_types(db, book.id)
        logger.info(f"Rebuilt {n_types} object types")

        # Activate
        book.is_active = True
        book.status = 'consistent'
        db.add(book)
        db.commit()
        logger.info(f"Book {BOOK_CODE} id={book.id} activated.")

        # Spot-check Кашин rows
        logger.info("\n--- Spot-check Кашин rows ---")
        # НЗ-2024-МС53-ВК-3.17-006: АБК м³ от 3000 до 6000 → table=17, row=п.6
        # expected from Кашин (тыс.руб): a=365, b=1.014
        # НЗ-2024-МС53-ВК-3.14-001: резервуар м³ от 30 до 2000 → table=14, row=п.1
        # expected from Кашин (тыс.руб): a=137.2, b=0.323
        checks = [
            (17, 'п.6', 365.0, 1.014, 'АБК 3000-6000 м³'),
            (14, 'п.1', 137.2, 0.323, 'Резервуар 30-2000 м³'),
        ]
        all_ok = True
        for tnum, rnum, exp_a, exp_b, label in checks:
            r = db.query(ReferenceRow).filter_by(
                book_version_id=book.id, table_num=tnum, row_num=rnum
            ).first()
            if not r:
                logger.warning(f"  NOT FOUND: Table {tnum} {rnum} ({label})")
                all_ok = False
                # Show what's in that table
                rows_t = db.query(ReferenceRow).filter_by(book_version_id=book.id, table_num=tnum).all()
                logger.info(f"    Table {tnum} has {len(rows_t)} rows: {[x.row_num for x in rows_t[:10]]}")
                continue
            a_ok = r.a is not None and abs(float(r.a) - exp_a) < 0.1
            b_ok = r.b is not None and abs(float(r.b) - exp_b) < 0.001
            status = 'OK' if (a_ok and b_ok) else 'MISMATCH'
            logger.info(f"  {status} Table {tnum} {rnum} ({label}): a={r.a} b={r.b} | expected a≈{exp_a} b≈{exp_b}")
            if status != 'OK':
                all_ok = False

        logger.info('\nALL OK' if all_ok else 'SOME CHECKS FAILED')

    finally:
        db.close()


if __name__ == '__main__':
    run()

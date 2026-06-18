"""
Import СБЦ "Объекты промышленности химических волокон. 2004 г." into reference_books.

Key differences from standard СБЦП:
- Values are in тыс.руб → multiply by 1000 on import
- Table 3 uses decimal row numbering: 1.1, 1.89, 2.10б, 3.1 etc.
- Each position has 3 sub-rows (П/Р/РП) — we store ONCE per position
- Tables 6-7 have fixed prices (no a+b*X) — skip or store with b=0
"""
import sys
sys.path.insert(0, '/app')

import json
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from app.database import SessionLocal
from app.models import ReferenceBook, ReferenceRow
from app.services.reference_parser import parse_reference_pdf, rebuild_object_types

PDF_PATH = '/app/scripts/sbc_khimvolokna_2004.pdf'
BOOK_CODE = 'СБЦ-ХимВолокна-2004'
BOOK_NAME = 'Справочник базовых цен на проектные работы для строительства. Объекты промышленности химических волокон. 2004 г.'
BASE_YEAR = 2001  # prices as of 01.01.2001

CUSTOM_PROMPT = """Ты извлекаешь данные из страницы «Справочника базовых цен на проектные работы для строительства. Объекты промышленности химических волокон. 2004 г.»

СТРУКТУРА СПРАВОЧНИКА:
- Таблицы 1, 2, 4, 5: простая нумерация строк (1, 2, 3...)
- Таблица 3: десятичная нумерация (1.1, 1.2, ..., 1.89, 1.90, ..., 2.1, 2.4, 2.10, 2.10б, 3.1 и т.д.)
  Секции в таблице 3: раздел «1 Здания и сооружения», «2 Внутриплощадочные инженерные сети», «3 Общеплощадочные решения»
- Таблицы 6-7: фиксированные цены без a и b — ПРОПУСТИ (верни rows: [])
- Таблица 8: если есть — ПРОПУСТИ

ОСОБЕННОСТИ СТРОК:
Каждая позиция имеет ТРИ подстроки для стадий: П (Проект), Р (Рабочая документация), РП (Рабочий проект).
Значения a и b ОДИНАКОВЫ для всех трёх подстрок — они указаны в объединённой ячейке левее.
Правее идут проценты разделов — НЕ НУЖНЫ для извлечения.
ВАЖНО: для каждой позиции извлекай ОДНУ строку (не три), используя значения a и b из объединённой ячейки.

ЧИСЛА: значения a и b указаны в тыс.руб. Возвращай их как есть (без умножения).
Запятые в числах заменяй на точки: 1,455 → 1.455; 394,26 → 394.26

Верни JSON строго в формате:
{
  "table_num": <номер таблицы целым числом, или null если таблица не началась>,
  "official_name": "<название документа если видно на первой странице, иначе null>",
  "rows": [
    {
      "row_num": "п.7",
      "description": "Полное описание позиции с диапазоном X",
      "x_min": <число или null>,
      "x_max": <число или null>,
      "x_unit": "м³/сут",
      "a": <число или null>,
      "b": <число или null>
    }
  ]
}

ПРАВИЛА row_num:
- Берётся из колонки 1 с префиксом "п.": число 7 → "п.7", число 1.89 → "п.1.89", "2.10б" → "п.2.10б"
- Для под-строк (б), (в): 2.10а → "п.2.10а", 2.10б → "п.2.10б"
- Для заголовков разделов («1 Здания и сооружения», «2 Внутриплощадочные инженерные сети» и т.д.) — НЕ создавай строку
- НИКОГДА не нумеруй строки самостоятельно — только из документа

ПРАВИЛА description:
- Полное описание включая тип объекта И диапазон X
- Пример: "Локальные очистные сооружения ТЭС производительностью м³/сут: от 100 до 200"
- Для строк-продолжений («То же, свыше 42 до 84») — добавляй название из предыдущей строки

ПРАВИЛА x_min/x_max:
- «до 200» → x_min=null, x_max=200
- «от 100 до 200» → x_min=100, x_max=200
- «свыше 42 до 84» → x_min=42, x_max=84
- «свыше 100» → x_min=100, x_max=null
- Если нет диапазона (одно значение) → x_min=null, x_max=<это значение>

ПРАВИЛА a и b:
- Если в колонке a стоит прочерк (—) или пусто → a=null
- Если в колонке b стоит прочерк (—) или пусто → b=null
- Для строк подраздела 2.10 (Электрокабельные сети) с вариантами а/б/в: a=null, b из соответствующей колонки

Если на странице нет таблиц с ценами — верни "rows": [].
Если таблица продолжается — table_num равен номеру продолжающейся таблицы.

Верни ТОЛЬКО JSON, без markdown и пояснений."""


def run():
    db = SessionLocal()
    try:
        # Check if already exists
        existing = db.query(ReferenceBook).filter(ReferenceBook.code == BOOK_CODE).first()
        if existing:
            logger.info(f"Book {BOOK_CODE} already exists (id={existing.id}), deleting rows and re-importing")
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == existing.id).delete()
            db.delete(existing)
            db.commit()

        # Create book record
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

        # Parse PDF
        logger.info("Parsing PDF (73 pages, ~15 min)...")
        def on_progress(page, total, msg):
            if page % 5 == 0 or page == total:
                logger.info(f"  {msg}")

        rows, official_name = parse_reference_pdf(PDF_PATH, CUSTOM_PROMPT, on_progress=on_progress)
        logger.info(f"Parsed {len(rows)} rows from PDF")

        if official_name:
            book.official_name = official_name
            db.add(book)

        # Insert rows — multiply a,b by 1000 (тыс.руб → руб)
        inserted = 0
        skipped = 0
        for r in rows:
            a_raw = r.get('a')
            b_raw = r.get('b')
            # Skip rows with no pricing data at all
            if a_raw is None and b_raw is None:
                skipped += 1
                continue
            a_val = float(a_raw) * 1000 if a_raw is not None else None
            b_val = float(b_raw) * 1000 if b_raw is not None else None

            row = ReferenceRow(
                book_version_id=book.id,
                table_num=r['table_num'],
                row_num=r.get('row_num'),
                description=r.get('description'),
                x_min=r.get('x_min'),
                x_max=r.get('x_max'),
                x_unit=r.get('x_unit'),
                a=a_val,
                b=b_val,
                notes=r.get('notes'),
            )
            db.add(row)
            inserted += 1

        db.commit()
        logger.info(f"Inserted {inserted} rows, skipped {skipped}")

        # Rebuild object types
        n_types = rebuild_object_types(db, book.id)
        logger.info(f"Rebuilt {n_types} object types")

        # Activate
        # Deactivate other books with same code (none expected, but safe)
        db.query(ReferenceBook).filter(
            ReferenceBook.code == BOOK_CODE,
            ReferenceBook.id != book.id,
            ReferenceBook.is_active == True,
        ).update({'is_active': False})
        book.is_active = True
        book.status = 'consistent'
        db.add(book)
        db.commit()
        logger.info(f"Book {BOOK_CODE} id={book.id} activated. Done.")

        # Spot-check key rows from Кашин
        logger.info("\n--- Spot-check Кашин rows ---")
        checks = [
            (4, 'п.7', 'a=1626000, b=1455'),
            (3, 'п.1.89', 'a=198000, b=75000'),
            (3, 'п.2.4', 'a=406200, b=43800'),
            (3, 'п.2.10б', 'a=null, b=394260'),
            (3, 'п.3.1', 'a=null, b=28125'),
        ]
        for tnum, rnum, expected in checks:
            row = db.query(ReferenceRow).filter(
                ReferenceRow.book_version_id == book.id,
                ReferenceRow.table_num == tnum,
                ReferenceRow.row_num == rnum,
            ).first()
            if row:
                logger.info(f"  Table {tnum} {rnum}: a={row.a}, b={row.b} | expected {expected}")
            else:
                logger.warning(f"  Table {tnum} {rnum}: NOT FOUND (expected {expected})")

    finally:
        db.close()


if __name__ == '__main__':
    run()

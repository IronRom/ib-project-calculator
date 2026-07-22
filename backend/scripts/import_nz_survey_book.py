"""Universal importer for НЗ survey books (изыскания): ИГДИ, ИГФИ и будущие.

Convention for survey books (matches НЗ-281-ИГИ / igi_calculator):
- prices stored in RUBLES as-is (NOT тыс.руб — survey engine does not ×1000)
- price_base_year from приказ (01.01.2024 → 2024)
- calc_method='survey' — main calculate() must NOT price these books

Usage (inside container):
  PYTHONPATH=/app python /app/scripts/import_nz_survey_book.py igdi
  PYTHONPATH=/app python /app/scripts/import_nz_survey_book.py igfi
"""
import sys

sys.path.insert(0, '/app')

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

from app.database import SessionLocal
from app.models import BookObjectType, ReferenceBook, ReferenceRow
from app.services.reference_parser import parse_reference_pdf, rebuild_object_types

BOOKS = {
    "igdi": dict(
        code="НЗ-2024-МС812-ИГДИ",
        name=(
            "Нормативные затраты на работы по инженерно-геодезическим изысканиям. "
            "Приказ Минстроя России от 02.12.2024 № 812/пр"
        ),
        pdf="/tmp/igdi.pdf",
        base_year=2024,
    ),
    "igfi": dict(
        code="НЗ-2025-МС282-ИГФИ",
        name=(
            "Нормативные затраты на работы по инженерно-геофизическим изысканиям. "
            "Приказ Минстроя России от 12.05.2025 № 282/пр"
        ),
        pdf="/tmp/igfi.pdf",
        base_year=2024,
    ),
}

SURVEY_PROMPT = """Ты извлекаешь данные из страницы НЗ (Нормативных затрат) Минстроя на инженерные изыскания.

СТРУКТУРА ДОКУМЕНТА:
- Главы I–II — общие положения и порядок определения стоимости (текст, формулы) → rows: []
- Главы III и далее — таблицы с показателями затрат (ПЗ, ПЗп, ПЗк, ПЗ1, ПЗ2)
- Таблицы 1, 2 в общих положениях (коэффициенты К1/К2, проценты неблагоприятного периода) → rows: []

НОМЕР ТАБЛИЦЫ:
- "Таблица 5" → table_num: 5 (целое число). Продолжение таблицы — тот же номер.
- Если таблица не пронумерована или это коэффициенты — rows: []

ФОРМАТ СТРОК ТАБЛИЦ ПОКАЗАТЕЛЕЙ ЗАТРАТ:
- row_num — из колонки № п/п: "п." + число ("п.3"). НИКОГДА не нумеруй сам.
- description — ПОЛНОЕ описание: вид работы, категория сложности, масштаб/сечение рельефа,
  диапазон. Если строка — продолжение группы (только категория или диапазон), добавь
  название вида работ из первой строки группы.
- x_min/x_max — из диапазонов ("от X до Y", "до X", "свыше X"). Если показатель
  задан на единицу объёма без диапазона — оба null.
- x_unit — единица натурального показателя (га, км, п.м, точка, скважина, км профиля,
  физическая точка, гектар и т.п.) точно как в таблице.
- a — показатель постоянных затрат (ПЗ1) если в таблице две колонки показателей; если
  колонка одна (цена за единицу объёма) — a=0 и b=показатель.
- b — показатель на единицу объёма (ПЗ2 или единственный показатель).
- Все значения в РУБЛЯХ — возвращай КАК ЕСТЬ, без умножений.
- ДЕСЯТИЧНЫЕ ЗАПЯТЫЕ: "1 234,56" → 1234.56. Пробел — разряды, запятая — десятичные.
  Показатель «б» обычно МЕНЬШЕ «а» той же строки — при подозрении на порядок перепроверь запятую.

Верни JSON строго:
{
  "table_num": <int или null>,
  "official_name": "<название НЗ с титульной страницы или null>",
  "rows": [
    {"row_num": "п.1", "description": "...", "x_min": null, "x_max": 5,
     "x_unit": "га", "a": 6266, "b": 4475}
  ]
}
Если на странице нет строк показателей затрат — "rows": [].
Верни ТОЛЬКО JSON."""


def run(key: str) -> None:
    cfg = BOOKS[key]
    db = SessionLocal()
    try:
        book = db.query(ReferenceBook).filter(ReferenceBook.code == cfg["code"]).first()
        if book:
            logger.info(f"Reusing existing {cfg['code']} id={book.id} — clearing rows/types")
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).update({'object_type_id': None})
            db.flush()
            db.query(BookObjectType).filter(BookObjectType.book_version_id == book.id).delete()
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).delete()
            book.parse_prompt = SURVEY_PROMPT
            book.pdf_path = cfg["pdf"]
            book.price_base_year = cfg["base_year"]
            book.calc_method = "survey"
            db.commit()
        else:
            book = ReferenceBook(
                code=cfg["code"],
                official_name=cfg["name"],
                version=1,
                status="requires_validation",
                is_active=False,
                price_base_year=cfg["base_year"],
                calc_method="survey",
                parse_prompt=SURVEY_PROMPT,
                pdf_path=cfg["pdf"],
            )
            db.add(book)
            db.commit()
            db.refresh(book)
            logger.info(f"Created book id={book.id}")

        def on_progress(page, total, msg):
            if page % 10 == 0 or page == total:
                logger.info(f"  {msg}")

        rows, official_name = parse_reference_pdf(cfg["pdf"], SURVEY_PROMPT, on_progress=on_progress)
        logger.info(f"Parsed {len(rows)} rows")

        inserted = 0
        for r in rows:
            a_raw, b_raw = r.get('a'), r.get('b')
            if a_raw is None and b_raw is None:
                continue
            db.add(ReferenceRow(
                book_version_id=book.id,
                table_num=r['table_num'],
                row_num=r.get('row_num'),
                description=r.get('description'),
                x_min=r.get('x_min'),
                x_max=r.get('x_max'),
                x_unit=r.get('x_unit'),
                a=float(a_raw) if a_raw is not None else None,   # rubles as-is
                b=float(b_raw) if b_raw is not None else None,   # rubles as-is
                notes=None,
            ))
            inserted += 1
        db.commit()
        logger.info(f"Inserted {inserted} rows")

        db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).update({'object_type_id': None})
        db.flush()
        n_types = rebuild_object_types(db, book.id)
        logger.info(f"Rebuilt {n_types} object types")

        book.is_active = True
        book.status = "consistent"
        db.add(book)
        db.commit()
        logger.info(f"Book {cfg['code']} id={book.id} activated (calc_method=survey).")
    finally:
        db.close()


if __name__ == "__main__":
    run(sys.argv[1])

"""НЗ-52-ГРС (Приказ Минстроя от 03.02.2025 № 52/пр) — газораспределительные
сети. ЧАСТИЧНЫЙ кураторский импорт (vision, лист 21): табл.3.16 и 3.17
(теплогенераторные и котельные установки). Остальные таблицы (3.1-3.15,
3.18+) — дочитка по мере надобности (OCR кривой, числа сверять глазами).

База цен 01.01.2024 (код эталона «НЗ-2024-МС52», индекс 1,27 в БД есть).
Верификация: эталон Котельной п.2: (2388,8+259,358×4)×40%×1,27 = 1740,53 тыс.
"""
import sys
from datetime import datetime, timezone
sys.path.insert(0, "/app")
from app.database import SessionLocal
from app.models import BookObjectType, ReferenceBook, ReferenceRow

CODE = "НЗ-2024-МС52-ГРС"
DATA = [
    ("Теплогенераторная установка, тепловой мощностью (НЗ-52 т.3.16)", 316, [
        ("п.1", "до 0,07 МВт включительно", "объект", None, None, 934.1, None),
        ("п.1", "от 0,07 до 0,36 МВт", "МВт", 0.07, 0.36, 679.3, 3639.931),
    ]),
    ("Котельная установка с газовыми котлами наружного размещения (НЗ-52 т.3.17)", 317, [
        ("п.1", "от 0,36 до 1 МВт (за установку)", "установка", 0.36, 1, 1619.2, 1028.984),
        ("п.1", "свыше 1 до 5 МВт", "МВт", 1, 5, 2388.8, 259.358),
        ("п.1", "свыше 5 до 10 МВт", "МВт", 5, 10, 3238.8, 89.358),
    ]),
]

db = SessionLocal()
old = db.query(ReferenceBook).filter(ReferenceBook.code == CODE).first()
if old:
    for m in (ReferenceRow, BookObjectType):
        db.query(m).filter(m.book_version_id == old.id).delete()
    db.delete(old)
    db.flush()
book = ReferenceBook(
    code=CODE,
    official_name="НЗ на подготовку проектной документации: газораспределительные "
                  "сети (Приказ Минстроя от 03.02.2025 № 52/пр). ЧАСТИЧНО: табл.3.16-3.17",
    version=1, status="consistent", is_active=True,
    price_base_year=2024, calc_method="standard", pricing_method="707pr",
    uploaded_at=datetime.now(timezone.utc),
    notes="Кураторский частичный импорт (vision, import_nz52.py): табл.3.16-3.17 "
          "(котельные). Остальные таблицы — дочитка (лист 21 из ~27).",
)
db.add(book)
db.flush()
n = 0
for tname, tn, rows in DATA:
    ot = BookObjectType(book_version_id=book.id, name=tname, table_num=tn)
    db.add(ot)
    db.flush()
    for row_num, desc, unit, x_min, x_max, a, b in rows:
        db.add(ReferenceRow(book_version_id=book.id, object_type_id=ot.id,
                            table_num=tn, row_num=row_num, description=desc,
                            x_unit=unit, x_min=x_min, x_max=x_max, a=a, b=b))
        n += 1
db.commit()
print(f"{CODE}: строк {n}")
db.close()

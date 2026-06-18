"""Seed BookCondition records for K1 (корректирующий коэффициент) per table.

НЗ-2025-МС281-ИГИ Таблица 1 (Приказ Минстроя 281/пр от 12.05.2025):
  All field work (default): K1 = 0.70
  Колонковое бурение        (Табл.14): K1 = 0.76
  Колонковое бурение ССК    (Табл.16): K1 = 0.72
  Закопушки / шурфы         (Табл.28–32): K1 = 0.55
  Опытно-фильтрационные     (Табл.34,35,37,39,41): K1 = 0.57
  Статическое зондирование  (Табл.43–44): K1 = 0.85

Run inside container:
  docker exec ib-project-calculator-backend-1 \\
    python /app/app/scripts/seed_nz_281pr_geolog_k1_conditions.py
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import BookCondition, ReferenceBook

BOOK_CODE = "НЗ-2025-МС281-ИГИ"

# (table_num, k1_value, description)
K1_TABLE = [
    (14,  0.76, "Колонковое бурение (Табл.14 п.55 НЗ)"),
    (16,  0.72, "Колонковое бурение ССК (Табл.16 п.57 НЗ)"),
    (28,  0.55, "Закопушки (Табл.28 п.70 НЗ)"),
    (29,  0.55, "Вскрытие покрытий для шурфов (Табл.29)"),
    (30,  0.55, "Шурфы проходка (Табл.30 п.74 НЗ)"),
    (31,  0.55, "Крепление шурфов (Табл.31)"),
    (32,  0.55, "Водоотлив из шурфов (Табл.32)"),
    (34,  0.57, "Опытно-фильтрационные: пробная откачка (Табл.34)"),
    (35,  0.57, "Опытно-фильтрационные: одиночная откачка (Табл.35)"),
    (37,  0.57, "Опытно-фильтрационные: кустовая откачка (Табл.37)"),
    (39,  0.57, "Опытно-фильтрационные: опытный налив (Табл.39)"),
    (41,  0.57, "Опытно-фильтрационные: кустовой налив (Табл.41)"),
    (43,  0.85, "Статическое зондирование (Табл.43 п.55 НЗ)"),
    (44,  0.85, "Статическое зондирование прерывистое (Табл.44)"),
]


def main():
    db = SessionLocal()
    try:
        book = db.query(ReferenceBook).filter(ReferenceBook.code == BOOK_CODE).first()
        if not book:
            print(f"ERROR: book {BOOK_CODE} not found — run seed_nz_281pr_geolog.py first",
                  file=sys.stderr)
            sys.exit(1)
        print(f"Book: {book.code} id={book.id}")

        added = 0
        for table_num, k1_val, note in K1_TABLE:
            existing = db.query(BookCondition).filter(
                BookCondition.book_version_id == book.id,
                BookCondition.table_num == table_num,
                BookCondition.coeff_key == "k1",
            ).first()
            if existing:
                if abs(float(existing.coeff_min) - k1_val) > 0.001:
                    existing.coeff_min = k1_val
                    existing.coeff_max = k1_val
                    existing.description = note
                    print(f"  ~ updated табл.{table_num}: k1={k1_val}")
                    added += 1
                else:
                    print(f"  = exists табл.{table_num}: k1={k1_val}")
                continue
            cond = BookCondition(
                book_version_id=book.id,
                table_num=table_num,
                coeff_key="k1",
                coeff_min=k1_val,
                coeff_max=k1_val,
                description=note,
            )
            db.add(cond)
            added += 1
            print(f"  + табл.{table_num}: k1={k1_val}  [{note}]")

        db.commit()
        print(f"\nDone. Added/updated {added} K1 conditions.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

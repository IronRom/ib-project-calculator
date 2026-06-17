"""Seed missing rows for НЗ-2021-МС847-СИТО that aren't parsed from PDF.

Adds п.11 (шкаф в существующем РП) and п.12 (шкаф РЗА) to table 313.
Also seeds BookObjectType entries for these object types if missing.

Run inside container:
  docker exec ib-project-calculator-backend-1 \
    python /app/app/scripts/seed_nz_sito_missing_rows.py
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import BookObjectType, ReferenceBook, ReferenceRow

# Rows to add per table
# (table_num, row_num, description, x_min, x_max, x_unit, a, b, object_type_name)
MISSING_ROWS = [
    (313, "п.11", "Установка дополнительного шкафа в существующем распределительном пункте",
     None, None, "шт", 4.8, 0.0, "Шкаф в существующем РП"),
    # п.12 — шкаф РЗА/защиты (применительно, те же параметры что п.11)
    (313, "п.11а", "Установка шкафа РЗА / защиты в существующем РП (применительно)",
     None, None, "шт", 4.8, 0.0, "Шкаф РЗА в существующем РП"),
]


def main():
    db = SessionLocal()
    try:
        # Find active НЗ-СИТО book
        book = (
            db.query(ReferenceBook)
            .filter(
                ReferenceBook.is_active == True,
                ReferenceBook.code.ilike("%СИТО%"),
            )
            .first()
        )
        if not book:
            print("ERROR: active НЗ-СИТО book not found", file=sys.stderr)
            sys.exit(1)

        print(f"Book: {book.code} id={book.id}")

        for table_num, row_num, desc, x_min, x_max, x_unit, a, b, otype_name in MISSING_ROWS:
            # Upsert object type
            otype = (
                db.query(BookObjectType)
                .filter(
                    BookObjectType.book_version_id == book.id,
                    BookObjectType.name == otype_name,
                )
                .first()
            )
            if not otype:
                otype = BookObjectType(
                    book_version_id=book.id,
                    name=otype_name,
                    table_num=table_num,
                )
                db.add(otype)
                db.flush()
                print(f"  + object_type: {otype_name} id={otype.id}")
            else:
                print(f"  = object_type exists: {otype_name} id={otype.id}")

            # Check if row already exists
            existing = (
                db.query(ReferenceRow)
                .filter(
                    ReferenceRow.book_version_id == book.id,
                    ReferenceRow.table_num == table_num,
                    ReferenceRow.row_num == row_num,
                )
                .first()
            )
            if existing:
                print(f"  = row exists: табл.{table_num} {row_num}")
                continue

            row = ReferenceRow(
                book_version_id=book.id,
                object_type_id=otype.id,
                table_num=table_num,
                row_num=row_num,
                description=desc,
                x_min=x_min,
                x_max=x_max,
                x_unit=x_unit,
                a=a,
                b=b,
            )
            db.add(row)
            print(f"  + row: табл.{table_num} {row_num} a={a} b={b} x_unit={x_unit!r}")

        db.commit()
        print("\nDone.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

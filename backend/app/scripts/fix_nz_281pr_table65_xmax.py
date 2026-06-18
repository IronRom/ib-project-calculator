"""Fix Table 65 "свыше" rows: set x_min to the correct reference threshold.

НЗ 281/пр Table 65 last rows:
  Cat I  п.7:  "свыше 1500.0" — x_min must be 1500 (was 1000)
  Cat II п.15: "свыше 3500.0" — x_min must be 3500 (was 2000)
  Cat III п.24:"свыше 10000.0"— x_min must be 10000 (was 5000)

These are used as reference points for linear interpolation in _lookup_report_cost.

Run inside container:
  docker exec ib-project-calculator-backend-1 \\
    python /app/app/scripts/fix_nz_281pr_table65_xmax.py
"""
import sys
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import ReferenceBook, ReferenceRow

BOOK_CODE = "НЗ-2025-МС281-ИГИ"

# (row_num, correct_x_min)
FIXES = [
    ("п.7",  1500),   # Cat I  "свыше 1500 тыс.руб"
    ("п.15", 3500),   # Cat II "свыше 3500 тыс.руб"
    ("п.24", 10000),  # Cat III "свыше 10000 тыс.руб"
]


def main():
    db = SessionLocal()
    try:
        book = db.query(ReferenceBook).filter(ReferenceBook.code == BOOK_CODE).first()
        if not book:
            print(f"ERROR: book {BOOK_CODE} not found", file=sys.stderr)
            sys.exit(1)

        fixed = 0
        for row_num, correct_x_min in FIXES:
            row = db.query(ReferenceRow).filter(
                ReferenceRow.book_version_id == book.id,
                ReferenceRow.table_num == 65,
                ReferenceRow.row_num == row_num,
                ReferenceRow.x_max == None,
            ).first()
            if not row:
                print(f"  ? табл.65 {row_num} with x_max=None not found (already fixed?)")
                continue
            old_x_min = row.x_min
            row.x_min = correct_x_min
            fixed += 1
            print(f"  fix табл.65 {row_num}: x_min {old_x_min} → {correct_x_min}")

        db.commit()
        print(f"\nDone. Fixed {fixed} rows.")
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

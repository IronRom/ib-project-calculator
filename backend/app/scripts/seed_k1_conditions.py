"""Seed K1 coefficients per table into book_conditions for НЗ-2025-МС281-ИГИ.

НЗ-2025-МС281-ИГИ Табл.1 п.12 defines different K1 values per work type:
  - Table 14 (колонковый): K1=0.76
  - Table 16 (ССК): K1=0.72
  - Tables 28-32 (закопушки/шурфы): K1=0.55
  - Tables 34,35,37,39,41 (фильтрация): K1=0.57
  - Tables 43-44 (зондирование): K1=0.85
  - All others: fallback to survey.k1 (0.70, no DB entry needed)

Run via:
  docker exec ib-project-calculator-backend-1 python3 /app/scripts/seed_k1_conditions.py
"""
import sys
sys.path.insert(0, '/app')

from app.models import BookCondition
from app.database import SessionLocal

# book_version_id for НЗ-2025-МС281-ИГИ
BOOK_VERSION_ID = 9

# table_num → k1_value per НЗ-2025-МС281-ИГИ Табл.1 п.12
K1_BY_TABLE = {
    14: 0.76,   # колонковый
    16: 0.72,   # ССК
    28: 0.55,   # закопушки/шурфы
    29: 0.55,
    30: 0.55,
    31: 0.55,
    32: 0.55,
    34: 0.57,   # фильтрация
    35: 0.57,
    37: 0.57,
    39: 0.57,
    41: 0.57,
    43: 0.85,   # зондирование
    44: 0.85,
    # Tables not listed here fall back to survey.k1 = 0.70 (default)
}

TABLE_NOTES = {
    14: "колонковый",
    16: "ССК",
    28: "закопушки/шурфы", 29: "закопушки/шурфы", 30: "закопушки/шурфы",
    31: "закопушки/шурфы", 32: "закопушки/шурфы",
    34: "фильтрация", 35: "фильтрация", 37: "фильтрация",
    39: "фильтрация", 41: "фильтрация",
    43: "зондирование", 44: "зондирование",
}


def main():
    db = SessionLocal()
    added = 0
    skipped = 0

    try:
        for table_num, k1 in K1_BY_TABLE.items():
            existing = db.query(BookCondition).filter_by(
                book_version_id=BOOK_VERSION_ID,
                table_num=table_num,
                coeff_key="k1",
            ).first()
            if existing:
                print(f"SKIP  table {table_num}: K1={existing.coeff_min} already exists")
                skipped += 1
                continue

            note = TABLE_NOTES.get(table_num, "")
            db.add(BookCondition(
                book_version_id=BOOK_VERSION_ID,
                table_num=table_num,
                coeff_key="k1",
                coeff_min=k1,
                coeff_max=k1,
                condition_short=f"К1 табл.{table_num}" + (f" ({note})" if note else ""),
                condition_text_full=(
                    f"Корректирующий коэффициент К1={k1} для таблицы {table_num}"
                    f" ({note}) — НЗ-2025-МС281-ИГИ Табл.1 п.12"
                ),
                effect_type="field_k1",
            ))
            print(f"ADD   table {table_num}: K1={k1}" + (f" ({note})" if note else ""))
            added += 1

        db.commit()
        print(f"\nDone: {added} added, {skipped} skipped.")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

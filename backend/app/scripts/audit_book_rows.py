"""Audit reference_rows of a book for parse defects (universal, any book).

Checks per (table_num, row_num, x_unit) group of interval rows:
1. Price continuity at interval boundaries: цена по строке i в точке X=x_max
   должна примерно совпадать с ценой строки i+1 в той же точке.
   Разрыв больше tolerance → вероятная ошибка парсинга (запятая, разряд).
2. Magnitude sanity: b×X_max сопоставимо с a (b, увеличенное в 1000 раз из-за
   десятичной запятой, даёт вклад в тысячи раз больше a).

Run: PYTHONPATH=/app python -m app.scripts.audit_book_rows "НЗ-2025-МС53-ВК" [tolerance]
"""
import sys

from app.database import SessionLocal
from app.models import ReferenceBook, ReferenceRow


def audit(book_code: str, tolerance: float = 0.5) -> list[str]:
    db = SessionLocal()
    problems: list[str] = []
    try:
        book = db.query(ReferenceBook).filter(ReferenceBook.code == book_code).first()
        if not book:
            raise SystemExit(f"Книга «{book_code}» не найдена")

        rows = (
            db.query(ReferenceRow)
            .filter(ReferenceRow.book_version_id == book.id)
            .order_by(ReferenceRow.table_num, ReferenceRow.id)
            .all()
        )

        groups: dict[tuple, list[ReferenceRow]] = {}
        for r in rows:
            if r.x_min is None and r.x_max is None:
                continue  # unit-priced — nothing to check
            key = (r.table_num, r.row_num or "", r.x_unit or "")
            groups.setdefault(key, []).append(r)

        for (tnum, rnum, unit), grp in groups.items():
            grp = sorted(grp, key=lambda r: float(r.x_min if r.x_min is not None else 0))

            # 2) magnitude: b contribution vs a
            for r in grp:
                if r.a is None or r.b is None or r.x_max is None:
                    continue
                a, b, xmax = float(r.a), float(r.b), float(r.x_max)
                if a > 0 and b * xmax > a * 200:
                    problems.append(
                        f"[магнитуда] табл.{tnum} {rnum} ({unit}): b×Xmax = {b * xmax:,.0f} "
                        f"при a = {a:,.0f} (×{b * xmax / a:,.0f}) — проверь десятичную запятую в b"
                    )

            # 1) continuity at boundaries
            for r1, r2 in zip(grp, grp[1:]):
                if r1.x_max is None or r2.x_min is None:
                    continue
                if float(r1.x_max) != float(r2.x_min):
                    continue  # not adjacent intervals
                x = float(r1.x_max)
                p1 = float(r1.a or 0) + float(r1.b or 0) * x
                p2 = float(r2.a or 0) + float(r2.b or 0) * x
                if p1 <= 0 or p2 <= 0:
                    continue
                rel = abs(p1 - p2) / max(p1, p2)
                if rel > tolerance:
                    problems.append(
                        f"[разрыв {rel * 100:.0f}%] табл.{tnum} {rnum} ({unit}) на X={x:g}: "
                        f"цена слева {p1:,.1f} vs справа {p2:,.1f}"
                    )
    finally:
        db.close()
    return problems


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "НЗ-2025-МС53-ВК"
    tol = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    issues = audit(code, tol)
    if not issues:
        print(f"OK — проблем не найдено ({code})")
    else:
        print(f"{len(issues)} подозрительных мест в «{code}»:")
        for p in issues:
            print("  " + p)

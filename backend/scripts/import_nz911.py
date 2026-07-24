"""Импорт НЗ-2022-МС911 (приказ Минстроя от 13.12.2023 № 911/пр) —
объекты городской среды: благоустройство, МАФ, озеленение, фонтаны,
водоемы, АХО, ритуальные объекты, ТКО, рекультивация, проекты СЗЗ.

Источник: vision-оцифровка приказа (текстовый слой битый) —
scripts/nz911_digitized.json. Цены в ТЫС. РУБ., база 01.01.2022
(индекс 2022 → 1,53 уже в price_quarterly_indices).

Особенность: проекты СЗЗ (табл. 3.10 пп.2,3) заданы ОПОРНЫМИ ТОЧКАМИ
(x_min = x_max = точка, только «а») — движок считает интерполяцией
707/пр ф.8.6-8.8. Эталон СПб (ЛС-10): X=5,15 га → 660,1 + (2640,4-660,1)/9
× 4,15 = 1573,238 тыс. — встроенный spot-check.

Usage: PYTHONPATH=/app python /app/scripts/import_nz911.py /tmp/nz911_digitized.json
"""
import json
import re
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models import BookCondition, BookObjectType, ReferenceBook, ReferenceRow

CODE = "НЗ-2022-МС911"
NAME = ("Нормативные затраты на работы по подготовке проектной документации "
        "для строительства объектов городской среды. "
        "Приказ Минстроя России от 13.12.2023 № 911/пр (цены 01.01.2022)")


def tn_int(s: str) -> int:
    # "3.01" → 301, "3.10" → 310 (конвенция СИТО/МРР)
    return int(s.replace(".", ""))


def group_key(row_num: str) -> str:
    return row_num.split(".")[0]


def base_name(desc: str) -> str:
    """Имя типа объекта: описание без интервального хвоста."""
    cut = re.split(r",\s*(?:площадью|от |до |емкостью|мощностью|высотой|с количеством)", desc)[0]
    return cut.strip().rstrip(",")[:110]


def run(json_path: str) -> None:
    data = json.load(open(json_path, encoding="utf-8"))
    db = SessionLocal()
    try:
        book = db.query(ReferenceBook).filter(ReferenceBook.code == CODE).first()
        if book:
            if book.notes and not book.notes.startswith("Оцифровано"):
                raise SystemExit(f"{CODE}: кураторская книга, импорт запрещён")
            db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).delete()
            db.query(BookObjectType).filter(BookObjectType.book_version_id == book.id).delete()
            db.query(BookCondition).filter(BookCondition.book_version_id == book.id).delete()
            db.flush()
        else:
            book = ReferenceBook(code=CODE, official_name=NAME, version=1,
                                 status="consistent", is_active=False)
            db.add(book)
            db.flush()
        book.official_name = NAME
        book.notes = "Оцифровано vision-агентом по приказу 911/пр, 2026-07-24"
        book.price_base_year = 2022
        book.pricing_method = "707pr"
        book.calc_method = "standard"

        n_types = n_rows = n_cond = 0
        for t in data["tables"]:
            tn = tn_int(t["table_num"])
            groups: dict[str, list[dict]] = {}
            for r in t["rows"]:
                groups.setdefault(group_key(r["row_num"]), []).append(r)
            for g, rows in groups.items():
                ot = BookObjectType(
                    book_version_id=book.id,
                    name=f"{base_name(rows[0]['description'])} (табл.{t['table_num']} п.{int(g)})",
                    table_num=tn,
                )
                db.add(ot)
                db.flush()
                n_types += 1
                for r in rows:
                    db.add(ReferenceRow(
                        book_version_id=book.id, object_type_id=ot.id,
                        table_num=tn, row_num=f"п.{r['row_num']}",
                        description=r["description"][:900],
                        x_unit=(r.get("x_unit") or "")[:100],
                        x_min=r.get("x_min"), x_max=r.get("x_max"),
                        a=r.get("a"), b=r.get("b"),
                    ))
                    n_rows += 1

        for c in data.get("coefficients", []):
            tn = tn_int(c["applies_to"]) if c.get("applies_to") else None
            db.add(BookCondition(
                book_version_id=book.id, table_num=tn,
                row_range=c.get("row_range"),
                condition_short=f"{c['condition']} ({c['source']})"[:500],
                condition_text_full=f"{c['source']}: {c['condition']}",
                effect_type="multiplier_range",
                coeff_min=c["value"], coeff_max=c["value"], coeff_key=None,
            ))
            n_cond += 1

        # важные оговорки — flag-условия book-wide (контекст для AI)
        for note in data.get("notes_important", []):
            db.add(BookCondition(
                book_version_id=book.id, table_num=None,
                condition_short=note[:500], condition_text_full=note,
                effect_type="flag", coeff_min=None, coeff_max=None, coeff_key=None,
            ))
            n_cond += 1

        # ── Spot-checks против эталонной сметы СПб ────────────────────────
        def row(tn, num):
            return (db.query(ReferenceRow)
                    .filter(ReferenceRow.book_version_id == book.id,
                            ReferenceRow.table_num == tn,
                            ReferenceRow.row_num == num).first())

        r = row(301, "п.001.1"); assert r and float(r.a) == 277.6, "301/001.1 ≠ 277.6"
        r = row(301, "п.001.3"); assert r and float(r.a) == 302.2 and float(r.b) == 268.8, "301/001.3"
        r = row(303, "п.001");   assert r and float(r.a) == 62.2 and float(r.b) == 4.139, "303/001"
        r = row(309, "п.005");   assert r and float(r.a) == 562.5 and float(r.b) == 1.193, "309/005"
        p1 = row(310, "п.002.1"); p2 = row(310, "п.002.2")
        assert p1 and float(p1.a) == 660.1 and p2 and float(p2.a) == 2640.4, "310 СЗЗ точки"
        # интерполяция эталона ЛС-10: X=5,15 га
        interp = 660.1 + (2640.4 - 660.1) / (10 - 1) * (5.15 - 1)
        assert abs(interp - 1573.2383) < 0.001, interp

        book.is_active = True
        db.commit()
        print(f"{CODE} id={book.id}: таблиц {len(data['tables'])}, типов {n_types}, "
              f"строк {n_rows}, условий {n_cond}. Spot-checks OK "
              f"(СЗЗ 5,15 га → {interp:.3f} тыс. базовых)")
    finally:
        db.close()


if __name__ == "__main__":
    run(sys.argv[1])

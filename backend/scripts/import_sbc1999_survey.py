"""Импорт СБЦ-1999/2001 изыскательских справочников из agent-JSON.

Книги (цены 01.01.2001, РУБЛИ, calc_method='survey'):
  ekologiya — «Инженерно-геологические и инженерно-экологические изыскания»
  gidromet  — «Инженерно-гидрографические работы. Инженерно-гидрометеорологические
               изыскания на реках»

Схема входного JSON (готовит агент-оцифровщик):
  {"book": {"title", "price_date", "notes": [...]},
   "tables": [{"table_num", "title", "izmeritel", "columns": [...],
               "rows": [{"par", "name", "values": {col: num | {"полевые":x, "камеральные":y}}}],
               "notes": [...]}],
   "chapters": [{"num", "title", "rules": [...]}]}

Конвенции БД — как у МРР гл.3 (import_mrr_digitized):
  object_type per (таблица × field/kameral/lab), строка per (§ × колонка),
  цена в b (руб как есть), a=0; примечания с коэффициентами → book_conditions.

Usage (в контейнере):
  PYTHONPATH=/app python /app/scripts/import_sbc1999_survey.py ekologiya /tmp/ekologiya_digitized.json
  PYTHONPATH=/app python /app/scripts/import_sbc1999_survey.py gidromet /tmp/gidromet_digitized.json
"""
import json
import re
import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal
from app.models import (BookCondition, BookObjectType, PriceQuarterlyIndex,
                        ReferenceBook, ReferenceRow)

BOOKS = {
    "ekologiya": dict(
        code="СБЦ-2001-ИГИ-ИЭИ",
        name=("Справочник базовых цен на инженерно-геологические и "
              "инженерно-экологические изыскания для строительства "
              "(цены на 01.01.2001)"),
    ),
    "gidromet": dict(
        code="СБЦ-2001-ГИДРОМЕТ",
        name=("Справочник базовых цен на инженерные изыскания для строительства. "
              "Инженерно-гидрографические работы. Инженерно-гидрометеорологические "
              "изыскания на реках (цены на 01.01.2001)"),
    ),
}

_COEF_RE = re.compile(r"коэффициент[а-я]*\s+(\d+[.,]\d+)|К\s*=\s*(\d+[.,]\d+)", re.I)


def _num(v):
    """Число или None. Формульные цены («80 руб. + 3%…») — не числа."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _category(title: str, col_label: str = "") -> str:
    low = f"{title} {col_label}".lower()
    if "лаборатор" in low:
        return "lab"
    if "камеральн" in low or "отчет" in low or "отчёт" in low or "программ" in low:
        return "kameral"
    return "field"


def import_book(db, key: str, json_path: str) -> None:
    cfg = BOOKS[key]
    data = json.load(open(json_path, encoding="utf-8"))

    book = db.query(ReferenceBook).filter(ReferenceBook.code == cfg["code"]).first()
    if book:
        # защита кураторских: пересоздаём только авто-оцифрованные
        if book.notes and not book.notes.startswith("Оцифровано"):
            raise SystemExit(f"{cfg['code']}: книга кураторская, импорт запрещён")
        db.query(ReferenceRow).filter(ReferenceRow.book_version_id == book.id).delete()
        db.query(BookObjectType).filter(BookObjectType.book_version_id == book.id).delete()
        db.query(BookCondition).filter(BookCondition.book_version_id == book.id).delete()
        db.flush()
    else:
        book = ReferenceBook(
            code=cfg["code"], official_name=cfg["name"], version=1,
            status="consistent", is_active=False,
            price_base_year=2001, calc_method="survey",
        )
        db.add(book)
        db.flush()
    book.official_name = cfg["name"]
    book.notes = "Оцифровано агентом по текстовому слою PDF, 2026-07-24"
    book.price_base_year = 2001
    book.calc_method = "survey"

    n_types = n_rows = n_cond = 0
    for t in data.get("tables", []):
        tn = t.get("table_num")
        if tn is None:
            continue
        try:
            tn = int(tn)
        except (TypeError, ValueError):
            continue
        title = (t.get("title") or "").strip() or f"Таблица {tn}"
        izm = (t.get("izmeritel") or "").strip()
        rows = t.get("rows") or []

        # есть ли дробные цены (полевые/камеральные) в этой таблице
        has_dual = any(isinstance(v, dict) for r in rows
                       for v in (r.get("values") or {}).values())
        cats = ["field", "kameral"] if has_dual else [_category(title)]
        types_here = {}
        for cat in cats:
            label = {"field": " (полевые)", "kameral": " (камеральные)", "lab": ""}[cat] \
                if has_dual else ""
            ot = BookObjectType(
                book_version_id=book.id,
                name=f"{title[:100]}{label} (табл.{tn})",
                table_num=tn, work_category=cat,
            )
            db.add(ot)
            db.flush()
            types_here[cat] = ot
            n_types += 1

        for r in rows:
            par = str(r.get("par") or "").strip()
            name = (r.get("name") or "").strip()
            values = r.get("values") or {}
            for col, v in values.items():
                col_note = f" [{col}]" if col not in ("Цена", "", None) else ""
                desc = f"{name}{col_note}"[:900]
                if isinstance(v, dict):
                    pairs = []
                    if v.get("полевые") is not None:
                        pairs.append(("field", _num(v["полевые"])))
                    if v.get("камеральные") is not None:
                        pairs.append(("kameral", _num(v["камеральные"])))
                else:
                    price = _num(v)
                    if price is None:
                        # формульная цена текстом → условие-примечание таблицы
                        if isinstance(v, str) and v.strip():
                            db.add(BookCondition(
                                book_version_id=book.id, table_num=tn,
                                condition_short=f"§{par} {name[:200]}: {v}"[:500],
                                condition_text_full=f"Табл.{tn} §{par} {name}: {v}",
                                effect_type="flag",
                                coeff_min=None, coeff_max=None, coeff_key=None,
                            ))
                            n_cond += 1
                        continue
                    pairs = [(cats[0], price)]
                for cat, price in pairs:
                    if price is None:
                        continue
                    ot = types_here.get(cat) or next(iter(types_here.values()))
                    db.add(ReferenceRow(
                        book_version_id=book.id, object_type_id=ot.id,
                        table_num=tn, row_num=(f"п.{par}" if par else None),
                        description=desc, x_unit=izm[:100],
                        x_min=None, x_max=None, a=0, b=price,
                    ))
                    n_rows += 1

        # примечания таблицы: коэффициенты → book_conditions
        for note in (t.get("notes") or []):
            note = (note or "").strip()
            if not note:
                continue
            m = _COEF_RE.search(note)
            coef = _num(m.group(1) or m.group(2)) if m else None
            db.add(BookCondition(
                book_version_id=book.id, table_num=tn,
                condition_short=note[:500], condition_text_full=note,
                effect_type=("multiplier_range" if coef else "flag"),
                coeff_min=coef, coeff_max=coef, coeff_key=None,
            ))
            n_cond += 1

    # книжные правила (общие положения) — book-wide условия
    for note in (data.get("book", {}).get("notes") or []):
        note = (note or "").strip()
        if not note:
            continue
        m = _COEF_RE.search(note)
        coef = _num(m.group(1) or m.group(2)) if m else None
        db.add(BookCondition(
            book_version_id=book.id, table_num=None,
            condition_short=note[:500], condition_text_full=note,
            effect_type=("multiplier_range" if coef else "flag"),
            coeff_min=coef, coeff_max=coef, coeff_key=None,
        ))
        n_cond += 1

    book.is_active = True
    db.commit()
    print(f"{cfg['code']} id={book.id}: таблиц {len(data.get('tables', []))}, "
          f"типов {n_types}, строк {n_rows}, условий {n_cond}")


def ensure_survey_index_2001(db) -> None:
    """Индекс изысканий к базе 01.01.2001 = 80,58 (письмо 20212-ИФ/09)."""
    rec = (db.query(PriceQuarterlyIndex)
           .filter(PriceQuarterlyIndex.base_year == 2001,
                   PriceQuarterlyIndex.work_type == "survey").first())
    if not rec:
        db.add(PriceQuarterlyIndex(
            year=2026, quarter=2, base_year=2001, work_type="survey",
            index_value=80.58,
            source_ref="Письмо Минстроя №20212-ИФ/09 от 08.04.2026, "
                       "изыскания к уровню цен 01.01.2001",
        ))
        db.commit()
        print("Добавлен survey-индекс база 2001 → 80.58")
    else:
        print(f"Survey-индекс база 2001 уже есть: {rec.index_value}")


if __name__ == "__main__":
    key, path = sys.argv[1], sys.argv[2]
    session = SessionLocal()
    try:
        ensure_survey_index_2001(session)
        import_book(session, key, path)
    finally:
        session.close()

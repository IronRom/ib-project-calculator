"""Generic-импортёр оцифрованных НЗ-книг (707/пр) из JSON.

Вход — JSON, снятый vision-оцифровкой (см. nz828_digitized.json /
nz848_digitized.json), в схеме:

{
  "code": "НЗ-2021-МС828-ИТСО",
  "base_year": 2021,
  "pd_pct": 0.4, "rd_pct": 0.6,          # NULL/absent → МУ №620 дефолт 0.4/0.6
  "official_name": "...",                 # опционально
  "tables": [
    {"table": 31, "label": "3.1", "title": "...", "object_types": [
       {"point": "п.1", "name": "...", "unit": "кв.м", "rows": [
          {"desc": "...", "x_min": 300, "x_max": 1000, "a": 26.3, "b": 0.070}, ...]},
       ...]},
    ...],
  "conditions": [{"key": "...", "coeff": 1.5, "table": null, "short": "..."}, ...],
  "notes": "..."
}

Создаёт ReferenceBook (pricing_method='707pr', calc_method='standard',
is_active=True) + object_types + rows + conditions. Идемпотентно (сносит
книгу с тем же code перед импортом). Индекс к base_year (work_type='project')
должен уже существовать — иначе печатает предупреждение.

Запуск: docker exec backend python /app/scripts/import_nz_digitized.py \
        /app/scripts/nz828_digitized.json
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BookCondition,
    BookObjectType,
    PriceQuarterlyIndex,
    ReferenceBook,
    ReferenceRow,
)


def _num(v):
    if v is None or v == "" or v == "-":
        return None
    if isinstance(v, str):
        v = v.replace(",", ".").replace(" ", "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(path: str):
    data = json.load(open(path, encoding="utf-8"))
    code = data["code"]
    base_year = int(data.get("base_year") or 2021)

    db = SessionLocal()
    old = db.query(ReferenceBook).filter(ReferenceBook.code == code).first()
    if old:
        for model in (ReferenceRow, BookObjectType, BookCondition):
            db.query(model).filter(model.book_version_id == old.id).delete()
        db.delete(old)
        db.flush()

    book = ReferenceBook(
        code=code,
        official_name=data.get("official_name") or code,
        version=1, status="consistent", is_active=True,
        price_base_year=base_year, calc_method="standard", pricing_method="707pr",
        pd_pct=data.get("pd_pct"), rd_pct=data.get("rd_pct"),
        uploaded_at=datetime.now(timezone.utc),
        notes=data.get("notes") or f"Оцифровано (vision) import_nz_digitized.py из {path.split('/')[-1]}",
    )
    db.add(book)
    db.flush()

    n_types = n_rows = 0
    for t in data.get("tables", []):
        table_num = int(t["table"])
        label = t.get("label", str(table_num))
        for ot in t.get("object_types", []):
            name = ot.get("name", "").strip()
            unit = ot.get("unit", "")
            point = ot.get("point", "")
            obj = BookObjectType(
                book_version_id=book.id,
                name=f"{name} ({code} т.{label}{' ' + point if point else ''})".strip(),
                table_num=table_num,
            )
            db.add(obj)
            db.flush()
            n_types += 1
            for r in ot.get("rows", []):
                db.add(ReferenceRow(
                    book_version_id=book.id, object_type_id=obj.id,
                    table_num=table_num, row_num=point or None,
                    description=r.get("desc", ""), x_unit=unit,
                    x_min=_num(r.get("x_min")), x_max=_num(r.get("x_max")),
                    a=_num(r.get("a")), b=_num(r.get("b")),
                ))
                n_rows += 1

    n_cond = 0
    for c in data.get("conditions", []):
        coeff = _num(c.get("coeff"))
        db.add(BookCondition(
            book_version_id=book.id,
            table_num=(int(c["table"]) if c.get("table") not in (None, "", "null") else None),
            coeff_key=c["key"],
            coeff_min=coeff, coeff_max=coeff,
            condition_short=c.get("short", ""),
            effect_type="multiplier_range" if coeff is not None else "flag",
            apply_mode="multiply",
        ))
        n_cond += 1

    idx = db.query(PriceQuarterlyIndex).filter_by(
        base_year=base_year, work_type="project").order_by(
        PriceQuarterlyIndex.year.desc()).first()
    idx_note = f"индекс к базе {base_year}: {idx.index_value} ({idx.year}q{idx.quarter})" if idx \
        else f"⚠ ИНДЕКС к базе {base_year} (project) НЕ НАЙДЕН — задайте вручную!"

    db.commit()
    print(f"{code}: типов {n_types}, строк {n_rows}, условий {n_cond}; {idx_note}")
    db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/app/scripts/nz828_digitized.json")

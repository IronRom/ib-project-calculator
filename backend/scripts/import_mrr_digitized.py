"""Импорт оцифрованных сборников МРР (JSON от mrr_digitize.py) в БД.

Главы: 3 (изыскания, calc_method='survey', цены в РУБЛЯХ) и
7 (благоустройство, calc_method='standard', цены в тыс. руб, а+в×X).

Правила разбора:
- table_num: id таблицы без точек («3.1.4» → 314, «4.2.3.1» → 4231,
  суффикс «а» → …1, «б» → …2); уникальность в книге проверяется
- survey-таблицы: ценовые колонки — числовые с медианой > 25 (руб);
  прочие числовые колонки (высота сечения, глубина и т.п.) уходят
  в description. Ячейка с двумя числами = полевые/камеральные —
  два object_type (field/kameral) на таблицу
- standard-таблицы (а/в): диапазон X парсится из текста строки
  («до 50», «от 1 до 5», «свыше 100»)
- нормативные таблицы-формулы (text_rows) → book_conditions (справочно,
  coeff_key=NULL)

Запуск: python import_mrr_digitized.py  (внутри контейнера backend)
"""
import json
import re
import sys
from datetime import datetime, timezone
from statistics import median

sys.path.insert(0, "/app")

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BookCondition,
    BookObjectType,
    PriceQuarterlyIndex,
    ReferenceBook,
    ReferenceRow,
)

# (json_file, code, official_name, calc_method)
BOOKS = [
    ("mrr_digitized/МРР-3.1.02-23.json", "МРР-3.1.02-23",
     "Сборник 3.1 «Инженерно-геодезические изыскания. МРР-3.1.02-23» (в ред. от 16.10.2025)", "survey"),
    ("mrr_digitized/МРР-3.2.02-23.json", "МРР-3.2.02-23",
     "Сборник 3.2 «Инженерно-геологические изыскания. МРР-3.2.02-23» (в ред. от 16.10.2025)", "survey"),
    ("mrr_digitized/МРР-3.3.02-23.json", "МРР-3.3.02-23",
     "Сборник 3.3 «Инженерно-экологические изыскания. МРР-3.3.02-23» (в ред. от 16.10.2025)", "survey"),
    ("mrr_digitized/МРР-3.4.02-23.json", "МРР-3.4.02-23",
     "Сборник 3.4 «Работы с применением технологий лазерного сканирования. МРР-3.4.02-23» (в ред. от 18.07.2024)", "survey"),
    ("mrr_digitized/МРР-3.5.02-21.json", "МРР-3.5.02-21",
     "Сборник 3.5 «Археологические исследования. МРР-3.5.02-21»", "survey"),
    ("mrr_digitized/МРР-3.6.02-19.json", "МРР-3.6.02-19",
     "Сборник 3.6 «Обследование состояния грунтов оснований зданий и сооружений. МРР-3.6.02-19» (в ред. от 16.10.2025)", "survey"),
    ("mrr_digitized/МРР-3.7.02-18.json", "МРР-3.7.02-18",
     "Сборник 3.7 «Обследование и мониторинг технического состояния строительных конструкций. МРР-3.7.02-18»", "survey"),
    ("mrr_digitized/МРР-3.8-16.json", "МРР-3.8-16",
     "Сборник 3.8 «Обследование технического состояния мостовых сооружений. МРР-3.8-16»", "survey"),
    ("mrr_digitized/МРР-7.1.03-21.json", "МРР-7.1.03-21",
     "Сборник 7.1 «Объекты благоустройства. МРР-7.1.03-21» (в ред. от 16.10.2025)", "standard"),
    ("mrr_digitized/МРР-7.2.02-24.json", "МРР-7.2.02-24",
     "Сборник 7.2 «Памятники и монументы. МРР-7.2» (в ред. от 25.06.2024)", "standard"),
    ("mrr_digitized/МРР-7.3.02-24.json", "МРР-7.3.02-24",
     "Сборник 7.3 «Фонтаны» (в ред. от 16.10.2025)", "standard"),
    ("mrr_digitized/МРР-7.4.02-24.json", "МРР-7.4.02-24",
     "Сборник 7.4 «Архитектурное освещение» (в ред. от 25.06.2024)", "standard"),
    ("mrr_digitized/МРР-7.6-16.json", "МРР-7.6-16",
     "Сборник 7.6 «Водоемы. МРР-7.6-16»", "standard"),
    ("mrr_digitized/МРР-7.7-20.json", "МРР-7.7-20",
     "Сборник 7.7 «МРР-7.7-20»", "standard"),
    ("mrr_digitized/МРР-7.5.02-20.json", "МРР-7.5.02-20",
     "Сборник 7.5 «Колористическое решение фасадов. МРР-7.5.02-20»", "standard"),
]

RE_RANGE = re.compile(
    r"(?:от\s+([\d\s,.]+)\s+до\s+([\d\s,.]+))|(?:свыше\s+([\d\s,.]+)\s+до\s+([\d\s,.]+))"
    r"|(?:до\s+([\d\s,.]+))|(?:свыше\s+([\d\s,.]+))"
)


def _rownum(num):
    """«5», «6.1», «001.2» → «п.N»; текст → '' (уйдёт в description)."""
    num = (num or "").strip()
    if re.fullmatch(r"[\d.]{1,16}", num):
        return f"п.{num}"
    return ""


def _f(s):
    try:
        return float(s.replace(" ", "").replace(" ", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def parse_range(text):
    m = RE_RANGE.search(text or "")
    if not m:
        return None, None
    g = [(_f(x) if x else None) for x in m.groups()]
    if g[0] is not None or g[1] is not None:
        return g[0], g[1]
    if g[2] is not None or g[3] is not None:
        return g[2], g[3]
    if g[4] is not None:
        return None, g[4]
    if g[5] is not None:
        return g[5], None
    return None, None


def table_num_of(tid):
    s = tid.replace("а", ".91").replace("б", ".92")
    return int(s.replace(".", ""))


def is_ab_table(labels):
    low = [(lb or "").lower().replace("«", "").replace("»", "") for lb in labels]
    has_a = any(re.search(r"(^|\s)а(\s|,|$)", lb) for lb in low)
    has_b = any(re.search(r"(^|\s)в(\s|,|$)", lb) for lb in low)
    return has_a and has_b


def price_columns(rows, threshold=25.0):
    """label → медиана значений; ценовые = медиана > threshold.

    Для survey-книг (руб) порог 25 отсекает параметровые колонки (высоты,
    масштабы); для standard (тыс.руб) цены бывают единицами — сперва ищем
    колонки с «цена» в подписи, порог применяем как fallback."""
    stats = {}
    for r in rows:
        for lb, vals in r["vals"].items():
            stats.setdefault(lb, []).extend(vals)
    return {lb for lb, vs in stats.items() if vs and median(vs) > threshold}


def import_book(db, json_path, code, name, calc_method, log):
    data = json.load(open(json_path))
    old = db.query(ReferenceBook).filter(ReferenceBook.code == code).first()
    if old:
        for model in (ReferenceRow, BookObjectType, BookCondition):
            db.query(model).filter(model.book_version_id == old.id).delete()
        db.delete(old)
        db.flush()

    book = ReferenceBook(
        code=code, official_name=name, version=1, status="consistent",
        is_active=True, price_base_year=2000, calc_method=calc_method,
        uploaded_at=datetime.now(timezone.utc),
        notes="Оцифровано из текстового слоя PDF 22.07.2026 (mrr_digitize.py). "
              "Пересчёт — Кпер МКЭ к базе 01.01.2000.",
    )
    db.add(book)
    db.flush()

    seen_tn = {}
    n_rows = n_types = n_cond = 0
    for t in data["tables"]:
        tn = table_num_of(t["id"])
        if tn in seen_tn:
            log.append(f"{code}: КОЛЛИЗИЯ table_num {tn} ({t['id']} vs {seen_tn[tn]}) — пропуск")
            continue
        seen_tn[tn] = t["id"]
        title = (t["title"] or f"Таблица {t['id']}")[:250]

        if t.get("text_rows"):
            # нормативная таблица-формула → условие (справочно)
            body = "\n".join(
                f"п.{r['num']}: " + "; ".join(f"{k}: {v}" for k, v in r["cells"].items())
                for r in t["text_rows"]
            )
            db.add(BookCondition(
                book_version_id=book.id, table_num=tn,
                condition_short=f"Табл.{t['id']} (норматив-формула): {title[:120]}",
                condition_text_full=body[:4000], effect_type="flag",
            ))
            n_cond += 1
            continue
        # примечания к таблице → условия (Pass 2 видит их через conditions-контекст)
        for note in (t.get("notes") or []):
            coeffs = note.get("coeffs") or []
            uniq = sorted(set(coeffs))
            db.add(BookCondition(
                book_version_id=book.id, table_num=tn,
                condition_short=f"Прим. к табл.{t['id']}: {note['text'][:180]}",
                condition_text_full=note["text"][:4000],
                effect_type="multiplier_range" if uniq else "flag",
                coeff_min=uniq[0] if len(uniq) == 1 else None,
                coeff_max=uniq[0] if len(uniq) == 1 else None,
            ))
            n_cond += 1

        if not t["rows"]:
            continue

        ab = calc_method == "standard" and is_ab_table(t["labels"])
        if ab:
            # object_type PER ПУНКТ: у пунктов пересекаются диапазоны X,
            # слепой матч по таблице берёт чужую строку (урок МРР-4.2)
            a_lb = next(lb for lb in t["labels"] if re.search(r"(^|\s|/)\s*«?а»?(\s|,|$)", (lb or "").lower()))
            b_lb = next(lb for lb in t["labels"] if re.search(r"(^|\s|/)\s*«?в»?(\s|,|$)", (lb or "").lower()))
            ots_by_num = {}
            for r in t["rows"]:
                a = (r["vals"].get(a_lb) or [None])[0]
                b = (r["vals"].get(b_lb) or [None])[0]
                if a is None and b is None:
                    continue
                key = r["num"] or "_"
                if key not in ots_by_num:
                    base_name = r["name"].split("::")[0].strip() or title[:90]
                    ot = BookObjectType(
                        book_version_id=book.id,
                        name=f"{base_name[:95]} (табл.{t['id']} {_rownum(r['num']) or ''})".strip(),
                        table_num=tn)
                    db.add(ot)
                    db.flush()
                    ots_by_num[key] = ot
                    n_types += 1
                ot = ots_by_num[key]
                x_min, x_max = parse_range(r["name"])
                db.add(ReferenceRow(
                    book_version_id=book.id, object_type_id=ot.id, table_num=tn,
                    row_num=_rownum(r["num"]),
                    description=(r["name"] if _rownum(r["num"]) or not r["num"]
                                 else f"{r['num']} {r['name']}")[:900],
                    x_unit=(r["unit"] or "")[:100],
                    x_min=x_min, x_max=x_max, a=a or 0, b=b,
                ))
                n_rows += 1
            continue

        # survey (или standard без а/в): ценовые колонки по медиане
        if calc_method == "standard":
            all_lbs = {lb for r in t["rows"] for lb in r["vals"]}
            pcols = {lb for lb in all_lbs if "цена" in (lb or "").lower()} \
                or price_columns(t["rows"], threshold=0.0)
        else:
            pcols = price_columns(t["rows"])
        if not pcols:
            continue
        has_dual = any(len(v) >= 2 for r in t["rows"] for lb, v in r["vals"].items() if lb in pcols)
        types_here = {}
        cats = (["field", "kameral"] if calc_method == "survey" else ["field"]) if has_dual else [None]
        low_title = title.lower()
        default_cat = ("kameral" if ("камеральн" in low_title or "отчет" in low_title or "программ" in low_title)
                       else "lab" if "лаборатор" in low_title else "field")
        for cat in cats:
            label = {"field": " (полевые)", "kameral": " (камеральные)", None: ""}[cat]
            wc = cat or default_cat
            ot = BookObjectType(book_version_id=book.id,
                                name=f"{title[:100]}{label} (табл.{t['id']})",
                                table_num=tn)
            if hasattr(ot, "work_category"):
                ot.work_category = wc if calc_method == "survey" else None
            db.add(ot)
            db.flush()
            types_here[cat] = ot
            n_types += 1

        for r in t["rows"]:
            # параметровые числовые колонки → в description
            extra = [f"{lb}: {'/'.join(str(x) for x in v)}"
                     for lb, v in r["vals"].items() if lb not in pcols]
            desc_base = r["name"]
            if extra:
                desc_base = (desc_base + " | " + "; ".join(extra)).strip(" |")
            for lb in sorted(pcols):
                vals = r["vals"].get(lb)
                if not vals:
                    continue
                col_note = lb.replace("\n", " ")[:120]
                pairs = ([(cats[0], vals[0]), (cats[1], vals[1])]
                         if has_dual and len(vals) >= 2 and len(cats) == 2
                         else [(cats[0], vals[0])])
                for cat, price in pairs:
                    ot = types_here.get(cat) or next(iter(types_here.values()))
                    db.add(ReferenceRow(
                        book_version_id=book.id, object_type_id=ot.id, table_num=tn,
                        row_num=_rownum(r["num"]),
                        description=((f"{desc_base} [{col_note}]") if _rownum(r["num"]) or not r["num"]
                                     else f"{r['num']} {desc_base} [{col_note}]")[:900],
                        x_unit=(r["unit"] or "")[:100],
                        x_min=None, x_max=None, a=0, b=price,
                    ))
                    n_rows += 1

    log.append(f"{code}: таблиц {len(seen_tn)}, типов {n_types}, строк {n_rows}, "
               f"условий {n_cond}, пропущено парсером {len(data['skipped'])}")
    return book


def main():
    import os
    db = SessionLocal()
    log = []
    books = list(BOOKS)
    manifest = "/app/scripts/mrr_digitized/manifest.json"
    if os.path.exists(manifest):
        seen = {b[1] for b in books}
        for m in json.load(open(manifest)):
            if m["code"] not in seen:
                books.append((m["json"], m["code"], m["name"], m.get("method", "standard")))
    for jf, code, name, method in books:
        path = f"/app/scripts/{jf}" if not jf.startswith("mrr_digitized/") or True else jf
        import_book(db, f"/app/scripts/{jf}", code, name, method, log)

    # survey-индекс МКЭ к базе 2000 (для igi_calculator)
    for wt in ("survey",):
        if not db.query(PriceQuarterlyIndex).filter_by(
                year=2026, quarter=2, base_year=2000, work_type=wt).first():
            db.add(PriceQuarterlyIndex(
                year=2026, quarter=2, base_year=2000, work_type=wt,
                index_value=9.923,
                source_ref="Письмо МосКомЭкспертизы № МКЭ-ОД/26-10 от 20.02.2026 (Кпер МКЭ к 01.01.2000)",
            ))
    db.commit()
    for line in log:
        print(line)
    db.close()


if __name__ == "__main__":
    main()

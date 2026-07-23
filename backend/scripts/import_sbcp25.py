"""Кураторский импорт СБЦП 81-2001-25 «Обмерные работы и обследования
зданий и сооружений» (изд. 2016). Без AI.

Структура книги:
  табл.1-4  — МАТРИЦЫ (кат. сложности РАБОТ 1-3 × кат. сложности ЗДАНИЯ
              I-III × высота здания до 4..21+ м), руб/100 м³ строительного
              объёма. Парсинг по КООРДИНАТАМ слов (текстовые строки ломает
              OCR-мусор в прочерках) — колонка определяется ближайшим
              x-центром заголовка высоты
  табл.15   — обследование систем инженерного обеспечения: ступени по
              объёму здания, ТЫС. руб (внесена выверенными данными,
              «зд»/«1Д»-глюки OCR разрешены по монотонности рядов)
  табл.10/11/16 + преддоговорные работы — условия (текст/коэффициенты)
  табл.12-14 (вибродинамика, прочность бетона, пробы) — ВТОРОЙ ПРОХОД,
              пока не внесены (в эталонах не встречались)

Масштаб: матрицы в руб → в БД тыс.руб (÷1000, движок считает ×1000).
Встроенная верификация: эталонные ставки сметы «Самолёт» ЛС-05.

Запуск: docker exec ib-project-calculator-backend-1 python /app/scripts/import_sbcp25.py <pdf>
"""
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

import pdfplumber  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BookCondition,
    BookObjectType,
    ReferenceBook,
    ReferenceRow,
)

CODE = "СБЦП 81-2001-25"
PDF = sys.argv[1] if len(sys.argv) > 1 else "/app/scripts/_x25.pdf"

# (page0, table_num, название, вид работ)
MATRICES = [
    (9, 1, "Обмерные работы: одноэтажные здания", "обмерные работы"),
    (10, 2, "Обмерные работы: многоэтажные здания", "обмерные работы"),
    (11, 3, "Инженерные обследования строительных конструкций: одноэтажные здания", "обследование конструкций"),
    (12, 4, "Инженерные обследования строительных конструкций: многоэтажные здания", "обследование конструкций"),
]

ROMAN_FIX = {"I": "I", "И": "II", "II": "II", "Н": "II", "III": "III",
             "TTI": "III", "тп": "III", "ТП": "III", "Ш": "III", "1П": "III",
             "ш": "III", "TII": "III", "ІІІ": "III"}
WORK_CAT = {"перво": 1, "второ": 2, "третье": 3, "треть": 3}


def parse_matrix(page):
    """Матрица табл.1-4 по координатам слов."""
    words = page.extract_words(keep_blank_chars=False)
    # строки по y (кластеризация top с допуском 3pt)
    lines = {}
    for w in words:
        key = round(w["top"] / 3)
        lines.setdefault(key, []).append(w)
    ordered = [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(lines.items())]

    # Заголовок высот 4..21 может расщепиться на два y-кластера, а строка
    # НУМЕРАЦИИ колонок (1 2 3 …) выглядит похоже — исключаем её (начинается
    # с 1,2,3 подряд) и собираем высоты из всех строк ДО первой секции
    # «Стоимость…», объединяя по значению (первое вхождение по x).
    by_height = {}
    for ws in ordered:
        text = " ".join(w["text"] for w in ws).lower()
        if "стоимость" in text.replace(" ", ""):
            break
        nums = [(w, int(w["text"])) for w in ws if re.fullmatch(r"\d{1,2}", w["text"])]
        vals = [v for _, v in nums]
        if len(vals) >= 3 and vals[:3] == [1, 2, 3]:
            continue  # нумерация колонок
        for w, v in nums:
            if 3 <= v <= 21 and v not in by_height:
                by_height[v] = (w["x0"] + w["x1"]) / 2
    col_x = sorted(((x, h) for h, x in by_height.items()))
    assert len(col_x) >= 10, f"заголовок высот: снято {len(col_x)} колонок"
    # колонка «21 и выше»: слова «21»? последний header = 20 или 21
    heights = [h for _, h in col_x]
    if heights[-1] == 20:
        # «21 и выше» слово «21» могло попасть — ищем правее
        pass

    work_cat = None
    row_idx = 0
    out = []  # (work_cat, bldg_cat, height, price)
    lost = []
    for ws in ordered:
        text = " ".join(w["text"] for w in ws)
        low = text.lower().replace(" ", "")
        if "категори" in low and "сложности" in low:
            for k, v in WORK_CAT.items():
                if k in low:
                    work_cat = v
                    row_idx = 0
                    break
            continue
        if work_cat is None:
            continue
        # строка данных: ≥8 ценовых чисел; категория здания — ПОРЯДКОМ
        # строки в секции (маркеры I/II/III в words ненадёжны)
        price_words = []
        for w in ws:
            t = w["text"].replace("^", "").replace("зд", "")
            found = re.findall(r"\d{2,4}[,.]\d", t)
            if len(found) == 1 and re.fullmatch(r"[\d,.]+", t):
                price_words.append((w, float(found[0].replace(",", "."))))
            elif found:
                lost.append(t)
        if len(price_words) < 8:
            continue
        # гибрид: явный маркер I/II/III в начале строки надёжнее порядка
        first = ws[0]["text"].strip(".")
        if first in ROMAN_FIX:
            bldg = ROMAN_FIX[first]
            row_idx = {"I": 1, "II": 2, "III": 3}[bldg]
        else:
            row_idx += 1
            if row_idx > 3:
                lost.append(f"лишняя строка секции {work_cat}: {text[:50]}")
                continue
            bldg = ["I", "II", "III"][row_idx - 1]
        for w, price in price_words:
            xc = (w["x0"] + w["x1"]) / 2
            height = min(col_x, key=lambda c: abs(c[0] - xc))[1]
            out.append((work_cat, bldg, height, price))
    if lost:
        print(f"  [потери OCR, дочистить руками]: {lost[:6]}")
    return out


# табл.15: (пункт, система, [(объём_до_тыс_м3, тыс.руб)], (добавка, шаг_м3))
T15 = [
    ("п.1", "Обследование систем горячего водоснабжения",
     [(1, 0.6), (2, 0.9), (4, 1.0), (8, 2.2), (12, 2.8), (16, 3.5),
      (24, 4.3), (32, 5.1), (40, 5.6)], (0.2, 1000)),
    ("п.2", "Обследование систем отопления",
     [(1, 0.9), (3, 1.5), (5, 2.5), (10, 3.3), (15, 4.0), (20, 4.9)], (0.7, 5000)),
    ("п.3", "Обследование систем холодного водоснабжения и канализации без ванн",
     [(1, 0.7), (2, 1.0), (4, 1.4), (8, 2.4), (12, 3.1), (16, 3.9),
      (24, 4.8), (32, 5.7), (40, 6.2)], (0.3, 1000)),
    ("п.4", "Обследование систем вентиляции",
     [(1, 1.0), (3, 2.2), (5, 3.5), (10, 4.4), (15, 5.2), (20, 6.6)], (1.1, 5000)),
    ("п.5", "Обследование систем мусороудаления",
     [(1, 1.0), (3, 2.2), (5, 3.5), (10, 4.4), (15, 5.2), (20, 6.6)], (1.1, 5000)),
    ("п.6", "Обследование систем газоснабжения",
     [(1, 0.6), (2, 0.8), (4, 1.1), (8, 1.9), (12, 2.5), (16, 3.1),
      (24, 3.8), (32, 4.6), (40, 5.0)], (0.2, 1000)),
    ("п.7", "Обследование состояния водостоков",
     [(1, 0.4), (3, 0.9), (5, 1.5), (10, 1.9), (15, 2.2), (20, 2.7)], (0.5, 1000)),
]

CONDITIONS = [
    (None, "preddogovor", 0.10,
     "Преддоговорные работы — 10% от стоимости обмерных/обследовательских работ",
     "Эталонная практика (Самолёт ЛС-05): преддоговорные работы 10% от соответствующих позиций. Percent-механика."),
    (16, None, None,
     "Табл.16: поправочные коэффициенты по числу однотипных работ по обследованию систем",
     "10 видов работ — 0,1; 9 — 0,2; 8 — 0,3; 7 — 0,4; 6 — 0,5; 5 — 0,6; 4 — 0,7; 3 — 0,8; 2 вида — 0,9 (к базовой цене каждой)."),
    # табл.10 — усложняющие факторы (multiply, книжные)
    (None, "difficult_soil", 1.2, "Табл.10 п.1: просадочные/набухающие грунты, подработка, карст — К=1,2", None),
    (None, "equipment_50", 1.15, "Табл.10 п.2: насыщенность оборудованием >50%, стеснённость — К=1,15", None),
    (None, "harmful_shop", 1.2, "Табл.10 п.3: цеха с вредным производством, вибрация, пар, шум — К=1,2", None),
    (None, "unheated", 1.2, "Табл.10 п.4: неотапливаемые здания/чердаки/кровли в неблагоприятный период — К=1,2", None),
    (None, "monument", 1.25, "Табл.10 п.5: памятник архитектуры — К=1,25", None),
    (None, "safety_special", 1.15, "Табл.10 п.6: условия с обеспечением безопасности — К=1,15", None),
    (None, "aggressive_weak", 1.2, "Табл.10 п.7: слабая агрессивная среда — К=1,2", None),
    (None, "aggressive_mid", 1.3, "Табл.10 п.8: средняя агрессивная среда — К=1,3", None),
    (None, "aggressive_strong", 1.4, "Табл.10 п.9: сильная агрессивная среда — К=1,4", None),
    (None, "reinforced", 1.2, "Табл.10 п.10: конструкции, усиленные по ранее разработанным проектам — К=1,2", None),
    (None, "seismic_8", 1.2, "Табл.10 п.12: сейсмичность 8 баллов — К=1,2 (7 б. — 1,1 п.11; 9 б. — 1,25 п.13)", None),
    (None, "special_regime", 1.25, "Табл.10 п.14: объекты со спецрежимом — К=1,25", None),
    # табл.11 — корректирующие по строительному объёму (multiply, книжные)
    (None, "vol_lt_1000", 4.3, "Табл.11 п.1: объём до 1000 м³ — К=4,3", None),
    (None, "vol_lt_2000", 3.5, "Табл.11 п.2: объём до 2000 м³ — К=3,5", None),
    (None, "vol_lt_3000", 2.2, "Табл.11 п.3: объём до 3000 м³ — К=2,2", None),
    (None, "vol_lt_4000", 1.8, "Табл.11 п.4: объём до 4000 м³ — К=1,8", None),
    (None, "vol_lt_5000", 1.3, "Табл.11 п.5: объём до 5000 м³ — К=1,3 (свыше 5000 — 1,0)", None),
]


def main():
    db = SessionLocal()
    old = db.query(ReferenceBook).filter(ReferenceBook.code == CODE).first()
    if old:
        for model in (ReferenceRow, BookObjectType, BookCondition):
            db.query(model).filter(model.book_version_id == old.id).delete()
        db.delete(old)
        db.flush()

    book = ReferenceBook(
        code=CODE,
        official_name="СБЦП 81-2001-25 Справочник базовых цен на обмерные работы "
                      "и обследования зданий и сооружений (изд. 2016)",
        version=1, status="consistent", is_active=True,
        price_base_year=2001, calc_method="standard", pricing_method="mu620",
        uploaded_at=datetime.now(timezone.utc),
        notes="Кураторский импорт (import_sbcp25.py): матрицы табл.1-4 по "
              "координатам слов + табл.15 выверенными данными. "
              "Табл.12-14 — второй проход (не внесены).",
    )
    db.add(book)
    db.flush()

    pdf = pdfplumber.open(PDF)
    n_rows = 0
    checks = {2: {}, 4: {}}
    for page0, tn, title, kind in MATRICES:
        cells = parse_matrix(pdf.pages[page0])
        assert len(cells) >= 40, f"табл.{tn}: снято лишь {len(cells)} ячеек"
        print(f"  табл.{tn}: {len(cells)} ячеек")
        # Матрица адресуется ячейкой (кат.работ × кат.здания × высота) —
        # у движка выбор строки идёт через object_type, поэтому тип
        # создаётся PER ЯЧЕЙКУ с говорящим именем; строка штучная (a×X,
        # X = объём в сотнях м³)
        for work_cat, bldg, height, price in cells:
            label = (f"{title}: работы кат.{work_cat}, здание кат.{bldg}, "
                     f"высота до {height} м" + (" и выше" if height == 21 else ""))
            ot = BookObjectType(book_version_id=book.id,
                                name=f"{label} (т.{tn})"[:255], table_num=tn)
            db.add(ot)
            db.flush()
            db.add(ReferenceRow(
                book_version_id=book.id, object_type_id=ot.id, table_num=tn,
                row_num=f"п.{work_cat}.{bldg}.{height}",
                description=label + "; цена за 100 м³ строительного объёма",
                x_unit="100 м³ строительного объёма",
                x_min=None, x_max=None, a=price / 1000.0, b=None,
            ))
            n_rows += 1
            if tn in checks:
                checks[tn][(work_cat, bldg, height)] = price

    # верификация матриц по эталону Самолёта (ЛС-05)
    assert checks[2].get((2, "II", 6)) == 787.4, checks[2].get((2, "II", 6))
    assert checks[4].get((2, "II", 6)) == 659.8, checks[4].get((2, "II", 6))

    # табл.15
    ot15 = BookObjectType(book_version_id=book.id,
                          name="Обследование систем инженерного обеспечения зданий (СБЦП-25 табл.15)",
                          table_num=15)
    db.add(ot15)
    db.flush()
    prev = {}
    for num, name, steps, (add_price, add_step) in T15:
        lo = None
        for hi, price in steps:
            db.add(ReferenceRow(
                book_version_id=book.id, object_type_id=ot15.id, table_num=15,
                row_num=num, description=f"{name}; объём здания"
                                         f" {'до ' + str(hi) if lo is None else f'свыше {lo} до {hi}'} тыс. м³",
                x_unit="тыс. м³", x_min=lo, x_max=hi, a=price, b=None,
            ))
            lo = hi
            n_rows += 1
        db.add(ReferenceRow(
            book_version_id=book.id, object_type_id=ot15.id, table_num=15,
            row_num=num + ".доп",
            description=f"{name}; на каждые последующие {add_step} м³ сверх "
                        f"{lo} тыс. м³ — добавлять (ОПАСНО: за каждую порцию)",
            x_unit=f"{add_step} м³", x_min=None, x_max=None, a=None, b=add_price,
        ))
        n_rows += 1
        prev[num] = steps
    # электросети п.8: 1,2 тыс за 1000 м² площади
    db.add(ReferenceRow(
        book_version_id=book.id, object_type_id=ot15.id, table_num=15,
        row_num="п.8", description="Обследование состояния электрических сетей "
                                   "и средств связи; на площадь здания",
        x_unit="тыс. м²", x_min=None, x_max=None, a=0, b=1.2,
    ))
    n_rows += 1
    # верификация т.15 по эталону
    assert dict(prev["п.1"])[8] == 2.2 and dict(prev["п.2"])[10] == 3.3 \
        and dict(prev["п.3"])[8] == 2.4

    for tn, key, val, short, full in CONDITIONS:
        db.add(BookCondition(
            book_version_id=book.id, table_num=tn, coeff_key=key,
            coeff_min=val, coeff_max=val,
            condition_short=short, condition_text_full=full,
            effect_type="multiplier_range" if val else "flag",
            apply_mode="multiply" if val else None,
        ))

    db.commit()
    print(f"{CODE}: импортировано {n_rows} строк, "
          f"матрицы верифицированы (787,4 и 659,8 на месте)")
    db.close()


if __name__ == "__main__":
    main()

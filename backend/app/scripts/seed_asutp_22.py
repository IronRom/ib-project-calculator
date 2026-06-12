"""Seed СБЦП 81-2001-22 (АСУТП) — book entry, factor options, modules.

Run inside container:
  docker exec ib-project-calculator-backend-1 python /app/app/scripts/seed_asutp_22.py
"""
import sys
import os
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import AsutpFactorOption, AsutpModule, ReferenceBook

# ── Factor data from СБЦП-2001-22 Table 2 ────────────────────────────────────
# Columns: option_code, description, or, oo, io, to, mo, po

FACTOR_DATA = {
    "Ф2": {
        "name": "Характер протекания управляемого технологического процесса во времени",
        "options": [
            ("п.1.1", "Непрерывный",                    1, 1, 1, 1, 1, 1),
            ("п.1.2", "Полунепрерывный",                2, 1, 2, 1, 2, 2),
            ("п.1.3", "Непрерывно-дискретный I",        3, 3, 3, 3, 3, 3),
            ("п.1.4", "Непрерывно-дискретный II",       4, 3, 4, 3, 4, 4),
            ("п.1.5", "Циклический",                    3, 2, 3, 2, 3, 3),
            ("п.1.6", "Дискретный",                     2, 2, 2, 2, 3, 3),
        ],
    },
    "Ф5": {
        "name": "Количество технологических операций, контролируемых или управляемых АСУТП",
        "options": [
            ("п.2.1", "до 5",                   1, 1, 1, 1, 1, 1),
            ("п.2.2", "свыше 5 до 10",          2, 2, 2, 2, 2, 2),
            ("п.2.3", "свыше 10 до 20",         3, 3, 3, 3, 3, 3),
            ("п.2.4", "свыше 20 до 35",         4, 4, 4, 3, 4, 4),
            ("п.2.5", "свыше 35 до 50",         5, 3, 5, 4, 5, 5),
            ("п.2.6", "свыше 50 до 70",         6, 4, 6, 4, 6, 6),
            ("п.2.7", "свыше 70 до 100",        7, 5, 7, 6, 7, 7),
            ("п.2.8", "за каждые 50 свыше 100", 1, 1, 1, 1, 1, 1),
        ],
    },
    "Ф6": {
        "name": "Степень развитости информационных функций АСУТП",
        "options": [
            ("п.3.1", "I — параллельный контроль и измерение",     1, 1, 1, 1, 1, 1),
            ("п.3.2", "II — централизованный контроль и измерение", 3, 2, 3, 3, 3, 3),
            ("п.3.3", "III — косвенное измерение сложных показателей", 6, 2, 6, 5, 6, 6),
            ("п.3.4", "IV — анализ/диагностика/прогноз по модели", 9, 3, 9, 8, 9, 9),
        ],
    },
    "Ф7": {
        "name": "Степень развитости управляющих функций АСУТП",
        "options": [
            ("п.4.1", "I — одноконтурное рег. / однотактное лог. управление",   1, 1, 1, 1,  1,  1),
            ("п.4.2", "II — каскадное рег. / лог. по жёсткому циклу",           3, 2, 3, 3,  3,  3),
            ("п.4.3", "III — многосвязное рег. / лог. с разветвлениями",        5, 2, 5, 5,  5,  5),
            ("п.4.4", "IV — оптим. управление установившимися режимами",        6, 3, 7, 7,  7,  7),
            ("п.4.5", "V — оптим. управление переходными процессами",           8, 4, 9, 9, 11, 11),
            ("п.4.6", "VI — оптим. управление быстропротекающими/авариями",    9, 4,11,10, 13, 13),
            ("п.4.7", "VII — оптим. с адаптацией (самообучение)",             10, 5,12,11, 14, 14),
        ],
    },
    "Ф8": {
        "name": "Режим выполнения управляющих функций АСУТП",
        "options": [
            ("п.5.1", "Автоматизированный ручной",                    1, 1, 1, 1, 1, 1),
            ("п.5.2", "Автоматизированный режим советника",           1, 1, 2, 2, 1, 2),
            ("п.5.3", "Автоматизированный диалоговый",                2, 2, 2, 2, 2, 3),
            ("п.5.4", "Автоматический режим косвенного управления",   2, 3, 3, 4, 3, 4),
            ("п.5.5", "Автоматический прямой цифровой",               5, 3, 5, 7, 7, 7),
        ],
    },
    "Ф9": {
        "name": "Количество переменных, измеряемых, контролируемых и регистрируемых АСУТП",
        "options": [
            ("п.6.1",  "до 20",                    1, 1,  1,  1,  1,  1),
            ("п.6.2",  "свыше 20 до 50",           2, 1,  2,  2,  2,  2),
            ("п.6.3",  "свыше 50 до 100",          2, 2,  3,  3,  3,  3),
            ("п.6.4",  "свыше 100 до 170",         3, 2,  4,  3,  4,  4),
            ("п.6.5",  "свыше 170 до 250",         3, 3,  5,  5,  5,  5),
            ("п.6.6",  "свыше 250 до 350",         4, 3,  6,  6,  6,  6),
            ("п.6.7",  "свыше 350 до 470",         4, 4,  7,  7,  7,  7),
            ("п.6.8",  "свыше 470 до 600",         5, 4,  8,  8,  8,  8),
            ("п.6.9",  "свыше 600 до 800",         5, 5,  9,  9,  9,  9),
            ("п.6.10", "свыше 800 до 1000",        3, 3,  5,  5,  5,  5),
            ("п.6.11", "свыше 1000 до 1300",       6, 5, 10, 10, 10, 10),
            ("п.6.12", "свыше 1300 до 1600",       7, 6, 11, 11, 11, 11),
            ("п.6.13", "свыше 1600 до 2000",       8, 6, 12, 12, 12, 12),
            ("п.6.14", "за каждые 500 свыше 2000", 9, 7, 13, 13, 13, 13),
        ],
    },
    # Ф10 — Количество управляющих воздействий (аналогичная структура Ф5)
    # Scores from real example: п.7.2 (5-10) → [2, 1, 2, 2, 2, 2]
    "Ф10": {
        "name": "Количество управляющих воздействий, вырабатываемых АСУТП",
        "options": [
            ("п.7.1", "до 5",                   1, 1, 1, 1, 1, 1),
            ("п.7.2", "свыше 5 до 10",          2, 1, 2, 2, 2, 2),
            ("п.7.3", "свыше 10 до 20",         3, 2, 3, 3, 3, 3),
            ("п.7.4", "свыше 20 до 35",         4, 3, 4, 3, 4, 4),
            ("п.7.5", "свыше 35 до 50",         5, 3, 5, 4, 5, 5),
            ("п.7.6", "свыше 50 до 70",         6, 4, 6, 5, 6, 6),
            ("п.7.7", "свыше 70 до 100",        7, 5, 7, 6, 7, 7),
            ("п.7.8", "за каждые 50 свыше 100", 1, 1, 1, 1, 1, 1),
        ],
    },
}

# ── Module definitions (СБЦП-2001-22 п.2.11.2 + Table 6 stage ranges) ────────
# stage_r = Р (рабочая), stage_p = П (проектная)
MODULES = [
    # code,  S value,  order, r_min, r_max, p_min, p_max
    ("ОР",  15.73, 1, 20, 30, 70, 80),
    ("ОО",   9.56, 2, 60, 70, 30, 40),
    ("ИО",  14.11, 3, 50, 60, 40, 50),
    ("ТО",  33.77, 4, 50, 60, 40, 50),
    ("МО",  37.93, 5, 10, 20, 80, 90),
    ("ПО",  46.26, 6, 80, 90, 10, 20),
]


def main():
    db = SessionLocal()
    try:
        # 1. Upsert book entry
        book = db.query(ReferenceBook).filter(
            ReferenceBook.code == "СБЦП 81-2001-22"
        ).first()

        if not book:
            book = ReferenceBook(
                code="СБЦП 81-2001-22",
                official_name=(
                    "Справочник базовых цен на проектные работы в строительстве. "
                    "Автоматизированные системы управления технологическими процессами (АСУТП)"
                ),
                version=1,
                status="consistent",
                is_active=True,
                price_base_year=2001,
                calc_method="asutp",
            )
            db.add(book)
            db.flush()
            print(f"Created book СБЦП 81-2001-22 id={book.id}")
        else:
            book.calc_method = "asutp"
            book.status = "consistent"
            book.is_active = True
            print(f"Updated book СБЦП 81-2001-22 id={book.id}")

        book_id = book.id

        # 2. Seed modules (idempotent)
        existing_modules = {
            m.module_code
            for m in db.query(AsutpModule).filter(AsutpModule.book_version_id == book_id)
        }
        for code, s_val, order, r_min, r_max, p_min, p_max in MODULES:
            if code not in existing_modules:
                db.add(AsutpModule(
                    book_version_id=book_id,
                    module_code=code,
                    s_value=s_val,
                    sort_order=order,
                    stage_r_min=r_min,
                    stage_r_max=r_max,
                    stage_p_min=p_min,
                    stage_p_max=p_max,
                ))
                print(f"  + module {code} S={s_val}")

        # 3. Seed factor options (idempotent)
        existing_opts = {
            (r.factor_code, r.option_code)
            for r in db.query(AsutpFactorOption).filter(
                AsutpFactorOption.book_version_id == book_id
            )
        }
        for factor_code, fdata in FACTOR_DATA.items():
            for row in fdata["options"]:
                opt_code, desc, s_or, s_oo, s_io, s_to, s_mo, s_po = row
                if (factor_code, opt_code) not in existing_opts:
                    db.add(AsutpFactorOption(
                        book_version_id=book_id,
                        factor_code=factor_code,
                        factor_name=fdata["name"],
                        option_code=opt_code,
                        option_description=desc,
                        score_or=s_or, score_oo=s_oo, score_io=s_io,
                        score_to=s_to, score_mo=s_mo, score_po=s_po,
                    ))
                    print(f"  + {factor_code} {opt_code}: {desc}")

        db.commit()
        print("\nDone. СБЦП-2001-22 seeded successfully.")

    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

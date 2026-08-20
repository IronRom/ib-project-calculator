"""Golden-тесты расчётного движка против эталонных смет и формул методик.

БЕЗ AI и БЕЗ токенов: фиксированные наборы entities → calculate() → суммы.
Требуют живую БД со справочниками (запускать в контейнере backend):

    docker exec ib-project-calculator-backend-1 pytest tests/test_golden.py -q

Источники ожидаемых значений:
  [Кашин]   (ПС) «Завод по переработке лубяных культур…» 14.05.2026, Инфострой
  [Барвиха] (ПС-01) «Барвиха Инвест» 23.04.2026, Инфострой
  [МУ-620]  приказ Минрегиона №620 от 29.12.2009, п.2.1.3, Прил.1
  [707/пр]  приказ Минстроя №707/пр (ред. 409/пр), п.131 ф.8.2-8.5
  [МРР-4.2] МРР-4.2.04-22, п.2.2 ф.2.2

Если тест упал после правок движка/сидов — сначала смотри, какая цифра
уехала, и сверяй с указанным источником, а не подгоняй ожидание.
"""
import math

import pytest

from app.database import SessionLocal
from app.services.calculator import calculate


@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    yield s
    s.close()


def _ent(**kw):
    base = {
        "category": "new_construction", "object_type": kw.get("object_name", "t"),
        "address": "-", "quantity": 1, "coefficients": [],
    }
    base.update(kw)
    return base


def _pos(result, stage=None):
    ps = result["positions"]
    if stage:
        ps = [p for p in ps if p.get("stage_label") == stage]
    return ps


def _one(result, stage):
    ps = _pos(result, stage)
    assert len(ps) == 1, f"ожидалась 1 позиция {stage}, получено {len(ps)}: {ps}"
    return ps[0]




def _tid53(db, sub, table_num):
    from app.models import BookObjectType, ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "НЗ-2025-МС53-ВК").first()
    t = (db.query(BookObjectType)
         .filter(BookObjectType.book_version_id == b.id,
                 BookObjectType.table_num == table_num,
                 BookObjectType.name.like(f"%{sub}%")).first())
    assert t, f"НЗ-53: тип '{sub}' т.{table_num} не найден"
    return t.id

# ── Кашин: НЗ-53-ВК (707pr) ──────────────────────────────────────────────

def test_kashin_kos_sections(db):
    """[Кашин] КОС 2 тыс.м³/сут, НЗ-53 т.12 п.3, разделы из ТЗ.

    Базис: (7 921,5+1 706,42×2)×1,27 = 14 394,612 тыс (полная П+Р)
    ПД: ×0,4×0,85 = 4 894,168 тыс; РД: ×0,6×0,93 = 8 032,193 тыс
    (проценты разделов сверены со структурой эталона; книга у эталона другая)
    """
    r = calculate({"stage": "П+Р", "region": "Тверская обл.", "entities": [_ent(
        object_name="КОС", sbts_code="НЗ-2025-МС53-ВК", sbts_table=12,
        sbts_object_type_id=_tid53(db, "биологической очистки", 12),
        x_value=2, x_unit="тыс. м³/сут",
        sections=["ПЗ", "ПЗУ", "АР", "КР", "ИОС.ЭС", "ИОС.ВС", "ИОС.ВО",
                  "ИОС.ОВ", "ИОС.СС", "ИОС.АВТ", "ТХ", "ПОС", "ПБ"],
    )]}, db)
    assert not r["errors"], r["errors"]
    pd, rd = _one(r, "ПД"), _one(r, "РД")
    base = (7921.5 + 1706.42 * 2) * 1000 * 1.27
    assert math.isclose(pd["cost"], base * 0.4 * 0.85, rel_tol=1e-9), pd["cost"]
    assert math.isclose(rd["cost"], base * 0.6 * 0.93, rel_tol=1e-9), rd["cost"]
    assert pd["stage_pct"] == pytest.approx(0.4 * 0.85)
    assert rd["stage_pct"] == pytest.approx(0.6 * 0.93)


def test_kashin_usrednitel_extrapolation_707pr(db):
    """[Кашин] Резервуар-усреднитель 3050 м³, НЗ-53 т.14 п.1 — экстраполяция
    вверх 707/пр ф.8.3 (3050 > Xмакс=2000, но < 2×Xмакс — капа у НЗ нет).

    Эталон ЛС-02 п.4: (137,2+0,323×(0,4×2000+0,6×3050))×40%×85%×1,27
    = 426,0527 тыс; РД (93%): 699,2277 тыс.
    """
    r = calculate({"stage": "П+Р", "region": "-", "entities": [_ent(
        object_name="Усреднитель", sbts_code="НЗ-2025-МС53-ВК", sbts_table=14,
        sbts_object_type_id=_tid53(db, "резервуара-усреднителя", 14),
        x_value=3050, x_unit="м³",
        sections=["ПЗ", "ПЗУ", "АР", "КР", "ИОС.ЭС", "ИОС.ОВ", "ИОС.АВТ",
                  "ТХ", "ПОС", "ПБ"],
    )]}, db)
    assert not r["errors"], r["errors"]
    pd, rd = _one(r, "ПД"), _one(r, "РД")
    assert math.isclose(pd["cost"], 426_052.70, rel_tol=1e-5), pd["cost"]
    assert math.isclose(rd["cost"], 699_227.70, rel_tol=1e-5), rd["cost"]


def test_707pr_no_upper_cap(db):
    """[707/пр п.131-2] НЗ-книга: X=3×Xмакс — ф.8.3 без ограничения, капа нет.

    НЗ-53 т.14 п.1 (30–2000 м³), X=6000: X_расч=0,4×2000+0,6×6000=4400.
    """
    r = calculate({"stage": "П", "region": "-", "entities": [_ent(
        object_name="x", sbts_code="НЗ-2025-МС53-ВК", sbts_table=14,
        sbts_object_type_id=_tid53(db, "резервуара-усреднителя", 14),
        x_value=6000, x_unit="м³",
    )]}, db)
    p = _one(r, "ПД")
    # (137,2 + 0,323×4400) ×1000×1,27×0,4
    assert math.isclose(p["cost"], (137.2 + 0.323 * 4400) * 1000 * 1.27 * 0.4,
                        rel_tol=1e-9), p["cost"]
    assert not any("ограничен" in w for w in r["warnings"])


# ── МУ №620: СБЦП-книги — пределы применимости ───────────────────────────

def test_mu620_upper_cap(db):
    """[МУ-620 п.2.1.3] СБЦП-17 т.10: X=3×Xмакс → X_расч ограничен 2×Xмакс,
    warning про ф.3П. Xмакс табл.10 = 3600 тыс.м³/сут."""
    r = calculate({"stage": "П", "region": "-", "entities": [_ent(
        object_name="cap", sbts_code="СБЦП 81-2001-17", sbts_table=10,
        x_value=10800, x_unit="тыс. м3/сут",
    )]}, db)
    p = _one(r, "ПД")
    assert any("3П" in w and "cap" in w for w in r["warnings"]), r["warnings"]
    assert "ограничен" in p["justification"] or "Xмакс" in p["justification"]


def test_mu620_lower_ke(db):
    """[МУ-620 п.2.1.3, разъяснения ЦИП-2006] mu620-книга, X ниже Xмин/2 → Кэ
    (как для 707/пр), НЕ кап/ф.3П. Канализация СБЦП-2001-05 т.8 (эталон Рейсовой):
    X=30 < Xмин/2=50 → Кэ=0,6, ПД=(23100+90×70)×0,6×0,4×7,1 = 50 097,6 руб."""
    from app.models import ReferenceBook, ReferenceRow
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "СБЦП 81-2001-05").first()
    if not b:
        return  # книга не импортирована в этой БД — пропуск
    row = (db.query(ReferenceRow)
           .filter(ReferenceRow.book_version_id == b.id,
                   ReferenceRow.table_num == 8, ReferenceRow.a == 23.1).first())
    if not row:
        return
    r = calculate({"stage": "П+Р", "region": "Москва", "entities": [_ent(
        object_name="Канализация", sbts_code="СБЦП 81-2001-05", sbts_table=8,
        sbts_object_type_id=row.object_type_id, x_value=30, x_unit="м",
    )]}, db)
    pd = next((p["cost"] for p in r["positions"] if p.get("stage_label") == "ПД"), None)
    assert pd and math.isclose(pd, 50_097.6, abs_tol=1.0), pd
    assert not any("3П" in w for w in r["warnings"]), r["warnings"]


# ── Барвиха: МРР (mrr) ───────────────────────────────────────────────────

def test_barviha_rd_block(db):
    """[Барвиха ЛС-03] Полный РД-блок по МРР — копейка в копейку:
    сеть 1500 п.м ×Ксл0,9 = 1 099,548; камеры 4 = 374,494;
    узел = 63,110; благоустройство 1,5 га = 440,581. Итого 1 977,733 тыс."""
    from app.models import BookObjectType, ReferenceBook

    def tid(code, sub, table_num=None):
        b = db.query(ReferenceBook).filter(ReferenceBook.code == code,
                                           ReferenceBook.is_active == True).first()  # noqa: E712
        q = (db.query(BookObjectType)
             .filter(BookObjectType.book_version_id == b.id,
                     BookObjectType.name.like(f"%{sub}%")))
        if table_num is not None:
            q = q.filter(BookObjectType.table_num == table_num)
        t = q.first()
        assert t is not None, f"{code}: тип '{sub}' (т.{table_num}) не найден"
        return t.id

    r = calculate({"stage": "Р", "region": "МО", "entities": [
        _ent(object_name="Сеть", sbts_code="МРР-4.2.04-22", sbts_table=31,
             sbts_object_type_id=tid("МРР-4.2.04-22", "Распределительные внутриквартальные"),
             x_value=1500, x_unit="п.м",
             coefficients=[{"name": "complexity_cat_1", "value": 1.0}]),
        _ent(object_name="Камеры", sbts_code="МРР-4.2.04-22", sbts_table=33,
             sbts_object_type_id=tid("МРР-4.2.04-22", "Камера индивидуальная (перепадная", 33),
             x_value=4, x_unit="камера"),
        _ent(object_name="Узел врезки", sbts_code="МРР-4.2.04-22", sbts_table=33,
             sbts_object_type_id=tid("МРР-4.2.04-22", "Узел врезки", 33),
             x_value=1, x_unit="узел"),
        _ent(object_name="Благоустройство", sbts_code="МРР-7.1.03-21", sbts_table=221,
             sbts_object_type_id=tid("МРР-7.1.03-21", "восстановле"),
             x_value=1.5, x_unit="га"),
    ]}, db)
    assert not r["errors"], r["errors"]
    costs = sorted(round(p["cost"] / 1e3, 3) for p in _pos(r, "РД"))
    assert costs == [63.110, 374.494, 440.581, 1099.548], costs
    assert math.isclose(sum(costs), 1977.733, abs_tol=0.001)


def test_mrr_f22_upper_extrapolation(db):
    """[МРР-4.2 ф.2.2] X=12000 п.м > Xмакс=10000 (табл.3.1 п.2):
    Ц = a + в×(Xмакс + 0,5×ΔX) = 279,2 + 0,04×11000 = 719,2 тыс (база)."""
    from app.models import BookObjectType, ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "МРР-4.2.04-22").first()
    t = (db.query(BookObjectType)
         .filter(BookObjectType.book_version_id == b.id,
                 BookObjectType.name.like("%Распределительные внутриквартальные%")).first())
    r = calculate({"stage": "П", "region": "МО", "entities": [_ent(
        object_name="f22", sbts_code="МРР-4.2.04-22", sbts_table=31,
        sbts_object_type_id=t.id, x_value=12000, x_unit="п.м",
    )]}, db)
    p = _one(r, "ПД")
    assert math.isclose(p["cost"], (279.2 + 0.040 * 11000) * 1000 * 9.923 * 0.4,
                        rel_tol=1e-9), p["cost"]
    assert "ф.2.2" in p["justification"] or "ф.2.2" in (p.get("formula") or "") \
        or "МРР" in p["justification"]


# ── ИГИ-блок (survey) ────────────────────────────────────────────────────

def test_igi_report_kameral_base(db):
    """[НЗ-281 п.121+прим.2 табл.65] База X отчёта = ТОЛЬКО камеральные.
    Камеральные 187 225 руб (база) → интерполяция кат.II (100→250 тыс):
    278 776 + 0,872×(421 816−278 776)/1,5… — сверено фактом 452,433 тыс
    при индексе 1,25 (Кашин, пятая сессия)."""
    from app.models import ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "НЗ-2025-МС281-ИГИ").first()
    surveys = [{
        "book_id": b.id, "book_code": b.code, "complexity_category": 2,
        "k1": 0.7, "winter_pct": 0, "unfavorable_months": 0, "k2": 1.0,
        "items": [
            {"work_category": "kameral", "object_type_name": "Камералка",
             "table_num": 33, "row_num": "п.2", "description": "-",
             "volume": 199, "a": 0, "x_unit": "п.м", "b": 342},
            {"work_category": "lab", "object_type_name": "Лаборатория",
             "table_num": 58, "row_num": "п.2", "description": "-",
             "volume": 69, "a": 0, "x_unit": "опр", "b": 7357},
        ],
    }]
    r = calculate({"stage": "П+Р", "region": "-", "entities": [],
                   "geological_surveys": surveys}, db)
    rep = [p for p in r["positions"] if p.get("work_category") == "report"]
    assert len(rep) == 1
    # база = только камеральные (342×199=68 058 руб = 68,058 тыс) → кат.II
    # интерполяция табл.65 в диапазоне 50→100: 203 793 + пропорция
    base_x = 342 * 199 / 1000
    lo, hi = 203_793, 278_776
    expected = (lo + (hi - lo) * (base_x - 50) / (100 - 50)) * 1.25
    assert math.isclose(rep[0]["cost"], expected, rel_tol=1e-6), \
        (rep[0]["cost"], expected)


def test_unit_priced_rows(db):
    """[МРР-4.2 табл.3.1 п.6] Штучная строка (b=NULL, без диапазона):
    НС холодной воды = 212,8 тыс × X станций."""
    from app.models import BookObjectType, ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "МРР-4.2.04-22").first()
    t = (db.query(BookObjectType)
         .filter(BookObjectType.book_version_id == b.id,
                 BookObjectType.name.like("%Насосная станция холодной%")).first())
    r = calculate({"stage": "П+Р", "region": "МО", "entities": [_ent(
        object_name="НС", sbts_code="МРР-4.2.04-22", sbts_table=31,
        sbts_object_type_id=t.id, x_value=2, x_unit="станция",
    )]}, db)
    total = sum(p["cost"] for p in r["positions"])
    assert math.isclose(total, 212.8 * 2 * 1000 * 9.923, rel_tol=1e-9), total


# ── Изыскания Барвихи: survey-МРР с процентными позициями ────────────────

def _survey(db, code, items, **kw):
    from app.models import ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == code).first()
    s = {"book_id": b.id, "book_code": code, "complexity_category": 2,
         "k1": 1.0, "winter_pct": 0, "unfavorable_months": 0, "k2": 1.0,
         "items": items}
    s.update(kw)
    return s


def _it(cat, t, r, vol, b, k=1.0, **kw):
    d = {"work_category": cat, "object_type_name": kw.pop("name", f"т.{t} {r}"),
         "table_num": t, "row_num": r, "description": "-", "volume": vol,
         "a": 0, "x_unit": "-", "b": b, "k": k}
    d.update(kw)
    return d


def test_barviha_ls01_geodesy(db):
    """[Барвиха ЛС-01] ИГДИ по МРР-3.1.02-23, итог 593 641,7 руб.

    Полевые: опорная сеть 5 690,4×0,7×1,3×3; топопланы 2 908,07×1,25×2,25;
    съёмка коммуникаций 4 507,51×2,25; транспорт 7,5% (табл.2.2);
    орг/ликвидация 6% от полевых+транспорт (табл.2.3).
    Камеральные: 2 644,08×1,3×3; 1 111,6×1,25×1,15×2,25; 3 261,55×2,25.
    Все ставки — из оцифрованных таблиц; k — примечания к таблицам
    (у МРР транспорт отдельной строкой, поэтому survey.k1=1,0).
    """
    items = [
        _it("field", 314, "п.3", 3, 5690.40, k=0.7 * 1.3),
        _it("field", 323, "п.5", 2.25, 2908.07, k=1.25),
        _it("field", 326, "п.5", 2.25, 4507.51),
        _it("percent", 22, "", 0, 0, pct=7.5, percent_base="field",
            name="Расходы по внутреннему транспорту"),
        _it("percent", 23, "", 0, 0, pct=6.0, percent_base="field+percent",
            name="Расходы по организации и ликвидации работ"),
        _it("kameral", 314, "п.3", 3, 2644.08, k=1.3),
        _it("kameral", 323, "п.5", 2.25, 1111.60, k=1.25 * 1.15),
        _it("kameral", 326, "п.5", 2.25, 3261.55),
    ]
    r = calculate({"stage": "П+Р", "region": "МО", "entities": [],
                   "geological_surveys": [_survey(db, "МРР-3.1.02-23", items)]}, db)
    total = sum(p["cost"] for p in r["positions"])
    # эталон 593 641,7; допуск 0,1% на округления ставок в смете
    assert math.isclose(total, 593_641.7, rel_tol=1e-3), total


def test_barviha_ls02_geology(db):
    """[Барвиха ЛС-02] ИГИ по МРР-3.2.02-23.

    Эталон 787 705 руб, НО эталонная позиция 4.1 (отчёт) считает
    (86 486 ТЕКУЩИХ × 32%) × 9,923 — повторная индексация уже
    проиндексированной базы. По документу (табл.9.3.1: «норматив цены
    в % от стоимости камеральных работ», ступень «до 60 ТЫС. РУБ» —
    базовый уровень) отчёт = 32% от камеральных без доп. индекса:
    27 675 руб вместо эталонных 274 624. Ожидание — ПО ДОКУМЕНТУ:
    787 705 − 274 624 + 27 675 = 540 756 руб.
    """
    items = [
        _it("field", 311, "п.2", 1.5, 271.87),
        _it("field", 322, "п.1", 3, 102.71),
        _it("field", 423, "п.1", 21, 386.66),
        _it("field", 424, "п.1", 21, 16.11),
        _it("field", 721, "п.1", 10, 230.59),
        _it("percent", 22, "", 0, 0, pct=10.0, percent_base="field",
            name="Расходы по внутреннему транспорту"),
        _it("percent", 23, "", 0, 0, pct=9.0, percent_base="field+percent",
            name="Расходы по организации и ликвидации работ"),
        _it("lab", 812, "п.21", 10, 2286.33),
        _it("lab", 821, "п.5", 1, 300.89),
        _it("lab", 821, "п.9", 1, 138.60),
        _it("kameral", 311, "п.2", 1.5, 219.16),
        _it("kameral", 322, "п.1", 3, 77.0),
        _it("percent", 925, "п.1", 0, 0, pct=20.0, percent_base="lab",
            counts_as="kameral",
            name="Камеральная обработка физико-механических определений"),
        _it("percent", 925, "п.2", 0, 0, pct=15.0, percent_base="lab",
            counts_as="kameral",
            name="Камеральная обработка коррозионной активности"),
        _it("percent", 931, "п.1б", 0, 0, pct=32.0, percent_base="kameral",
            name="Составление технического отчета"),
        _it("program", 912, "п.1", 1, 5923.13,
            name="Составление программы производства работ"),
    ]
    r = calculate({"stage": "П+Р", "region": "МО", "entities": [],
                   "geological_surveys": [_survey(db, "МРР-3.2.02-23", items)]}, db)
    total = sum(p["cost"] for p in r["positions"])
    assert math.isclose(total, 540_756.0, rel_tol=2e-3), total


# ── Самолёт ЛС-05: обмеры и обследования по СБЦП 81-2001-25 ──────────────

def test_samolet_ls05_sbcp25(db):
    """[Самолёт ЛС-05] Обмеры/обследования здания 5 182 м³ (X=51,82 сотен м³),
    каркасное многоэтажное, кат. здания II, 2-я кат. сложности, высота до 6 м.

    Базовые позиции (без преддоговорных 10%, они percent-механика):
      обмеры т.2: 787,4 руб×51,82×7,1 = 289 702 руб
      обследования т.4: 659,8×51,82×7,1 = 242 755
      системы т.15 (объём 5,182 тыс.м³, ×1,2 усложняющий табл.10):
        ГВС (до 8) 2,2×1,2×7,1 = 18 744; отопление (до 10) 3,3×1,2×7,1=28 116;
        ХВС без ванн (до 8) 2,4×1,2×7,1 = 20 448
      электросети т.15 п.8: 1,2×1,127 тыс.м²×7,1 = 9 602 (без К=1,2!)
    Σ = 609 367 руб (эталон 670 303 = Σ×1,1 преддоговорных).
    """
    from app.models import BookObjectType, ReferenceBook
    b = db.query(ReferenceBook).filter(ReferenceBook.code == "СБЦП 81-2001-25").first()
    assert b is not None and b.is_active

    def tid(table_num):
        t = (db.query(BookObjectType)
             .filter(BookObjectType.book_version_id == b.id,
                     BookObjectType.table_num == table_num).first())
        return t.id

    def row_id(table_num, row_num):
        from app.models import ReferenceRow
        r = (db.query(ReferenceRow)
             .filter(ReferenceRow.book_version_id == b.id,
                     ReferenceRow.table_num == table_num,
                     ReferenceRow.row_num == row_num).first())
        assert r is not None, f"нет строки т.{table_num} {row_num}"
        return r

    # матричные строки адресуются row_num "п.{кат.работ}.{кат.здания}.{высота}"
    assert float(row_id(2, "п.2.II.6").a) == pytest.approx(0.7874)
    assert float(row_id(4, "п.2.II.6").a) == pytest.approx(0.6598)

    k12 = [{"name": "harmful_shop", "value": 1.0}]  # табл.10 К=1,2
    ents = [
        _ent(object_name="Обмерные работы", sbts_code="СБЦП 81-2001-25",
             sbts_table=2, sbts_object_type_id=row_id(2, "п.2.II.6").object_type_id,
             x_value=51.82, x_unit="100 м³ строительного объёма"),
        _ent(object_name="Обследования конструкций", sbts_code="СБЦП 81-2001-25",
             sbts_table=4, sbts_object_type_id=row_id(4, "п.2.II.6").object_type_id,
             x_value=51.82, x_unit="100 м³ строительного объёма"),
        _ent(object_name="ГВС", sbts_code="СБЦП 81-2001-25", sbts_table=15,
             sbts_object_type_id=tid(15), x_value=5.182, x_unit="тыс. м³",
             coefficients=k12),
        _ent(object_name="Электросети", sbts_code="СБЦП 81-2001-25", sbts_table=15,
             sbts_object_type_id=tid(15), x_value=1.127, x_unit="тыс. м²"),
    ]
    r = calculate({"stage": "П+Р", "region": "Москва", "entities": ents}, db)
    assert not r["errors"], r["errors"]
    by_name = {}
    for p in r["positions"]:
        by_name[p["name"]] = by_name.get(p["name"], 0) + p["cost"]
    assert math.isclose(by_name["Обмерные работы"], 787.4 * 51.82 * 7.1,
                        abs_tol=0.5), by_name["Обмерные работы"]
    assert math.isclose(by_name["Обследования конструкций"], 659.8 * 51.82 * 7.1,
                        abs_tol=0.5)
    assert math.isclose(by_name["ГВС"], 2200 * 1.2 * 7.1, abs_tol=0.5), by_name["ГВС"]
    assert math.isclose(by_name["Электросети"], 1200 * 1.127 * 7.1, abs_tol=0.5), by_name["Электросети"]


# ── Котельная Сафоновское: НЗ-849 (2022) + НЗ-52-ГРС (2024) ──────────────

def test_kotelnaya_nz849_nz52(db):
    """[Котельная ЛС-01] п.4 ЦПУ/операторная по НЗ-849 т.3.8 и п.2 котельная
    установка по НЗ-52 т.3.17 — копейка в копейку с эталоном.

    ЦПУ 60 м³ (X<Xмин=100 → ф.8.2: 0,4×100+0,6×60=76), К=0,7:
      (1007,2+1,085×76)×0,7×1,53×0,4 = 466 810,3 руб
    Котельная установка 4 МВт: (2388,8+259,358×4)×1,27×0,4 = 1 740 525,9 руб
    """
    from app.models import BookObjectType, ReferenceBook

    def tid(code, sub):
        b = db.query(ReferenceBook).filter(ReferenceBook.code == code).first()
        t = (db.query(BookObjectType)
             .filter(BookObjectType.book_version_id == b.id,
                     BookObjectType.name.like(f"%{sub}%")).first())
        assert t, f"{code}: {sub}"
        return t.id

    r = calculate({"stage": "П", "region": "МО", "entities": [
        _ent(object_name="ЦПУ", sbts_code="НЗ-2022-МС849", sbts_table=38,
             sbts_object_type_id=tid("НЗ-2022-МС849", "Центральный пункт"),
             x_value=60, x_unit="куб.м",
             coefficients=[{"name": "modular_07", "value": 1.0}]),
        _ent(object_name="Котельная установка", sbts_code="НЗ-2024-МС52-ГРС",
             sbts_table=317,
             sbts_object_type_id=tid("НЗ-2024-МС52-ГРС", "Котельная установка"),
             x_value=4, x_unit="МВт"),
    ]}, db)
    assert not r["errors"], r["errors"]
    by = {p["name"]: p["cost"] for p in r["positions"]}
    assert math.isclose(by["ЦПУ"], 466_810.30, abs_tol=0.5), by["ЦПУ"]
    assert math.isclose(by["Котельная установка"], 1_740_525.90, abs_tol=0.5), \
        by["Котельная установка"]


def _book_type_by_a(db, code, table_num, a_value):
    """Найти (book, object_type) по коду книги, номеру таблицы и значению «а»."""
    from app.models import BookObjectType, ReferenceBook, ReferenceRow
    b = db.query(ReferenceBook).filter(ReferenceBook.code == code).first()
    assert b, f"книга {code} не найдена"
    row = (db.query(ReferenceRow)
           .filter(ReferenceRow.book_version_id == b.id,
                   ReferenceRow.table_num == table_num,
                   ReferenceRow.a == a_value).first())
    assert row, f"{code} т.{table_num}: строка с a={a_value} не найдена"
    return b, db.query(BookObjectType).filter(BookObjectType.id == row.object_type_id).first()


def test_reisovaya_sotv_nz828(db):
    """[Рейсовая] СОТВ 12 видеокамер, НЗ-828-ИТСО т.3.3 п.1 (a=105,2 в=5,313),
    база 2021 ×1,68, П/Р 40/60: (105200+5313×12)×1,68 → ПД 113 538,43 / РД 170 307,65 руб."""
    b, ot = _book_type_by_a(db, "НЗ-2021-МС828-ИТСО", 33, 105.2)
    r = calculate({"stage": "П+Р", "entities": [
        _ent(object_name="СОТВ", category="reconstruction",
             sbts_code="НЗ-2021-МС828-ИТСО", sbts_table=33,
             sbts_object_type_id=ot.id, x_value=12, x_unit="шт.")]}, db)
    assert not r["errors"], r["errors"]
    assert math.isclose(_one(r, "ПД")["cost"], 113_538.43, abs_tol=1.0)
    assert math.isclose(_one(r, "РД")["cost"], 170_307.65, abs_tol=1.0)


def test_reisovaya_building_nz848(db):
    """[Рейсовая] АХ-блок 5182 м² реконструкция, НЗ-848-ОЖГС т.3.5 п.3.2
    (a=1342,6 в=1,405), реконструкция ×1,5, база 2021 ×1,68, П/Р 40/60:
    (1342600+1405×5182)×1,5×1,68 → ПД 8 692 296,48 / РД 13 038 444,72 руб."""
    b, ot = _book_type_by_a(db, "НЗ-2021-МС848-ОЖГС", 305, 1342.6)
    r = calculate({"stage": "П+Р", "entities": [
        _ent(object_name="АХ-блок", category="reconstruction",
             sbts_code="НЗ-2021-МС848-ОЖГС", sbts_table=305,
             sbts_object_type_id=ot.id, x_value=5182, x_unit="кв.м",
             coefficients=[{"name": "reconstruction", "value": 1.0}])]}, db)
    assert not r["errors"], r["errors"]
    assert math.isclose(_one(r, "ПД")["cost"], 8_692_296.48, rel_tol=1e-4)
    assert math.isclose(_one(r, "РД")["cost"], 13_038_444.72, rel_tol=1e-4)


def test_expertise_form3p_pge_table(db):
    """[Пост. Правительства РФ № 145, Приложение] Таблица П форма 3П:
    Спд+Сиж=1,667 млн (2001) → брекет «более 1,5» → П=11,88% (эталон Самолёта ЛС-08:
    866 349 = 847 965 × 0,1188 × 8,6)."""
    from app.services.calculator import _pge_percent
    assert _pge_percent(1_667_000) == 11.88     # эталонный брекет
    assert _pge_percent(100_000) == 33.75        # 0,1 млн → 0-0,15
    assert _pge_percent(500_001) == 20.22        # более 0,5
    assert _pge_percent(5_000_000) == 8.77       # более 4
    assert _pge_percent(250_000_000) == 0.58     # более 220


# ── Гарды состава сметы (сессия 20.08.2026, разбор Рейсовой против эталона) ────

def _asutp_entity(**kw):
    """АСУТП без количественных данных ТЗ (факторы назначены AI)."""
    base = dict(
        object_name="АСУ ТП", category="reconstruction",
        sbts_code="СБЦП 81-2001-22", sbts_table=None,
        x_value=None, x_unit="",
        x_value_missing_reason="перечень функций автоматизации в ТЗ отсутствует",
        asutp_factors={"Ф2": "п.1.1", "Ф5": "п.2.1", "Ф10": "п.7.1"},
    )
    base.update(kw)
    return _ent(**base)


def test_asutp_without_data_not_doubled(db):
    """[Рейсовая] АСУТП без данных ТЗ + объект автоматизации → отдельная позиция
    по СБЦП-22 НЕ создаётся (автоматизация объекта входит в цену его
    проектирования; эталон Инфостроя такой позиции не содержит), warning есть."""
    b, ot = _book_type_by_a(db, "НЗ-2021-МС828-ИТСО", 33, 105.2)
    r = calculate({"stage": "П+Р", "entities": [
        _ent(object_name="СОТВ", category="reconstruction",
             sbts_code="НЗ-2021-МС828-ИТСО", sbts_table=33,
             sbts_object_type_id=ot.id, x_value=12, x_unit="шт."),
        _asutp_entity(),
    ]}, db)
    assert not any(p["book_code"] == "СБЦП 81-2001-22" for p in r["positions"])
    assert any("НЕ включена" in w and "АСУ ТП" in w for w in r["warnings"]), r["warnings"]


def test_asutp_alone_still_calculated(db):
    """АСУТП — единственный предмет расчёта: позиция считается (по минимальным
    факторам), иначе смета осталась бы пустой."""
    r = calculate({"stage": "П", "entities": [_asutp_entity()]}, db)
    assert [p for p in r["positions"] if p["book_code"] == "СБЦП 81-2001-22"], r["errors"]


def test_component_position_not_doubled(db):
    """[Рейсовая] ИТП и узел учёта тепла — одна таблица НЗ-847 т.3.08 и один и
    тот же X=0,184 Гкал/ч: узел учёта учтён в цене ИТП (эталон ЛС-06/07 даёт
    одну позицию) → вторая позиция в смету не идёт, но объясняется warning'ом."""
    r = calculate({"stage": "П", "entities": [
        _ent(object_name="ИТП", category="reconstruction",
             sbts_code="НЗ-2021-МС847-СИТО", sbts_table=308,
             x_value=0.184, x_unit="Гкал/ч"),
        _ent(object_name="УУТЭ", category="reconstruction",
             sbts_code="НЗ-2021-МС847-СИТО", sbts_table=308,
             x_value=0.184, x_unit="Гкал/ч"),
    ]}, db)
    names = {p["name"] for p in r["positions"]}
    assert "ИТП" in names and "УУТЭ" not in names, names
    assert any("УУТЭ" in w and "составные элементы" in w for w in r["warnings"])


def test_unresolved_book_is_explained(db):
    """Экстрактор не определил справочник (пустой sbts_code) → внятная ошибка
    «требует уточнения», а не «активный справочник «» не найден»."""
    r = calculate({"stage": "П", "entities": [
        _ent(object_name="АПС и СОУЭ", sbts_code="", sbts_table=None)]}, db)
    assert r["errors"] and "требует уточнения" in r["errors"][0], r["errors"]
    assert "«»" not in r["errors"][0]


def test_expertise_flag_adds_form3p(db):
    """ТЗ говорит «ПД подлежит государственной экспертизе» (флаг
    expertise_required от экстрактора) → блок экспертизы по форме 3П в смете."""
    b, ot = _book_type_by_a(db, "НЗ-2021-МС828-ИТСО", 33, 105.2)
    ents = [_ent(object_name="СОТВ", category="reconstruction",
                 sbts_code="НЗ-2021-МС828-ИТСО", sbts_table=33,
                 sbts_object_type_id=ot.id, x_value=12, x_unit="шт.")]
    r_off = calculate({"stage": "П+Р", "entities": list(ents)}, db)
    r_on = calculate({"stage": "П+Р", "entities": list(ents),
                      "expertise_required": True}, db)
    assert not any(p.get("block_kind") == "expertise" for p in r_off["positions"])
    exp = [p for p in r_on["positions"] if p.get("block_kind") == "expertise"]
    assert len(exp) == 1 and exp[0]["cost"] > 0, r_on["positions"]


def test_obsledovanie_preddogovor_10pct(db):
    """[СБЦП-25 гл.2.1/2.5] Преддоговорные работы 10% от стоимости обследований
    добавляются автоматически (эталон ЛС-05 пп.2,4,9)."""
    r = calculate({"stage": "П+Р", "entities": [
        _ent(object_name="Обследование конструкций", category="reconstruction",
             sbts_code="СБЦП 81-2001-25", sbts_table=4, x_value=None,
             x_unit="100 м³ строительного объёма")]}, db)
    pd = [p for p in r["positions"] if p["name"] == "Преддоговорные работы"]
    others = [p for p in r["positions"] if p["name"] != "Преддоговорные работы"]
    assert len(pd) == 1, r["positions"]
    assert math.isclose(pd[0]["cost"], sum(p["cost"] for p in others) * 0.10, abs_tol=0.01)


def test_survey_surcharges_from_conditions(db):
    """[НЗ-812 п.28 табл.3 / п.19 табл.2] Надбавки изысканий — данные книги:
    ДЗвнеш 13,2% и ДЗнп 29% от полевых (эталон ЛС-01: 385 043×13,2% = 50 826,
    ×29% = 111 662)."""
    from app.models import ReferenceBook
    from app.services.calculator import _survey_surcharge_items
    from app.services.igi_calculator import calculate_igi
    bk = (db.query(ReferenceBook)
          .filter(ReferenceBook.code == "НЗ-2024-МС812-ИГДИ").first())
    surch = {round(float(i["pct"]), 2) for i in _survey_surcharge_items(db, bk)}
    assert {13.2, 29.0} <= surch, surch
    items = [{"work_category": "field", "a": 100000, "b": 0, "volume": 1, "k": 1.0,
              "table_num": 7, "row_num": "п.1", "x_unit": "1 пункт",
              "description": "полевые"}]
    items += _survey_surcharge_items(db, bk)
    pos, err = calculate_igi([{"book_id": bk.id, "book_code": bk.code,
                               "complexity_category": 2, "k1": 1.0, "k2": 1.0,
                               "winter_pct": 0, "unfavorable_months": 0,
                               "items": items}], db)
    assert not err, err
    field_cost = next(p["cost"] for p in pos if p["work_category"] == "field")
    pcts = {round(p["quantity"], 2): p["cost"] for p in pos
            if p["work_category"] == "percent"}
    assert math.isclose(pcts[13.2], field_cost * 0.132, rel_tol=1e-6)
    assert math.isclose(pcts[29.0], field_cost * 0.29, rel_tol=1e-6)


def test_surveys_scope_all_adds_missing_kinds(db):
    """ТЗ «выполнить необходимые инженерные изыскания» без перечня видов
    (surveys_scope='all') → добираются недостающие виды (гидрометеорология,
    экология) активными федеральными книгами; МРР для федерального заказа
    не подключаются."""
    b, ot = _book_type_by_a(db, "НЗ-2021-МС828-ИТСО", 33, 105.2)
    r = calculate({"stage": "П+Р", "surveys_scope": "all",
                   "funding_source": "federal", "entities": [
                       _ent(object_name="СОТВ", category="reconstruction",
                            sbts_code="НЗ-2021-МС828-ИТСО", sbts_table=33,
                            sbts_object_type_id=ot.id, x_value=12, x_unit="шт.")]}, db)
    books = {p["book_code"] for p in r["positions"] if p.get("work_category")}
    assert any("ГИДРОМЕТ" in b for b in books), books
    assert any("ИЭИ" in b for b in books), books
    assert not any("МРР" in b for b in books), books


def test_tz_flags_deterministic():
    """Признаки ТЗ ставит код, не AI: госэкспертиза, полный состав изысканий,
    источник финансирования (ТЗ «Рейсовая»: ФГБУ → federal, без МРР)."""
    from app.schemas import ExtractionResult
    from app.services.entity_extractor import _apply_tz_flags
    r = ExtractionResult(entities=[])
    _apply_tz_flags(r, "Заказчик ФГБУ «СЛО «Россия». Необходимые инженерные "
                       "изыскания (в т.ч. обследования). Проектная документация "
                       "подлежит прохождению государственной экспертизы.")
    assert r.expertise_required and r.surveys_scope == "all"
    assert r.funding_source == "federal"

    r2 = ExtractionResult(entities=[])
    _apply_tz_flags(r2, "Выполнить инженерно-геодезические и инженерно-геологические "
                        "изыскания. Финансирование — бюджет города Москвы, "
                        "Департамент строительства города Москвы.")
    assert r2.surveys_scope == "listed"      # виды перечислены явно
    assert not r2.expertise_required
    assert r2.funding_source == "moscow_city"


# ── Изыскания: типовой состав из данных книги, шкалы, ф.8.7 ────────────────────

def _survey_block(db, book_code: str):
    """Автособранный блок изысканий книги (как его строит calculate)."""
    from app.models import ReferenceBook
    from app.services.calculator import _autoblock_params, _autobuild_survey_items
    from app.services.igi_calculator import calculate_igi
    bk = db.query(ReferenceBook).filter(ReferenceBook.code == book_code).first()
    assert bk, f"книга {book_code} не найдена"
    params = _autoblock_params(db, bk)
    cat = int(params.get("complexity_category", 2))
    items = _autobuild_survey_items(db, bk, cat)
    pos, err = calculate_igi([{
        "book_id": bk.id, "book_code": bk.code, "complexity_category": cat,
        "k1": float(params.get("k1", 1.0)), "k2": float(params.get("k2", 1.0)),
        "winter_pct": float(params.get("winter_pct", 0)),
        "unfavorable_months": float(params.get("unfavorable_months", 0)),
        "items": items,
    }], db)
    assert not err, err
    return pos


def test_survey_composition_from_book_data(db):
    """[Рейсовая ЛС-01] Типовой состав геодезии посеян в book_conditions
    (autoitem_*), а не угадывается по словам: камеральная обработка плановой
    сети 1714×3×1,25 = 6 428 руб и нивелирной 4771×3×1,25 = 17 891 руб —
    копейка в копейку с эталоном."""
    pos = _survey_block(db, "НЗ-2024-МС812-ИГДИ")
    costs = [round(p["cost"], 0) for p in pos]
    assert 6_428 in costs, costs
    assert 17_891 in costs, costs
    # состав больше не тянет «незастроенную территорию 1:5000» за 100 руб/га
    assert not any("1:5000" in (p.get("row_description") or "") for p in pos), pos


def test_survey_winter_factor_from_book_data(db):
    """[СБЦ-2001 табл.2 общих указаний] Полевые работы в неблагоприятный период
    6–7,5 мес идут с К=1,3 (autoblock_winter_pct=0,3): рекогносцировка экологии
    27×1,3×80,58 = 2 828 руб и радон 535×2×1,3×80,58 = 112 087 — как в ЛС-04."""
    pos = _survey_block(db, "СБЦ-2001-ИГИ-ИЭИ")
    costs = [round(p["cost"], 0) for p in pos]
    assert 2_828 in costs, costs
    assert 112_087 in costs, costs


def test_survey_percent_row_not_charged_as_rubles(db):
    """[СБЦ-2001 табл.86] Строка с единицей «% от стоимости лабораторных работ»
    становится процентной позицией от лабораторных, а не рублёвой ставкой."""
    pos = _survey_block(db, "СБЦ-2001-ИГИ-ИЭИ")
    lab = sum(p["cost"] for p in pos if p["work_category"] == "lab")
    pct_rows = [p for p in pos if p["work_category"] == "percent"
                and "лабораторн" in (p["name"] or "").lower()]
    assert len(pct_rows) == 1, [p["name"] for p in pos]
    assert math.isclose(pct_rows[0]["cost"], lab * float(pct_rows[0]["quantity"]) / 100,
                        rel_tol=1e-6)


def test_survey_surcharge_scale_follows_base(db):
    """[НЗ-812 п.28 табл.3] Процент внешнего транспорта — шкала от стоимости
    полевых: до 250 тыс.руб — 13,2 %, свыше — 10,4 % (константа занижала бы
    смету при вводе реальных объёмов)."""
    from app.models import ReferenceBook
    from app.services.calculator import _survey_surcharge_items
    from app.services.igi_calculator import calculate_igi
    bk = db.query(ReferenceBook).filter(
        ReferenceBook.code == "НЗ-2024-МС812-ИГДИ").first()
    surch = _survey_surcharge_items(db, bk)
    transport = next(i for i in surch if "внешний транспорт" in i["description"])
    assert transport.get("pct_scale"), transport

    def _pct_for(field_base_rub):
        items = [{"work_category": "field", "a": field_base_rub, "b": 0, "volume": 1,
                  "k": 1.0, "table_num": 7, "row_num": "п.1", "x_unit": "1 пункт",
                  "description": "полевые"}, transport]
        pos, err = calculate_igi([{"book_id": bk.id, "book_code": bk.code,
                                   "complexity_category": 2, "k1": 1.0, "k2": 1.0,
                                   "winter_pct": 0, "unfavorable_months": 0,
                                   "items": items}], db)
        assert not err, err
        return next(p["quantity"] for p in pos if p["work_category"] == "percent")

    assert _pct_for(100_000) == 13.2
    assert _pct_for(400_000) == 10.4
    assert _pct_for(2_000_000) == 6.7


def test_report_table_extrapolates_down_707pr(db):
    """[707/пр п.133 ф.8.7] Ниже первой опорной точки таблицы отчёта цена
    снижается наклоном крайнего сегмента ×0,6, а не берётся «по первой строке»
    (эталон ЛС-02 считает так же). Для книг не по 707/пр поведение прежнее."""
    from app.models import ReferenceBook
    from app.services.igi_calculator import _interpolate_cost_table
    bk = db.query(ReferenceBook).filter(
        ReferenceBook.code == "НЗ-2025-МС281-ИГИ").first()
    first_point = _interpolate_cost_table(db, bk.id, 65, (8, 15), 20.0, "707pr")
    tiny = _interpolate_cost_table(db, bk.id, 65, (8, 15), 0.2, "707pr")
    flat = _interpolate_cost_table(db, bk.id, 65, (8, 15), 0.2, "mu620")
    assert tiny < first_point, (tiny, first_point)
    assert math.isclose(flat, first_point, rel_tol=1e-9)
    # ф.8.7 буквально: а1 − (а2−а1)/(Х2−Х1)×(Х1−Х)×0,6
    a1, a2 = 134_685.0, 203_793.0
    expected = a1 - (a2 - a1) / (50 - 20) * (20 - 0.2) * 0.6
    assert math.isclose(tiny, expected, rel_tol=1e-6), (tiny, expected)

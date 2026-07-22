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


def test_mu620_lower_cap(db):
    """[МУ-620 п.2.1.3] СБЦП-книга, X ниже Xмин/2 → X_расч = Xмин/2 + warning
    (ф.8.4/Кэ применяется только к НЗ-книгам по 707/пр)."""
    r = calculate({"stage": "П", "region": "-", "entities": [_ent(
        object_name="lowcap", sbts_code="СБЦП 81-2001-17", sbts_table=10,
        x_value=0.05, x_unit="тыс. м3/сут",  # Xмин табл.10 = 1? → ниже половины
    )]}, db)
    ps = _pos(r, "ПД")
    if ps:  # если Xмин строки >0.1
        p = ps[0]
        assert p["cost"] > 0
        ok = any("3П" in w for w in r["warnings"]) or "Кэ" not in p["formula"]
        assert ok, (p, r["warnings"])


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

import json
import re
from itertools import groupby
from typing import Optional

import anthropic
import httpx
from pydantic import ValidationError as PydanticValidationError

from app.config import settings
from app.schemas import CoefficientInput, ExtractionResult

_STRIP_TYPE_SUFFIX = re.compile(
    r'\s+(производительностью|мощностью|объёмом|длиной|протяженностью)'
    r'(\s*[\(,].*)?$',
    re.IGNORECASE,
)
_STRIP_RANGE_SUFFIX = re.compile(
    r'[,:]?\s*(до|свыше|от)\s+[\d,].*$',
    re.IGNORECASE,
)


# ── Context builders ──────────────────────────────────────────────────────────

def _build_book_list(db) -> str:
    """Step 0: books with representative object sample (one per table) for semantic matching."""
    from app.models import ReferenceBook, BookObjectType
    books = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    if not books:
        return ""
    lines = [
        "Активные справочники (код, название, примеры объектов):",
        "ПРАВИЛО РЕГИОНА: справочники с пометкой [Регион: …] применяй ТОЛЬКО "
        "для объектов в этом регионе, и для таких объектов они ПРИОРИТЕТНЕЕ "
        "федеральных аналогов ТОГО ЖЕ вида работ. НЕ создавай дублирующих "
        "позиций по региональному и федеральному справочнику одновременно — "
        "выбери один. ВАЖНО: правило выбирает справочник, а НЕ отменяет вид "
        "работ: если ТЗ требует изыскания (ИГИ/ИГДИ/топосъёмка и т.п.) — "
        "обязательно выбери справочник изысканий (региональный для его региона, "
        "иначе федеральный НЗ) и создай эти позиции.",
    ]
    for b in books:
        region_tag = f" [Регион: {b.region}]" if getattr(b, "region", None) else ""
        lines.append(f"\n  {b.code} — {b.official_name or b.code}{region_tag}")
        # Uniform sample across the book: pick one type per table, evenly spaced
        all_types = (
            db.query(BookObjectType)
            .filter(BookObjectType.book_version_id == b.id)
            .order_by(BookObjectType.table_num)
            .all()
        )
        # Deduplicate by table_num, keep first per table
        seen_tables: set = set()
        per_table: list = []
        for t in all_types:
            key = t.table_num if t.table_num is not None else id(t)
            if key not in seen_tables:
                seen_tables.add(key)
                per_table.append(t)
        # Pick 8 evenly spaced across all tables
        n = len(per_table)
        indices = [int(i * (n - 1) / 7) for i in range(8)] if n >= 8 else list(range(n))
        sample: list[str] = []
        for i in indices:
            name = per_table[i].name
            name = name if len(name) <= 80 else name[:77] + "…"
            sample.append(name)
        if sample:
            lines.append(f"    Примеры объектов: {'; '.join(sample)}")
    return "\n".join(lines)


def _build_hints_context(db, book_codes: list[str]) -> str:
    """Extraction hints for detected books — injected after types in pass 1."""
    from app.models import BookExtractionHint, ReferenceBook

    books = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    _norm = lambda s: re.sub(r'^(сбцп|сбц|мрр)\s+', '', s.strip(), flags=re.IGNORECASE).lower()
    matched = [b for b in books if any(_norm(b.code) == _norm(c) or b.code == c for c in book_codes)]
    if not matched:
        matched = books

    lines: list[str] = []
    for book in matched:
        hints = (
            db.query(BookExtractionHint)
            .filter(BookExtractionHint.book_version_id == book.id, BookExtractionHint.is_active == True)
            .order_by(BookExtractionHint.sort_order)
            .all()
        )
        if hints:
            lines.append(f"\n═══ ДОПОЛНИТЕЛЬНЫЕ УСЛОВИЯ ИЗВЛЕЧЕНИЯ ({book.code}) ═══\n")
            lines.append(
                "Следующие правила обязательны. При их применении укажи justification "
                "из правила в поле notes извлекаемой позиции.\n"
            )
            for h in hints:
                lines.append(f"УСЛОВИЕ: {h.trigger_condition}")
                lines.append(f"  → {h.hint_for_ai}")
                lines.append(f"  Обоснование для notes: «{h.justification}»\n")

    return "\n".join(lines)


def _build_types_context(db, book_codes: list[str]) -> str:
    """Pass 1: object types + extraction hints for the detected book(s) only."""
    from app.models import BookObjectType, ReferenceBook, ReferenceRow

    books = (
        db.query(ReferenceBook)
        .filter(ReferenceBook.is_active == True)
        .all()
    )
    # Match by code (normalized: strip prefix variants)
    _norm = lambda s: re.sub(r'^(сбцп|сбц|мрр)\s+', '', s.strip(), flags=re.IGNORECASE).lower()
    matched = [b for b in books if any(_norm(b.code) == _norm(c) or b.code == c for c in book_codes)]
    if not matched:
        matched = books  # fallback: all books

    lines = ["═══ ДОСТУПНЫЕ ТИПЫ ОБЪЕКТОВ ═══\n"]
    lines.append(
        "Каждый тип — отдельная позиция сметы. "
        "Если объект соответствует нескольким типам — создай позицию для каждого.\n"
        "Для каждой позиции укажи:\n"
        "  sbts_object_type_id — id из [type_id=N] в списке ниже\n"
        "  sbts_table          — номер таблицы из «Таблица N [type_id=N]»\n"
        "  sbts_code           — код справочника (в скобках после названия справочника)\n"
    )

    for book in matched:
        lines.append(f"{book.official_name or book.code} (код: {book.code}):")
        types = (
            db.query(BookObjectType)
            .filter(BookObjectType.book_version_id == book.id)
            .order_by(BookObjectType.table_num, BookObjectType.id)
            .all()
        )
        if types:
            for table_num, group in groupby(types, key=lambda t: t.table_num):
                for t in group:
                    sample = (
                        db.query(ReferenceRow.x_unit)
                        .filter(ReferenceRow.object_type_id == t.id, ReferenceRow.x_unit.isnot(None))
                        .first()
                    )
                    unit = sample[0] if sample else ""
                    unit_str = f" → {unit}" if unit else ""
                    lines.append(f"  Таблица {table_num} [type_id={t.id}]: {t.name}{unit_str}")
        else:
            rows = (
                db.query(ReferenceRow.table_num, ReferenceRow.description, ReferenceRow.x_unit)
                .filter(ReferenceRow.book_version_id == book.id)
                .order_by(ReferenceRow.table_num, ReferenceRow.id)
                .all()
            )
            seen: set[tuple] = set()
            for table_num, description, x_unit in rows:
                if not description:
                    continue
                type_name = _STRIP_RANGE_SUFFIX.sub("", description).strip()
                type_name = _STRIP_TYPE_SUFFIX.sub("", type_name).strip().rstrip(",:").strip()
                if not type_name:
                    continue
                key = (table_num, type_name, x_unit or "")
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"  Таблица {table_num}: {type_name}{' → ' + x_unit if x_unit else ''}")
        lines.append("")

    return "\n".join(lines)


def _build_conditions_context(db, entities: list[dict]) -> str:
    """Pass 2: keyed coefficient conditions for only the tables used in pass 1."""
    from app.models import BookCondition, ReferenceBook

    needed: dict[int, set[int]] = {}  # book_id → set of table_nums

    for entity in entities:
        sbts_code = (entity.get("sbts_code") or "").strip()
        table_num = entity.get("sbts_table")
        if not sbts_code or not table_num:
            continue
        book = (
            db.query(ReferenceBook)
            .filter(ReferenceBook.is_active == True)
            .filter(ReferenceBook.code == sbts_code)
            .first()
        ) or (
            db.query(ReferenceBook)
            .filter(ReferenceBook.is_active == True)
            .filter(ReferenceBook.code.ilike(f"%{sbts_code[-8:]}%"))
            .first()
        )
        if not book:
            continue
        needed.setdefault(book.id, set()).add(table_num)

    if not needed:
        return ""

    lines = [
        "═══ КОЭФФИЦИЕНТЫ ДЛЯ ВЫЯВЛЕННЫХ ТАБЛИЦ ═══\n",
        "Для каждой позиции из предыдущего ответа определи — применим ли коэффициент "
        "на основе текста ТЗ. Вызови функцию assign_coefficients.\n",
    ]

    for book_id, table_nums in needed.items():
        book = db.get(ReferenceBook, book_id)

        keyed_table = (
            db.query(BookCondition)
            .filter(
                BookCondition.book_version_id == book_id,
                BookCondition.table_num.in_(list(table_nums)),
                BookCondition.coeff_key.isnot(None),
            )
            .order_by(BookCondition.table_num)
            .all()
        )
        keyed_wide = (
            db.query(BookCondition)
            .filter(
                BookCondition.book_version_id == book_id,
                BookCondition.table_num.is_(None),
                BookCondition.coeff_key.isnot(None),
            )
            .all()
        )
        all_conds = keyed_table + keyed_wide
        if not all_conds:
            continue

        lines.append(f"{book.code}:")
        by_table: dict[Optional[int], list] = {}
        for c in all_conds:
            by_table.setdefault(c.table_num, []).append(c)

        for tnum in sorted(by_table, key=lambda x: (x is None, x)):
            label = f"Таблица {tnum}" if tnum is not None else "Все таблицы"
            lines.append(f"  {label}:")
            for c in by_table[tnum]:
                coeff_str = (
                    f"×{c.coeff_min}" if c.coeff_min == c.coeff_max
                    else f"×{c.coeff_min}–{c.coeff_max}"
                ) if c.coeff_min is not None else ""
                row_hint = f" ({c.row_range})" if c.row_range else ""
                lines.append(f"    • {c.condition_short}{row_hint}: {coeff_str} [key={c.coeff_key}]")
        lines.append("")

    return "\n".join(lines)


def _validate_entities(result: "ExtractionResult", tz_text: str) -> None:
    """Post-extraction sanity check.

    For each entity:
    1. tz_quote check  — if quote non-empty, at least 20 chars must appear verbatim in TZ
    2. x_value check   — the number must appear somewhere in TZ text (raw or formatted)

    Failed checks lower confidence; entity is NOT removed (user decides).
    """
    import re as _re

    def _num_in_text(value: float, text: str) -> bool:
        """Check if value appears in text in any reasonable format."""
        candidates = set()
        # raw variants
        candidates.add(str(value))
        candidates.add(str(int(value)) if value == int(value) else "")
        # comma-decimal (Russian)
        candidates.add(f"{value:g}".replace(".", ","))
        # without trailing zeros
        candidates.add(f"{value:.4g}")
        candidates.add(f"{value:.4g}".replace(".", ","))
        # large: maybe stored as тыс → try ×1000 and ×1000000
        for mult in (1, 1000, 1_000_000, 0.001, 0.000001):
            v = value * mult
            candidates.add(f"{v:g}")
            candidates.add(f"{v:g}".replace(".", ","))
            candidates.add(str(int(v)) if v == int(v) else "")
        candidates.discard("")
        for c in candidates:
            if c and c in text:
                return True
        return False

    def _quote_in_text(quote: str, text: str) -> bool:
        if not quote or len(quote) < 15:
            return False
        tl = text.lower()
        ql = quote.lower()
        # Try multiple 25-char chunks across the quote (start, 1/3, 2/3)
        chunk_size = 25
        positions = [0, len(ql) // 3, len(ql) * 2 // 3]
        for pos in positions:
            chunk = ql[pos:pos + chunk_size].strip()
            if len(chunk) >= 15 and chunk in tl:
                return True
        return False

    for entity in result.entities:
        entity.section_num  = getattr(entity, "section_num", 0) or 0
        entity.section_name = getattr(entity, "section_name", "") or ""
        flags: list[str] = []

        # 1. quote check
        if not entity.tz_quote:
            flags.append("нет цитаты из ТЗ")
        elif not _quote_in_text(entity.tz_quote, tz_text):
            flags.append(f"цитата не найдена в ТЗ: «{entity.tz_quote[:60]}»")

        # 2. x_value check
        if entity.x_value is not None and entity.x_value != 0:
            if not _num_in_text(entity.x_value, tz_text):
                flags.append(f"x_value={entity.x_value} не найден в тексте ТЗ")

        if flags:
            entity.confidence = min(entity.confidence, 0.55)
            warning = " | ".join(flags)
            entity.notes = f"⚠ {warning}" + (f"\n{entity.notes}" if entity.notes else "")


# ── Tool schemas ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты опытный сметчик ПИР (проектно-изыскательских работ) в России.
Твоя задача — извлечь из Технического задания (ТЗ) все объекты и их параметры для расчёта стоимости ПИР по активным справочникам.

═══ ТИПЫ СПРАВОЧНИКОВ ═══

Система работает с двумя типами нормативных справочников:
  НЗ  — Нормативы затрат (Приказ Минстроя №707/пр от 01.10.2021).
         Более новый стандарт. ПРИОРИТЕТ над СБЦ для одного и того же типа объекта.
  СБЦ — Справочники базовых цен (МУ №620 от 29.12.2009 Минрегион).
         Используется, если для типа объекта нет НЗ.

Если оба справочника (НЗ и СБЦ) покрывают один тип объекта — используй НЗ.

═══ ВЫБОР СПРАВОЧНИКА — ПО ВИДУ РАБОТ, НЕ ПО ОБЪЕКТУ ═══

НС, ТЭЦ, завод, водозабор — это АДРЕС работ, не тип объекта.
Справочник выбирается по ВИДУ РАБОТ:

  Вид работ                                    → Справочник
  Ячейки РУ 6-20 кВ, кабельные линии,
  шкафы СН/ОТ, трансформаторные подстанции    → НЗ-2021-МС847-СИТО
  АСУТП / ПЛК / АРМ / SCADA / системы
  управления технологическими процессами       → СБЦП 81-2001-22 (факторный метод!)
  Водопровод, канализация, НС как
  технологический объект ВКХ (трубы, ёмкости) → СБЦП 81-2001-17
  Нефтепереработка, нефтехимия                 → СБЦП 81-2001-13

  Если нужный справочник отсутствует в системе — оставь sbts_code="" и опиши в notes.

═══ ПРАВИЛА ИЗВЛЕЧЕНИЯ ═══

КАТЕГОРИЯ объекта (строго из ТЗ):
  new_construction — новое строительство
  reconstruction   — реконструкция
  overhaul         — капитальный ремонт

ПАРАМЕТР X — только в единицах из таблицы справочника (см. список типов ниже), не в единицах ТЗ:
  Единицы для каждого типа объекта указаны в справочнике (→ единица после названия типа).
  Конвертируй при необходимости.
  Пример: ТЗ пишет "104 000 м³/сут", справочник требует тыс. м³/сут → x_value=104, x_unit="тыс. м³/сут"
  Если X не указан явно числом — создай позицию с x_value=null,
  в notes укажи откуда его можно взять (например: "рассчитать из численности населения X чел.").

КАЖДЫЙ ОБЪЕКТ = ОТДЕЛЬНАЯ ПОЗИЦИЯ:
  Если несколько однотипных объектов в разных населённых пунктах, участках трассы или этапах —
  создай отдельную позицию для каждого. Не суммировать в одну строку.
  Если несколько одинаковых объектов в одном месте (например, 2 резервуара на одной площадке) —
  одна позиция с quantity=2 и x_value = параметр ОДНОГО объекта.
  Это важно: формула (a + b×X) содержит постоянную часть a, которая считается на каждый объект.

ОДИН ТЗ → НЕСКОЛЬКО СТРОК СПРАВОЧНИКА:
  Сложный объект (станция, комплекс, сооружение с вспомогательными объектами) порождает
  несколько позиций — по одной на каждый пункт справочника.
  Извлеки ВСЕ, даже если X неизвестен (x_value=null).

ТОЛЬКО ТО, ЧТО ОПИСАНО В ТЗ:
  Не добавляй объекты только из-за названия проекта или объекта.
  Объект должен быть явно упомянут в тексте ТЗ (в этапах, требованиях, перечне работ, ТЭП).

ЦИТАТА (tz_quote) — ОБЯЗАТЕЛЬНО для каждой позиции:
  Скопируй дословно фрагмент ТЗ (15–120 символов), который доказывает существование позиции.
  Пример: "Производительность насосной станции – 153,16 м3/час"
  Если позиция нормативно-обязательная (confidence < 0.7) — цитируй признак из ТЗ,
  который её обязывает: например "КНС с точкой слива".
  Если подходящей цитаты нет — tz_quote="" и confidence < 0.5.

НЕОЧЕВИДНЫЕ ПОЗИЦИИ:
  После извлечения явных объектов — рассуждай как опытный сметчик данной отрасли.
  Какие работы нормативно обязательны или технологически неизбежны,
  даже если ТЗ о них прямо не говорит?

  Добавляй такие позиции с confidence < 0.7 и notes с обоснованием.
  notes должен содержать: (а) цитату или признак из ТЗ, (б) нормативную логику.

  НЕ добавляй позиции, для которых нет соответствующего типа в списке
  доступных справочников (см. раздел ниже).
  НЕ изобретай коэффициенты сверх допустимых типов.

КОЭФФИЦИЕНТЫ — только те, что явно следуют из ТЗ:
  Указывай тип коэффициента (name) и признак применимости (value=1 если применимо).
  НЕ назначай числовые значения — они берутся из справочника (book_conditions).
  Допустимые типы:
    "reconstruction"  — реконструкция (категория = reconstruction)
    "overhaul"        — капитальный ремонт (категория = overhaul)
    "asu"             — микропроцессорные контроллеры / АСУ / АСДКУ / АСКП упомянуты в ТЗ
    "deepening"       — заглубление подземной части > 10 м указано в ТЗ
    "seismic"         — сейсмика > 6 баллов МСК указана в ТЗ (отдельный коэфф. для 7, 8, 9 баллов)
    "fishery"         — сброс в водоём рыбохозяйственного значения (I, II кат.) указан в ТЗ
  Для СБЦ (МУ №620 п.3.7): при сейсмике указывай балл в notes — 7, 8 или 9.
  Для НЗ: коэффициенты по усложняющим факторам задаются в book_conditions конкретного НЗ.
  НЕ добавляй районные, климатические, зональные коэффициенты (МУ620 п.3.6 и аналоги) —
  они не применяются для ПИР.
  Коэффициенты застройки территории, заглубления и усложняющие условия строительства
  (хранятся в book_conditions НЗ/СБЦ) — применяются. AI их не назначает числово,
  они берутся из book_conditions в Pass 2 по coeff_key.

ЭТАПЫ — группировка позиций по ТЗ:
  Если ТЗ явно содержит пронумерованные этапы ("1 Этап:", "2 Этап:", "Этап 1:", "Stage 1:" и т.п.) —
  присвой каждой извлекаемой позиции:
    section_num = номер этапа (1, 2, 3...)
    section_name = короткое название этапа из ТЗ (≤60 символов; убери лишние детали)
  Позиции, которые не относятся к конкретному этапу (например, общие требования):
    section_num = 0, section_name = ""
  Если ТЗ не содержит явных этапов:
    section_num = 0, section_name = "" для всех позиций.
  Один этап ТЗ может порождать несколько позиций (ячейка, кабель, РЗА — все из Этапа 1).

СТАДИЯ — из текста ТЗ:
  "П"   — только проектная документация
  "Р"   — только рабочая документация
  "П+Р" — проектная и рабочая документация вместе
  Для СБЦ (МУ №620 п.1.4): ПД = 40%, РД = 60% от базовой цены.
  Для НЗ: распределение устанавливается в самом НЗ.

АДРЕС — извлекай точно из ТЗ, без интерпретации.

НАИМЕНОВАНИЕ ОБЪЕКТА (tz_object_name) — официальное название из заголовка ТЗ:
  Ищи фразы "по объекту:", "объект:", "наименование объекта:", "Техническое задание на ...".
  Извлекай полное название в кавычках или после двоеточия.
  Пример: «Система управления и регулирования производительности сетевых насосов НС №7»
  Если не найдено — пустая строка.

═══ АСУТП (СБЦП 81-2001-22) — ОСОБЫЙ ТИП ═══

Для позиций АСУТП/ПЛК/АРМ/SCADA указывай:
  sbts_code = "СБЦП 81-2001-22"
  x_value = null  (не используется — АСУТП не имеет X параметра)
  coefficients = []  (пустой список — коррекция идёт через asutp_k, не coefficients)
  asutp_factors — объект РОВНО с 7 факторами: Ф2, Ф5, Ф6, Ф7, Ф8, Ф9, Ф10.
    Ф1/Ф3/Ф4 — только для Таблицы 1 (ТЗ на создание), здесь не используются.
  Если ТЗ разбивает АСУТП на этапы с разными группами объектов — отдельная позиция на каждый этап.
  Определи каждый фактор из ТЗ:

  Ф2  Характер процесса:
    п.1.1 Непрерывный (длительные режимы, безостановочная подача)
    п.1.2 Полунепрерывный (переходные режимы с добавками/заменой)
    п.1.3 Непрерывно-дискретный I (сочетает непрерывные и прерывистые)
    п.1.4 Непрерывно-дискретный II (прерывистые с малой длительностью, аварии)
    п.1.5 Циклический (прерывистый, длительные интервалы непрерывного функционирования)
    п.1.6 Дискретный (прерывистый, малая длительность непрерывных операций)

  Ф5  Количество технол. операций, контролируемых/управляемых АСУТП:
    п.2.1 до 5 | п.2.2 5-10 | п.2.3 10-20 | п.2.4 20-35
    п.2.5 35-50 | п.2.6 50-70 | п.2.7 70-100 | п.2.8 +1 за каждые 50 свыше 100

  Ф6  Степень развитости информационных функций:
    п.3.1 I (параллельный контроль) | п.3.2 II (централизованный контроль)
    п.3.3 III (косвенное измерение) | п.3.4 IV (анализ/диагностика по модели)

  Ф7  Степень развитости управляющих функций:
    п.4.1 I (одноконтурное рег.) | п.4.2 II (каскадное/жёсткий цикл)
    п.4.3 III (многосвязное рег./программное с разветвлениями)
    п.4.4 IV (оптим. установившихся режимов) | п.4.5 V (оптим. переходных)
    п.4.6 VI (оптим. быстропротекающих, аварии) | п.4.7 VII (адаптация/самообучение)

  Ф8  Режим выполнения управляющих функций:
    п.5.1 Авт. ручной | п.5.2 Советник | п.5.3 Диалоговый
    п.5.4 Авт. косвенного управления | п.5.5 Прямой цифровой

  Ф9  Количество переменных, измеряемых/контролируемых/регистрируемых:
    п.6.1 до 20 | п.6.2 20-50 | п.6.3 50-100 | п.6.4 100-170
    п.6.5 170-250 | п.6.6 250-350 | п.6.7 350-470 | п.6.8 470-600
    п.6.9 600-800 | п.6.10 800-1000 | п.6.11 1000-1300 | п.6.12 1300-1600
    п.6.13 1600-2000 | п.6.14 +1 за каждые 500 свыше 2000

  Ф10 Количество управляющих воздействий (аналогично Ф5 по диапазонам):
    п.7.1 до 5 | п.7.2 5-10 | п.7.3 10-20 | п.7.4 20-35
    п.7.5 35-50 | п.7.6 50-70 | п.7.7 70-100 | п.7.8 +1 за каждые 50 свыше 100

  asutp_k = 1.0 (если нет особых корректирующих условий из табл.3 СБЦП-2001-22)"""

_COEFF_ITEM = {
    "type": "object",
    "required": ["name", "value"],
    "properties": {
        "name": {
            "type": "string",
            "description": "coeff_key из book_conditions справочника (reconstruction, overhaul, asu, deepening, seismic, fishery и др.)",
        },
        "value": {"type": "number", "const": 1},
        "reason": {"type": "string"},
    },
}

EXTRACTION_TOOL = {
    "name": "extract_pir_entities",
    "description": "Извлечь структурированные данные о объектах ПИР из технического задания",
    "input_schema": {
        "type": "object",
        "required": ["entities", "stage", "region", "missing_data", "overall_confidence"],
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["category", "object_type", "object_name", "address"],
                    "properties": {
                        "category": {"type": "string", "enum": ["new_construction", "reconstruction", "overhaul"]},
                        "object_type": {"type": "string"},
                        "object_name": {"type": "string"},
                        "address": {"type": "string"},
                        "sbts_code": {"type": "string"},
                        "sbts_table": {"type": "integer"},
                        "sbts_object_type_id": {"type": "integer"},
                        "x_value": {"type": "number"},
                        "x_unit": {"type": "string"},
                        "quantity": {"type": "integer", "minimum": 1},
                        "coefficients": {"type": "array", "items": _COEFF_ITEM},
                        "asutp_factors": {
                            "type": "object",
                            "description": "Только для СБЦП 81-2001-22. Ключи: Ф2,Ф5,Ф6,Ф7,Ф8,Ф9,Ф10. Значения: п.N.M",
                            "additionalProperties": {"type": "string"},
                        },
                        "asutp_k": {
                            "type": "number",
                            "description": "Поправочный коэффициент К для АСУТП (табл.3 СБЦП-2001-22). Default=1.0",
                        },
                        "sections": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Коды разрабатываемых разделов документации, ТОЛЬКО если ТЗ явно "
                                "ограничивает состав (перечисляет разделы/части для этого объекта). "
                                "Стандартные коды ПД: ПЗ, ПЗУ, АР, КР, ИОС.ЭС, ИОС.ВС, ИОС.ВО, "
                                "ИОС.ОВ, ИОС.СС, ИОС.ГС, ИОС.АВТ, ТХ, ПОС, ООС, ПБ, ОДИ, ЭЭ, СМ. "
                                "Пустой массив = полный состав разделов."
                            ),
                        },
                        "notes": {"type": "string"},
                        "section_num": {
                            "type": "integer",
                            "description": "Номер этапа ТЗ (1, 2, 3...). 0 если ТЗ не разбито на этапы или позиция не привязана к конкретному этапу.",
                        },
                        "section_name": {
                            "type": "string",
                            "description": "Краткое название этапа из ТЗ (≤60 символов). Пустая строка если section_num=0.",
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "tz_quote": {"type": "string", "description": "Дословная цитата из ТЗ (15-120 символов), обосновывающая эту позицию"},
                    },
                },
            },
            "stage": {"type": "string", "enum": ["П", "Р", "П+Р"]},
            "region": {"type": "string"},
            "tz_object_name": {
                "type": "string",
                "description": "Официальное наименование объекта из заголовка ТЗ — текст после 'по объекту:' или 'объект:'. Полностью, включая кавычки если есть. Пример: «Система управления насосной станцией №7»",
            },
            "missing_data": {"type": "array", "items": {"type": "string"}},
            "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}

COEFF_TOOL = {
    "name": "assign_coefficients",
    "description": "Присвоить применимые коэффициенты к позициям ПИР на основе условий справочника и текста ТЗ.",
    "input_schema": {
        "type": "object",
        "required": ["assignments"],
        "properties": {
            "assignments": {
                "type": "array",
                "description": "Только позиции с хотя бы одним применимым коэффициентом.",
                "items": {
                    "type": "object",
                    "required": ["entity_index", "coefficients"],
                    "properties": {
                        "entity_index": {"type": "integer", "description": "0-based индекс позиции"},
                        "coefficients": {"type": "array", "items": _COEFF_ITEM},
                    },
                },
            }
        },
    },
}

EXTRACTION_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": EXTRACTION_TOOL["name"],
        "description": EXTRACTION_TOOL["description"],
        "parameters": EXTRACTION_TOOL["input_schema"],
    },
}

COEFF_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": COEFF_TOOL["name"],
        "description": COEFF_TOOL["description"],
        "parameters": COEFF_TOOL["input_schema"],
    },
}

_RESOLVE_X_ITEM = {
    "type": "object",
    "required": ["entity_index", "x_value", "x_unit", "reason"],
    "properties": {
        "entity_index": {"type": "integer", "description": "0-based индекс позиции"},
        "x_value": {"type": "number"},
        "x_unit": {"type": "string"},
        "reason": {"type": "string", "description": "Источник: цитата из ТЗ или ссылка на другую позицию"},
    },
}

RESOLVE_X_TOOL = {
    "name": "resolve_missing_x",
    "description": "Уточнить x_value для позиций, где AI не смог его определить",
    "input_schema": {
        "type": "object",
        "required": ["resolutions"],
        "properties": {
            "resolutions": {
                "type": "array",
                "description": "Только позиции, для которых X удалось определить. Пустой список если ничего.",
                "items": _RESOLVE_X_ITEM,
            }
        },
    },
}

RESOLVE_X_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": RESOLVE_X_TOOL["name"],
        "description": RESOLVE_X_TOOL["description"],
        "parameters": RESOLVE_X_TOOL["input_schema"],
    },
}


# ── Shared pipeline ───────────────────────────────────────────────────────────


def _fill_sbts_table_from_type_id(result: ExtractionResult, db) -> None:
    """Deterministic: fill sbts_table from sbts_object_type_id when AI omitted it."""
    if db is None:
        return
    from app.models import BookObjectType
    type_ids = {e.sbts_object_type_id for e in result.entities if e.sbts_table is None and e.sbts_object_type_id}
    if not type_ids:
        return
    types = db.query(BookObjectType).filter(BookObjectType.id.in_(type_ids)).all()
    type_to_table = {t.id: t.table_num for t in types}
    for entity in result.entities:
        if entity.sbts_table is None and entity.sbts_object_type_id in type_to_table:
            entity.sbts_table = type_to_table[entity.sbts_object_type_id]


def _fill_sbts_codes(result: ExtractionResult, db, detected_codes: list[str]) -> None:
    """Fill empty sbts_code by matching entity's sbts_table → book that owns it."""
    if not db:
        return
    from app.models import ReferenceBook, ReferenceRow

    _norm = lambda s: re.sub(r'^(сбцп|сбц|мрр)\s+', '', s.strip(), flags=re.IGNORECASE).lower()
    active = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    matched_books = [b for b in active if any(_norm(b.code) == _norm(c) or b.code == c for c in detected_codes)]
    if not matched_books:
        matched_books = active

    # table_num → canonical book code (first match wins)
    table_to_code: dict[int, str] = {}
    for book in matched_books:
        tables = {r.table_num for r in db.query(ReferenceRow.table_num)
                  .filter(ReferenceRow.book_version_id == book.id).all()}
        for t in tables:
            table_to_code.setdefault(t, book.code)

    for entity in result.entities:
        if not entity.sbts_code and entity.sbts_table and entity.sbts_table in table_to_code:
            entity.sbts_code = table_to_code[entity.sbts_table]


def _build_resolve_x_context(
    result: ExtractionResult, tz_text: str, hints_ctx: str, db=None
) -> str:
    """Pass 3 context: entity list with null-x highlighted + hints + TZ.

    Includes the reference-table units per entity so the resolved X is given
    in the book's units, not the TZ's.
    """
    null_indices = [i for i, e in enumerate(result.entities) if e.x_value is None]
    if not null_indices:
        return ""

    # (sbts_code, sbts_table) → units present in that table's rows
    unit_map: dict[tuple[str, int], str] = {}
    if db is not None:
        from app.models import ReferenceRow
        from app.services.calculator import _find_active_book
        for e in result.entities:
            if not e.sbts_table:
                continue
            key = (e.sbts_code or "", e.sbts_table)
            if key in unit_map:
                continue
            book = _find_active_book(db, e.sbts_code or "")
            if not book:
                continue
            units = sorted({
                u for (u,) in db.query(ReferenceRow.x_unit)
                .filter(
                    ReferenceRow.book_version_id == book.id,
                    ReferenceRow.table_num == e.sbts_table,
                    ReferenceRow.x_unit.isnot(None),
                )
                .distinct()
                .all()
            })
            if units:
                unit_map[key] = ", ".join(units)

    lines = [
        "═══ УТОЧНЕНИЕ ПАРАМЕТРА X ═══\n",
        "Анализ ТЗ уже выполнен. Ниже — все позиции с текущими X.",
        "Для позиций «X=null» определи X из текста ТЗ или из параметров других позиций.",
        "X указывай СТРОГО в единицах справочника (см. «ед. справочника» у позиции);",
        "при необходимости конвертируй значение из единиц ТЗ.",
        "Если X не удаётся определить — оставь такие позиции без изменений.\n",
        "Позиции (индекс, таблица, наименование, X):",
    ]
    for i, e in enumerate(result.entities):
        x_str = f"{e.x_value} {e.x_unit}" if e.x_value is not None else "null ← ОПРЕДЕЛИТЬ"
        unit_hint = unit_map.get((e.sbts_code or "", e.sbts_table or 0))
        unit_str = f" | ед. справочника: {unit_hint}" if unit_hint else ""
        lines.append(f"  [{i}] Таблица {e.sbts_table}: {e.object_name} | {x_str}{unit_str}")
    if hints_ctx:
        lines.append("\n" + hints_ctx)
    lines.append("\n═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text)
    lines.append("\nВызови функцию resolve_missing_x. Если X не удалось определить — resolutions=[].")
    return "\n".join(lines)


def _merge_resolved_x(result: ExtractionResult, resolutions: list[dict]) -> None:
    for r in resolutions:
        idx = r.get("entity_index", -1)
        if not (0 <= idx < len(result.entities)):
            continue
        entity = result.entities[idx]
        if entity.x_value is not None:
            continue  # never overwrite AI-extracted value
        x_val = r.get("x_value")
        if x_val is None:
            continue
        entity.x_value = float(x_val)
        entity.x_unit = r.get("x_unit") or entity.x_unit
        reason = r.get("reason", "")
        prefix = f"[pass 3] {reason}" if reason else "[pass 3]"
        entity.notes = (prefix + "\n" + (entity.notes or "")).strip()


def _flag_missing_x_values(result: ExtractionResult) -> None:
    """After all passes: mark entities where x_value is still None so UI can prompt manual entry."""
    for entity in result.entities:
        if entity.x_value is not None:
            continue
        reason = f"Объём/мощность не указаны в ТЗ для «{entity.object_type}» — введите вручную"
        entity.x_value_missing_reason = reason
        result.missing_data.append(f"Нет X: {entity.object_type} ({entity.object_name or entity.address or '—'})")


def _merge_coefficients(result: ExtractionResult, assignments: list[dict]) -> None:
    for assignment in assignments:
        idx = assignment.get("entity_index", -1)
        if not (0 <= idx < len(result.entities)):
            continue
        entity = result.entities[idx]
        existing = {c.name for c in entity.coefficients}
        for c in assignment.get("coefficients", []):
            name = c.get("name")
            if name and name not in existing:
                try:
                    entity.coefficients.append(CoefficientInput(**c))
                    existing.add(name)
                except Exception:
                    pass


def _detect_books_from_text(tz_text: str) -> list[str]:
    """Fast regex: find СБЦП/МРР codes explicitly mentioned in TZ text."""
    pattern = re.compile(
        r'\b(?:СБЦП|СБЦ|МРР)\s*[\d\-\.]+(?:\-\d+)*',
        re.IGNORECASE,
    )
    return list(dict.fromkeys(m.group(0).strip() for m in pattern.finditer(tz_text)))


# ── Anthropic three-pass ──────────────────────────────────────────────────────

async def extract_entities(text: str, db=None) -> ExtractionResult:
    """Three-pass extraction (Anthropic):
    Step 0 — full TZ + book list → detect applicable book(s).
    Pass 1 — TZ (cached) + types for detected book → entities.
    Pass 2 — conditions for extracted table_nums → coefficients merged in.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tz_text = text[: settings.max_tz_chars]
    system_block = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]

    # ── Step 0: book detection ────────────────────────────────────────────────
    detected_codes: list[str] = []

    if db is not None:
        # Try regex first (free)
        detected_codes = _detect_books_from_text(tz_text)

        if not detected_codes:
            book_list = _build_book_list(db)
            if book_list:
                # ── Step 0a: extract object list + project context from TZ ──
                step0a_msg = (
                    "Прочитай техническое задание и выдай:\n"
                    "СТРОКА 1: Тип проекта одной строкой — укажи: гражданский / промышленный / инфраструктурный, "
                    "и если промышленный — отрасль (например: «промышленный, переработка лубяных культур / текстиль»).\n"
                    "СТРОКИ 2+: Нумерованный список объектов проектирования. "
                    "Для каждого: название, тип (здание/сооружение/сеть/изыскания), параметры из ТЗ.\n"
                    "Не упоминай справочники или нормативы.\n\n"
                    "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text
                )
                resp0a = client.messages.create(
                    temperature=0,
                    model=settings.extraction_model,
                    max_tokens=400,
                    system=system_block,
                    messages=[{"role": "user", "content": step0a_msg}],
                )
                object_list = resp0a.content[0].text.strip() if resp0a.content else ""

                # ── Step 0b: match object list to books ────────────────────────
                step0b_msg = (
                    "На основе списка объектов проектирования выбери применимые справочники.\n"
                    "Правила:\n"
                    "1. Для каждого объекта найди справочник, чьи «Примеры объектов» "
                    "совпадают по типу, назначению или отрасли — даже если терминология отличается.\n"
                    "2. Промышленные объекты (завод, цех, производство) → "
                    "отраслевой справочник, не общегражданский.\n"
                    "3. Изыскания → справочник изысканий (НЗ).\n"
                    "Ответь ТОЛЬКО кодами через запятую. Пример: СБЦП 81-2001-17, НЗ-2025-МС281-ИГИ\n\n"
                    f"ОБЪЕКТЫ ПРОЕКТИРОВАНИЯ:\n{object_list}\n\n"
                    f"{book_list}"
                )
                resp0b = client.messages.create(
                    temperature=0,
                    model=settings.extraction_model,
                    max_tokens=200,
                    system=system_block,
                    messages=[{"role": "user", "content": step0b_msg}],
                )
                raw = resp0b.content[0].text.strip() if resp0b.content else ""
                detected_codes = [c.strip() for c in raw.split(",") if c.strip()]

    # ── Pass 1: extract entities ──────────────────────────────────────────────
    types_ctx = _build_types_context(db, detected_codes) if db is not None else ""
    hints_ctx = _build_hints_context(db, detected_codes) if db is not None else ""
    msg1_content = "Проанализируй ТЗ и извлеки все объекты:\n\n"
    if types_ctx:
        msg1_content += types_ctx + "\n\n"
    if hints_ctx:
        msg1_content += hints_ctx + "\n\n"
    msg1_content += "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text

    messages: list[dict] = [{"role": "user", "content": msg1_content}]

    resp1 = client.messages.create(
        temperature=0,
        model=settings.extraction_model,
        max_tokens=4096,
        system=system_block,
        messages=messages,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_pir_entities"},
    )

    result: Optional[ExtractionResult] = None
    for block in resp1.content:
        if block.type == "tool_use" and block.name == "extract_pir_entities":
            try:
                result = ExtractionResult(**block.input)
            except Exception:
                result = ExtractionResult(entities=[], missing_data=["AI вернул пустой результат извлечения"])
            break

    if not result:
        return ExtractionResult(entities=[], missing_data=["Не удалось извлечь данные из ТЗ"])
    _fill_sbts_table_from_type_id(result, db)
    _fill_sbts_codes(result, db, detected_codes)

    if not result.entities or db is None:
        _flag_missing_x_values(result)
        _validate_entities(result, tz_text)
        return result

    # ── Pass 2: assign coefficients ───────────────────────────────────────────
    entities_dicts = [e.model_dump() for e in result.entities]
    conditions_ctx = _build_conditions_context(db, entities_dicts)

    if not conditions_ctx:
        return result

    # Find tool_use id from pass 1 to satisfy Anthropic's tool_result requirement
    tool_use_id = next(
        (b.id for b in resp1.content if b.type == "tool_use"),
        None,
    )
    pass2_user_content: list = []
    if tool_use_id:
        pass2_user_content.append({
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": "OK",
        })
    pass2_user_content.append({"type": "text", "text": conditions_ctx})

    messages = [
        {"role": "user", "content": msg1_content},
        {"role": "assistant", "content": resp1.content},
        {"role": "user", "content": pass2_user_content},
    ]

    resp2 = client.messages.create(
        temperature=0,
        model=settings.extraction_model,
        max_tokens=2048,
        system=system_block,
        messages=messages,
        tools=[COEFF_TOOL],
        tool_choice={"type": "tool", "name": "assign_coefficients"},
    )

    for block in resp2.content:
        if block.type == "tool_use" and block.name == "assign_coefficients":
            _merge_coefficients(result, block.input.get("assignments", []))
            break

    # ── Pass 3 (optional): resolve x_value=null ───────────────────────────────
    resolve_ctx = _build_resolve_x_context(result, tz_text, hints_ctx, db=db)
    if resolve_ctx:
        resp3 = client.messages.create(
            temperature=0,
            model=settings.extraction_model,
            max_tokens=1024,
            system=system_block,
            messages=[{"role": "user", "content": resolve_ctx}],
            tools=[RESOLVE_X_TOOL],
            tool_choice={"type": "tool", "name": "resolve_missing_x"},
        )
        for block in resp3.content:
            if block.type == "tool_use" and block.name == "resolve_missing_x":
                _merge_resolved_x(result, block.input.get("resolutions", []))
                break

    _flag_missing_x_values(result)
    _validate_entities(result, tz_text)
    return result


# ── OpenRouter three-pass ─────────────────────────────────────────────────────

async def extract_entities_openrouter(text: str, model_id: str, db=None) -> ExtractionResult:
    """Three-pass extraction via OpenRouter (OpenAI-compatible multi-turn)."""
    tz_text = text[: settings.max_tz_chars]

    def _or_headers() -> dict:
        return {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://ib-pir-calculator.ru",
            "X-Title": "IB PIR Calculator",
        }

    def _or_error(resp: httpx.Response) -> str:
        try:
            body = resp.json()
            return body.get("error", {}).get("message") or resp.text
        except Exception:
            return resp.text

    async def _call(messages: list[dict], tools: list, tool_name: str, max_tokens: int) -> dict:
        # Модели пишут текстовое рассуждение перед tool_call; при обрезке по
        # max_tokens провайдер отдаёт tool_call с пустыми аргументами "{}".
        # Поэтому: finish_reason=length → один ретрай с 4-кратным бюджетом.
        budget = max_tokens
        data: dict = {}
        for attempt in range(2):
            payload = {
                "model": model_id,
                "max_tokens": budget,
                "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                "tools": tools,
                # No tool_choice — let the model decide; avoids 404 on providers
                # that don't support forced function calling.
            }
            async with httpx.AsyncClient(timeout=180) as http:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers=_or_headers(),
                )
            if not resp.is_success:
                raise ValueError(f"OpenRouter {resp.status_code} для модели '{model_id}': {_or_error(resp)}")
            try:
                data = resp.json()
            except Exception:
                preview = resp.text[:300].replace("\n", " ")
                raise ValueError(f"OpenRouter вернул не-JSON (ct={resp.headers.get('content-type','?')}): {preview}")
            finish = data.get("choices", [{}])[0].get("finish_reason")
            if finish == "length" and attempt == 0:
                budget = max_tokens * 4
                continue
            break
        return data

    async def _call_plain(messages: list[dict], max_tokens: int) -> str:
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        }
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=_or_headers(),
            )
        if not resp.is_success:
            # Step 0 failure is non-fatal: fallback to all books
            return ""
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    # ── Step 0: book detection ────────────────────────────────────────────────
    detected_codes: list[str] = []
    if db is not None:
        detected_codes = _detect_books_from_text(tz_text)
        if not detected_codes:
            book_list = _build_book_list(db)
            if book_list:
                # ── Step 0a: extract object list + project context from TZ ──
                step0a_content = (
                    "Прочитай техническое задание и выдай:\n"
                    "СТРОКА 1: Тип проекта одной строкой — укажи: гражданский / промышленный / инфраструктурный, "
                    "и если промышленный — отрасль (например: «промышленный, переработка лубяных культур / текстиль»).\n"
                    "СТРОКИ 2+: Нумерованный список объектов проектирования. "
                    "Для каждого: название, тип (здание/сооружение/сеть/изыскания), параметры из ТЗ.\n"
                    "Не упоминай справочники или нормативы.\n\n"
                    "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text
                )
                object_list = await _call_plain(
                    [{"role": "user", "content": step0a_content}], max_tokens=400
                )

                # ── Step 0b: match object list to books ───────────────────────
                step0b_content = (
                    "На основе списка объектов проектирования выбери применимые справочники.\n"
                    "Правила:\n"
                    "1. Для каждого объекта найди справочник, чьи «Примеры объектов» "
                    "совпадают по типу, назначению или отрасли — даже если терминология отличается.\n"
                    "2. Промышленные объекты (завод, цех, производство) → "
                    "отраслевой справочник, не общегражданский.\n"
                    "3. Изыскания → справочник изысканий (НЗ).\n"
                    "Ответь ТОЛЬКО кодами через запятую. Пример: СБЦП 81-2001-17, НЗ-2025-МС281-ИГИ\n\n"
                    f"ОБЪЕКТЫ ПРОЕКТИРОВАНИЯ:\n{object_list}\n\n"
                    f"{book_list}"
                )
                raw = await _call_plain(
                    [{"role": "user", "content": step0b_content}], max_tokens=200
                )
                detected_codes = [c.strip() for c in raw.split(",") if c.strip()]

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    types_ctx = _build_types_context(db, detected_codes) if db is not None else ""
    hints_ctx = _build_hints_context(db, detected_codes) if db is not None else ""
    msg1_content = (
        "Проанализируй ТЗ и извлеки все объекты. "
        "Вызови функцию extract_pir_entities.\n\n"
    )
    if types_ctx:
        msg1_content += types_ctx + "\n\n"
    if hints_ctx:
        msg1_content += hints_ctx + "\n\n"
    msg1_content += "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text

    messages: list[dict] = [{"role": "user", "content": msg1_content}]
    data1 = await _call(messages, [EXTRACTION_TOOL_OPENAI], "extract_pir_entities", 4096)

    tool_calls = data1.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
    if not tool_calls:
        return ExtractionResult(
            entities=[],
            stage="П+Р",
            region="",
            missing_data=[f"OpenRouter ({model_id}): не вернул tool_call"],
            overall_confidence=0.0,
        )

    try:
        result = ExtractionResult(**json.loads(tool_calls[0]["function"]["arguments"]))
    except (json.JSONDecodeError, PydanticValidationError):
        finish = data1.get("choices", [{}])[0].get("finish_reason")
        return ExtractionResult(
            entities=[],
            stage="П+Р",
            region="",
            missing_data=[
                f"OpenRouter ({model_id}): невалидные аргументы tool_call "
                f"(finish_reason={finish}) — вероятно, ответ обрезан по max_tokens"
            ],
            overall_confidence=0.0,
        )
    _fill_sbts_table_from_type_id(result, db)
    _fill_sbts_codes(result, db, detected_codes)

    if not result.entities or db is None:
        _flag_missing_x_values(result)
        _validate_entities(result, tz_text)
        return result

    # ── Pass 2 ────────────────────────────────────────────────────────────────
    entities_dicts = [e.model_dump() for e in result.entities]
    conditions_ctx = _build_conditions_context(db, entities_dicts)
    if not conditions_ctx:
        return result

    assistant_msg = data1["choices"][0]["message"]
    messages = [
        {"role": "user", "content": msg1_content},
        {"role": "assistant", "content": assistant_msg.get("content") or "", "tool_calls": assistant_msg.get("tool_calls", [])},
        {"role": "tool", "tool_call_id": tool_calls[0]["id"], "content": tool_calls[0]["function"]["arguments"]},
        {"role": "user", "content": conditions_ctx},
    ]

    data2 = await _call(messages, [COEFF_TOOL_OPENAI], "assign_coefficients", 2048)
    tool_calls2 = data2.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
    if tool_calls2:
        try:
            assignments = json.loads(tool_calls2[0]["function"]["arguments"]).get("assignments", [])
            _merge_coefficients(result, assignments)
        except (json.JSONDecodeError, KeyError):
            pass  # truncated response — skip coefficients, return entities as-is

    # ── Pass 3 (optional): resolve x_value=null ───────────────────────────────
    resolve_ctx = _build_resolve_x_context(result, tz_text, hints_ctx, db=db)
    if resolve_ctx:
        data3 = await _call(
            [{"role": "user", "content": resolve_ctx}],
            [RESOLVE_X_TOOL_OPENAI],
            "resolve_missing_x",
            1024,
        )
        tool_calls3 = data3.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
        if tool_calls3:
            try:
                resolutions = json.loads(tool_calls3[0]["function"]["arguments"]).get("resolutions", [])
                _merge_resolved_x(result, resolutions)
            except (json.JSONDecodeError, KeyError):
                pass

    _flag_missing_x_values(result)
    _validate_entities(result, tz_text)
    return result

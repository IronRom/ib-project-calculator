import json
import re
from itertools import groupby
from typing import Optional

import anthropic
import httpx

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
    """Step 0: one line per active book — code + official name."""
    from app.models import ReferenceBook
    books = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    if not books:
        return ""
    lines = ["Активные справочники:"]
    for b in books:
        lines.append(f"  {b.code} — {b.official_name or b.code}")
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
Твоя задача — извлечь из Технического задания (ТЗ) все объекты и их параметры для расчёта стоимости ПИР по активному справочнику.

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
  НЕ назначай числовые значения — они берутся из справочника.
  Допустимые типы:
    "reconstruction"  — реконструкция (категория = reconstruction)
    "overhaul"        — капитальный ремонт (категория = overhaul)
    "asu"             — микропроцессорные контроллеры / АСУ / АСДКУ / АСКП упомянуты в ТЗ
    "deepening"       — заглубление подземной части > 10 м указано в ТЗ
    "seismic"         — сейсмика > 6 баллов МСК указана в ТЗ
    "fishery"         — сброс в водоём рыбохозяйственного значения (I, II кат.) указан в ТЗ
  НЕ добавляй районные, территориальные или климатические коэффициенты —
  для ПИР (проектных работ) они не применяются по Методике №620.

СТАДИЯ — из текста ТЗ:
  "П"   — только проектная документация
  "Р"   — только рабочая документация
  "П+Р" — проектная и рабочая документация вместе

АДРЕС — извлекай точно из ТЗ, без интерпретации."""

_COEFF_ITEM = {
    "type": "object",
    "required": ["name", "value"],
    "properties": {
        "name": {
            "type": "string",
            "enum": ["reconstruction", "overhaul", "asu", "deepening", "seismic", "fishery"],
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
                        "notes": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "tz_quote": {"type": "string", "description": "Дословная цитата из ТЗ (15-120 символов), обосновывающая эту позицию"},
                    },
                },
            },
            "stage": {"type": "string", "enum": ["П", "Р", "П+Р"]},
            "region": {"type": "string"},
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
    if not db or not detected_codes:
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


def _build_resolve_x_context(result: ExtractionResult, tz_text: str, hints_ctx: str) -> str:
    """Pass 3 context: entity list with null-x highlighted + hints + TZ."""
    null_indices = [i for i, e in enumerate(result.entities) if e.x_value is None]
    if not null_indices:
        return ""
    lines = [
        "═══ УТОЧНЕНИЕ ПАРАМЕТРА X ═══\n",
        "Анализ ТЗ уже выполнен. Ниже — все позиции с текущими X.",
        "Для позиций «X=null» определи X из текста ТЗ или из параметров других позиций.",
        "Если X не удаётся определить — оставь такие позиции без изменений.\n",
        "Позиции (индекс, таблица, наименование, X):",
    ]
    for i, e in enumerate(result.entities):
        x_str = f"{e.x_value} {e.x_unit}" if e.x_value is not None else "null ← ОПРЕДЕЛИТЬ"
        lines.append(f"  [{i}] Таблица {e.sbts_table}: {e.object_name} | {x_str}")
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
                step0_msg = (
                    "Определи, какой справочник (один или несколько) применим к данному ТЗ.\n"
                    "Ответь ТОЛЬКО кодами через запятую, без пояснений. Пример: СБЦП 81-2001-17\n\n"
                    f"{book_list}\n\n"
                    "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text
                )
                resp0 = client.messages.create(
                    model=settings.extraction_model,
                    max_tokens=100,
                    system=system_block,
                    messages=[{"role": "user", "content": step0_msg}],
                )
                raw = resp0.content[0].text.strip() if resp0.content else ""
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
            result = ExtractionResult(**block.input)
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
    resolve_ctx = _build_resolve_x_context(result, tz_text, hints_ctx)
    if resolve_ctx:
        resp3 = client.messages.create(
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
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
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
        return resp.json()

    async def _call_plain(messages: list[dict], max_tokens: int) -> str:
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
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
                step0_content = (
                    "Определи, какой справочник применим к данному ТЗ.\n"
                    "Ответь ТОЛЬКО кодами через запятую, без пояснений.\n\n"
                    f"{book_list}\n\n"
                    "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + tz_text
                )
                raw = await _call_plain([{"role": "user", "content": step0_content}], max_tokens=100)
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

    result = ExtractionResult(**json.loads(tool_calls[0]["function"]["arguments"]))
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
    resolve_ctx = _build_resolve_x_context(result, tz_text, hints_ctx)
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

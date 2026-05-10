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

def _build_types_context(db) -> str:
    """Pass 1 context: object types only — no coefficient conditions."""
    from app.models import BookObjectType, ReferenceBook, ReferenceRow

    active_books = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    if not active_books:
        return ""

    lines = ["═══ ДОСТУПНЫЕ ТИПЫ ОБЪЕКТОВ В АКТИВНЫХ СПРАВОЧНИКАХ ═══\n"]
    lines.append(
        "Каждый тип — отдельная позиция сметы. "
        "Если объект в ТЗ соответствует нескольким типам (КОС = биоочистка + доочистка + осадок) "
        "— создай позицию для каждого.\n"
        "Для каждой позиции укажи sbts_object_type_id из списка ниже.\n"
    )

    for book in active_books:
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
                unit_str = f" → {x_unit}" if x_unit else ""
                lines.append(f"  Таблица {table_num}: {type_name}{unit_str}")

        lines.append("")

    return "\n".join(lines)


def _build_conditions_context(db, entities: list[dict]) -> str:
    """Pass 2 context: keyed coefficient conditions for only the tables used in pass 1.

    Queries BookCondition filtered to (book_version_id, table_num) pairs
    found in extracted entities. Also includes book-wide conditions (table_num=NULL).
    Only conditions with coeff_key are included — those are the ones AI can assign.
    """
    from app.models import BookCondition, ReferenceBook

    # Collect needed (book_version_id, table_num) pairs
    needed: dict[int, set[Optional[int]]] = {}  # book_id → set of table_nums

    for entity in entities:
        sbts_code = (entity.get("sbts_code") or "").strip()
        table_num = entity.get("sbts_table")
        if not sbts_code or not table_num:
            continue

        book = (
            db.query(ReferenceBook)
            .filter(ReferenceBook.is_active == True)
            .filter(ReferenceBook.code.ilike(f"%{sbts_code.lstrip('СБЦП МРРсбцпмрр ').strip()}%"))
            .first()
        )
        if not book:
            # Try exact match
            book = (
                db.query(ReferenceBook)
                .filter(ReferenceBook.is_active == True)
                .filter(ReferenceBook.code == sbts_code)
                .first()
            )
        if not book:
            continue

        needed.setdefault(book.id, set()).add(table_num)
        needed[book.id].add(None)  # always include book-wide conditions

    if not needed:
        return ""

    lines = [
        "═══ КОЭФФИЦИЕНТЫ ДЛЯ ВЫЯВЛЕННЫХ ТАБЛИЦ ═══\n",
        "Просмотри каждую позицию из предыдущего ответа и определи — "
        "применим ли коэффициент на основе текста ТЗ. "
        "Вызови функцию assign_coefficients.\n",
    ]

    for book_id, table_nums in needed.items():
        book = db.get(ReferenceBook, book_id)
        conditions = (
            db.query(BookCondition)
            .filter(
                BookCondition.book_version_id == book_id,
                BookCondition.table_num.in_([t for t in table_nums if t is not None]),
                BookCondition.coeff_key.isnot(None),
            )
            .order_by(BookCondition.table_num)
            .all()
        )
        book_wide = (
            db.query(BookCondition)
            .filter(
                BookCondition.book_version_id == book_id,
                BookCondition.table_num.is_(None),
                BookCondition.coeff_key.isnot(None),
            )
            .all()
        )
        all_conds = conditions + book_wide
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
                if c.coeff_min is not None and c.coeff_max is not None:
                    coeff_str = (
                        f"×{c.coeff_min}"
                        if c.coeff_min == c.coeff_max
                        else f"×{c.coeff_min}–{c.coeff_max}"
                    )
                else:
                    coeff_str = ""
                row_hint = f" ({c.row_range})" if c.row_range else ""
                lines.append(
                    f"    • {c.condition_short}{row_hint}: {coeff_str} [key={c.coeff_key}]"
                )
        lines.append("")

    return "\n".join(lines)


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
            "description": "Тип коэффициента",
        },
        "value": {"type": "number", "const": 1, "description": "Всегда 1 — признак применимости"},
        "reason": {"type": "string", "description": "Цитата или ссылка из ТЗ"},
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
                        "category": {
                            "type": "string",
                            "enum": ["new_construction", "reconstruction", "overhaul"],
                        },
                        "object_type": {"type": "string"},
                        "object_name": {"type": "string"},
                        "address": {"type": "string"},
                        "sbts_code": {"type": "string", "description": "Код СБЦП, например 81-2001-17"},
                        "sbts_table": {"type": "integer", "description": "Номер таблицы СБЦП"},
                        "sbts_object_type_id": {
                            "type": "integer",
                            "description": "ID типа объекта из списка [type_id=X] в справочнике — обязательно указывать если список доступен",
                        },
                        "x_value": {"type": "number", "description": "Параметр X для ОДНОГО объекта"},
                        "x_unit": {"type": "string"},
                        "quantity": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Количество одинаковых объектов. По умолчанию 1.",
                        },
                        "coefficients": {
                            "type": "array",
                            "description": "Флаги применимых коэффициентов. value всегда 1.",
                            "items": _COEFF_ITEM,
                        },
                        "notes": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
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
    "description": (
        "Присвоить применимые коэффициенты к позициям ПИР на основе условий справочника и текста ТЗ. "
        "Указывай только позиции, где есть хотя бы один применимый коэффициент."
    ),
    "input_schema": {
        "type": "object",
        "required": ["assignments"],
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["entity_index", "coefficients"],
                    "properties": {
                        "entity_index": {
                            "type": "integer",
                            "description": "0-based индекс позиции из предыдущего ответа",
                        },
                        "coefficients": {
                            "type": "array",
                            "items": _COEFF_ITEM,
                        },
                    },
                },
            }
        },
    },
}

# OpenAI-compatible wrappers for OpenRouter
EXTRACTION_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": EXTRACTION_TOOL["name"],
        "description": EXTRACTION_TOOL["description"],
        "parameters": EXTRACTION_TOOL["input_schema"],
    },
}


# ── Extraction functions ──────────────────────────────────────────────────────

def _user_msg_1(text: str, db) -> str:
    types_ctx = _build_types_context(db) if db is not None else ""
    msg = "Проанализируй следующее техническое задание и извлеки все объекты:\n\n"
    if types_ctx:
        msg += types_ctx + "\n\n"
    msg += "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + text[: settings.max_tz_chars]
    return msg


def _merge_coefficients(result: ExtractionResult, assignments: list[dict]) -> None:
    """Merge pass-2 coefficient assignments into pass-1 entities (no duplicates by name)."""
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


async def extract_entities(text: str, db=None) -> ExtractionResult:
    """Two-pass extraction (Anthropic):
    Pass 1 — object types context → entities with sbts_table.
    Pass 2 — conditions for those tables → coefficient assignments merged in.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_block = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    user_msg_1 = _user_msg_1(text, db)

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    resp1 = client.messages.create(
        model=settings.extraction_model,
        max_tokens=4096,
        system=system_block,
        messages=[{"role": "user", "content": user_msg_1}],
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
    if not result.entities or db is None:
        return result

    # ── Pass 2: conditions for extracted tables only ───────────────────────────
    entities_dicts = [e.model_dump() for e in result.entities]
    conditions_ctx = _build_conditions_context(db, entities_dicts)

    if not conditions_ctx:
        return result  # no keyed conditions for these tables — skip pass 2

    resp2 = client.messages.create(
        model=settings.extraction_model,
        max_tokens=1024,
        system=system_block,  # same system → prompt cache hit on TZ text
        messages=[
            {"role": "user", "content": user_msg_1},   # cached
            {"role": "assistant", "content": resp1.content},  # pass 1 result
            {"role": "user", "content": conditions_ctx},
        ],
        tools=[COEFF_TOOL],
        tool_choice={"type": "tool", "name": "assign_coefficients"},
    )

    for block in resp2.content:
        if block.type == "tool_use" and block.name == "assign_coefficients":
            _merge_coefficients(result, block.input.get("assignments", []))
            break

    return result


async def extract_entities_openrouter(text: str, model_id: str, db=None) -> ExtractionResult:
    """Single-pass extraction via OpenRouter (no pass-2 coefficient verification)."""
    types_ctx = _build_types_context(db) if db is not None else ""
    user_content = (
        "Проанализируй следующее техническое задание и извлеки все объекты. "
        "Обязательно вызови функцию extract_pir_entities с результатами.\n\n"
    )
    if types_ctx:
        user_content += types_ctx + "\n\n"
    user_content += "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + text[: settings.max_tz_chars]

    payload = {
        "model": model_id,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "tools": [EXTRACTION_TOOL_OPENAI],
    }

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://ib-pir-calculator.ru",
                "X-Title": "IB PIR Calculator",
            },
        )
        resp.raise_for_status()

    data = resp.json()
    tool_calls = (
        data.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
    )
    if not tool_calls:
        return ExtractionResult(
            entities=[],
            stage="П+Р",
            region="",
            missing_data=[f"OpenRouter ({model_id}): не вернул tool_call"],
            overall_confidence=0.0,
        )

    args = json.loads(tool_calls[0]["function"]["arguments"])
    return ExtractionResult(**args)

import json
import re
from typing import Optional

import anthropic
import httpx

from app.config import settings
from app.schemas import ExtractionResult

_STRIP_TYPE_SUFFIX = re.compile(
    r'\s+(производительностью|мощностью|объёмом|длиной|протяженностью)'
    r'(\s*[\(,].*)?$',
    re.IGNORECASE,
)
_STRIP_RANGE_SUFFIX = re.compile(
    r'[,:]?\s*(до|свыше|от)\s+[\d,].*$',
    re.IGNORECASE,
)


def _build_reference_context(db) -> str:
    """Build prompt section: object types + coefficient conditions from active reference books."""
    from app.models import BookCondition, BookObjectType, ReferenceBook, ReferenceRow

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

        table_conditions: dict[int | None, list[BookCondition]] = {}
        for cond in db.query(BookCondition).filter(BookCondition.book_version_id == book.id).all():
            table_conditions.setdefault(cond.table_num, []).append(cond)

        if types:
            # Group by table_num so conditions appear once per table
            from itertools import groupby
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
                _append_conditions(lines, table_conditions.get(table_num, []))
        else:
            # Fallback: derive from reference_rows when book_object_types not yet populated
            rows = (
                db.query(ReferenceRow.table_num, ReferenceRow.description, ReferenceRow.x_unit)
                .filter(ReferenceRow.book_version_id == book.id)
                .order_by(ReferenceRow.table_num, ReferenceRow.id)
                .all()
            )
            seen: set[tuple] = set()
            last_table = None
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
                if table_num != last_table:
                    _append_conditions(lines, table_conditions.get(table_num, []))
                    last_table = table_num

        # Book-wide conditions
        book_wide = table_conditions.get(None, [])
        if book_wide:
            lines.append("  Общие коэффициенты (применимы ко всем таблицам):")
            _append_conditions(lines, book_wide, indent="    ")

        lines.append("")

    return "\n".join(lines)


def _append_conditions(lines: list[str], conditions: list, indent: str = "    ") -> None:
    if not conditions:
        return
    lines.append(f"{indent}Коэффициенты:")
    for c in conditions:
        if c.coeff_min is not None and c.coeff_max is not None:
            if c.coeff_min == c.coeff_max:
                coeff_str = f"×{c.coeff_min}"
            else:
                coeff_str = f"×{c.coeff_min}–{c.coeff_max}"
        else:
            coeff_str = ""
        key_hint = f" [key={c.coeff_key}]" if c.coeff_key else ""
        row_hint = f" ({c.row_range})" if c.row_range else ""
        lines.append(f"{indent}  • {c.condition_short}{row_hint}: {coeff_str}{key_hint}")

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
                        "sbts_object_type_id": {"type": "integer", "description": "ID типа объекта из списка [type_id=X] в справочнике — обязательно указывать если список доступен"},
                        "x_value": {"type": "number", "description": "Параметр X для ОДНОГО объекта"},
                        "x_unit": {"type": "string"},
                        "quantity": {"type": "integer", "minimum": 1, "description": "Количество одинаковых объектов. По умолчанию 1. Использовать если несколько объектов в одном месте — формула применяется quantity раз"},
                        "coefficients": {
                            "type": "array",
                            "description": "Флаги применимых коэффициентов. value всегда 1 — числовые значения берутся из справочника.",
                            "items": {
                                "type": "object",
                                "required": ["name", "value"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "enum": ["reconstruction", "overhaul", "asu", "deepening", "seismic", "fishery"],
                                        "description": "Тип коэффициента",
                                    },
                                    "value": {
                                        "type": "number",
                                        "const": 1,
                                        "description": "Всегда 1 — признак применимости",
                                    },
                                    "reason": {
                                        "type": "string",
                                        "description": "Цитата или ссылка из ТЗ обосновывающая применение",
                                    },
                                },
                            },
                        },
                        "notes": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "stage": {
                "type": "string",
                "enum": ["П", "Р", "П+Р"],
                "description": "Стадия проектирования",
            },
            "region": {"type": "string"},
            "missing_data": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Что не удалось определить из ТЗ",
            },
            "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}


# OpenAI-compatible tool schema for OpenRouter (same JSON Schema, different wrapper)
EXTRACTION_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": EXTRACTION_TOOL["name"],
        "description": EXTRACTION_TOOL["description"],
        "parameters": EXTRACTION_TOOL["input_schema"],
    },
}


async def extract_entities_openrouter(text: str, model_id: str, db=None) -> ExtractionResult:
    ref_context = _build_reference_context(db) if db is not None else ""
    user_content = (
        "Проанализируй следующее техническое задание и извлеки все объекты. "
        "Обязательно вызови функцию extract_pir_entities с результатами.\n\n"
    )
    if ref_context:
        user_content += ref_context + "\n\n"
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
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("tool_calls", [])
    )
    if not tool_calls:
        return ExtractionResult(
            entities=[],
            stage="П+Р",
            region="",
            missing_data=[f"OpenRouter ({model_id}): не вернул tool_call — модель не поддерживает принудительный вызов инструмента"],
            overall_confidence=0.0,
        )

    args = json.loads(tool_calls[0]["function"]["arguments"])
    return ExtractionResult(**args)


async def extract_entities(text: str, db=None) -> ExtractionResult:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    ref_context = _build_reference_context(db) if db is not None else ""
    user_content = "Проанализируй следующее техническое задание и извлеки все объекты:\n\n"
    if ref_context:
        user_content += ref_context + "\n\n"
    user_content += "═══ ТЕХНИЧЕСКОЕ ЗАДАНИЕ ═══\n\n" + text[: settings.max_tz_chars]

    response = client.messages.create(
        model=settings.extraction_model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_pir_entities"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_pir_entities":
            return ExtractionResult(**block.input)

    return ExtractionResult(entities=[], missing_data=["Не удалось извлечь данные из ТЗ"])

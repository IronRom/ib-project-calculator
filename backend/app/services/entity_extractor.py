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
    """Build a prompt section listing unique object types from all active reference books."""
    from app.models import ReferenceBook, ReferenceRow

    active_books = db.query(ReferenceBook).filter(ReferenceBook.is_active == True).all()
    if not active_books:
        return ""

    lines = ["═══ ДОСТУПНЫЕ ТИПЫ ОБЪЕКТОВ В АКТИВНЫХ СПРАВОЧНИКАХ ═══\n"]
    lines.append(
        "Каждый тип — отдельная позиция сметы. "
        "Если объект в ТЗ соответствует нескольким типам (КОС = биоочистка + доочистка + осадок) "
        "— создай позицию для каждого.\n"
    )

    for book in active_books:
        lines.append(f"{book.official_name or book.code} (код: {book.code}):")

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
            # Strip range suffix, then production-capacity suffix to get type name
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

SYSTEM_PROMPT = """Ты опытный сметчик ПИР (проектно-изыскательских работ) в России.
Твоя задача — извлечь из Технического задания (ТЗ) все объекты и их параметры для расчёта стоимости ПИР по СБЦП 81-2001-17.

═══ ПРАВИЛА ИЗВЛЕЧЕНИЯ ═══

КАТЕГОРИЯ объекта (строго из ТЗ):
  new_construction — новое строительство
  reconstruction   — реконструкция
  overhaul         — капитальный ремонт

ПАРАМЕТР X — только в единицах таблицы СБЦП, не в единицах ТЗ:
  Таблица 1  (НС I подъёма)          → тыс. м³/ч
  Таблица 2  (ВЗУ подземные)         → м³/ч
  Таблица 3  (Водовод)               → км
  Таблица 4  (ВОС)                   → тыс. м³/сут
  Таблица 5  (НС II подъёма)         → тыс. м³/ч
  Таблица 5  (Резервуары)            → тыс. м³
  Таблица 8  (Коллектор)             → км
  Таблица 9  (КНС)                   → тыс. м³/ч
  Таблица 10 (ОС канализации)        → тыс. м³/сут
  Таблица 11 (Обработка осадка)      → т/сут (сухого вещества)
  Таблица 14 (Выпуски, дюкеры)       → м
  Пример: ТЗ пишет "650 тыс. м³/сут" → x_value=650, x_unit="тыс. м³/сут"
  Пример: ТЗ пишет "104 000 м³/сут"  → x_value=104, x_unit="тыс. м³/сут"

ОДИН ТЗ → НЕСКОЛЬКО СТРОК СБЦП:
  Сложный объект (ОС, ВЗУ, КНС с вспомогательными зданиями) порождает
  несколько позиций в смете — по одной на каждый пункт СБЦП.
  Извлеки ВСЕ, даже если X неизвестен (x_value=null).

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
                        "x_value": {"type": "number"},
                        "x_unit": {"type": "string"},
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

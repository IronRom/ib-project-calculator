import json

import anthropic
import httpx

from app.config import settings
from app.schemas import ExtractionResult

SYSTEM_PROMPT = """Ты опытный сметчик ПИР (проектно-изыскательских работ) в России.
Твоя задача — извлечь из Технического задания (ТЗ) все объекты и их параметры для расчёта стоимости ПИР по СБЦП 81-2001-17.

═══ ПРАВИЛА ИЗВЛЕЧЕНИЯ ═══

КАТЕГОРИЯ объекта (строго из ТЗ):
  new_construction — новое строительство
  reconstruction   — реконструкция
  overhaul         — капитальный ремонт

ПАРАМЕТР X — только в единицах таблицы СБЦП, не в единицах ТЗ:
  Таблица 1  (НС I подъёма)          → тыс. м³/сут
  Таблица 2  (ВЗУ подземные)         → м³/ч
  Таблица 3  (Водовод)               → км
  Таблица 4  (ВОС)                   → тыс. м³/сут
  Таблица 5  (НС II подъёма)         → тыс. м³/ч
  Таблица 5  (Резервуары)            → тыс. м³
  Таблица 8  (Коллектор)             → км
  Таблица 9  (КНС)                   → тыс. м³/сут
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


async def extract_entities_openrouter(text: str, model_id: str) -> ExtractionResult:
    payload = {
        "model": model_id,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Проанализируй следующее техническое задание и извлеки все объекты:\n\n{text[:50000]}",
            },
        ],
        "tools": [EXTRACTION_TOOL_OPENAI],
    }
    payload["messages"][1]["content"] = (
        "Проанализируй следующее техническое задание и извлеки все объекты. "
        "Обязательно вызови функцию extract_pir_entities с результатами.\n\n"
        + text[:50000]
    )

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


async def extract_entities(text: str) -> ExtractionResult:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Проанализируй следующее техническое задание и извлеки все объекты:\n\n{text[:50000]}",
            }
        ],
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_pir_entities"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_pir_entities":
            return ExtractionResult(**block.input)

    return ExtractionResult(entities=[], missing_data=["Не удалось извлечь данные из ТЗ"])

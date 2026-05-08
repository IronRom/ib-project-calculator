import anthropic

from app.config import settings
from app.schemas import ExtractionResult

SYSTEM_PROMPT = """Ты опытный сметчик ПИР (проектно-изыскательских работ) в России.
Твоя задача — извлечь из Технического задания (ТЗ) все объекты строительства и их параметры для расчёта стоимости ПИР по справочнику базовых цен (СБЦП).

Для каждого объекта определи:
1. Категория: new_construction (новое строительство), reconstruction (реконструкция), overhaul (капитальный ремонт)
2. Тип объекта по СБЦП (КНС, ВЗУ, ОС, Водовод, Коллектор, Насосная станция I подъёма, Жилой дом, Промышленное здание и т.д.)
3. Название объекта из ТЗ
4. Адрес/регион (влияет на коэффициенты)
5. Параметр X — главный натуральный показатель для формулы СБЦП (производительность, длина, площадь и т.д.)
6. Единица X (тыс. м³/ч, км, м, тыс. м³/сут, м², т/сут и т.д.)
7. Номер таблицы СБЦП 81-2001-17 если применимо (1=НС I подъёма, 2=ВЗУ подземные, 3=Водовод, 4=ВОС, 5=НС II подъёма+резервуары, 8=Коллектор, 9=КНС, 10=ОС канализации, 11=Осадок, 14=Выпуски)
8. Применимые коэффициенты (реконструкция×1.5, заглубление, АСУ, тип труб и т.д.)
9. Стадия проектирования (П, Р, или П+Р)
10. Что не удалось определить

Важно: один ТЗ может содержать несколько объектов — извлеки ВСЕ.
При реконструкции и капремонте — выбирай самую дорогую категорию из применимых."""

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
                            "items": {
                                "type": "object",
                                "required": ["name", "value"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "value": {"type": "number"},
                                    "source": {"type": "string"},
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

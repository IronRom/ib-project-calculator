"""Уточнение расчёта свободным текстом: targeted AI-патч позиций.

Менеджер пишет «длина сети 1800 м, ООС не делаем, котёл один 4 МВт» —
модель применяет ДЕЛЬТУ к текущим позициям (не переэкстракция с нуля):
обновления полей, добавления, удаления. Возвращается diff для
предпросмотра/истории; суммы до/после считает вызывающая сторона.

Модель — из app_settings['clarification_model'] (админка), temperature=0.
"""
from __future__ import annotations

import copy
import json
from typing import Any

import httpx

from app.config import settings

CLARIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "patch_entities",
        "description": "Применить уточнение менеджера к позициям расчёта",
        "parameters": {
            "type": "object",
            "required": ["updates", "adds", "removes", "summary"],
            "properties": {
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["index", "field", "value"],
                        "properties": {
                            "index": {"type": "integer",
                                      "description": "0-based индекс позиции"},
                            "field": {
                                "type": "string",
                                "enum": ["x_value", "x_unit", "quantity",
                                         "sections", "object_name", "category",
                                         "deleted", "pd_sections_pct",
                                         "rd_sections_pct"],
                            },
                            "value": {"description": "новое значение"},
                            "reason": {"type": "string",
                                       "description": "цитата/пересказ уточнения"},
                        },
                    },
                },
                "adds": {
                    "type": "array",
                    "description": "Новые позиции (只 если уточнение прямо требует)",
                    "items": {"type": "object"},
                },
                "removes": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Индексы позиций к удалению (мягкому)",
                },
                "summary": {"type": "string",
                            "description": "1-2 предложения: что изменено"},
            },
        },
    },
}

SYSTEM = (
    "Ты применяешь уточнение менеджера к позициям сметы ПИР. "
    "Меняй ТОЛЬКО то, о чём прямо сказано в уточнении. Не пересматривай "
    "выбор справочников и таблиц без явного указания. Числа с единицами "
    "конвертируй в единицы позиции (1,8 км → 1800 п.м если x_unit='п.м'). "
    "«Не делаем/исключить раздел X» → убери код из sections (если список "
    "пуст — оставь пустым, это 100%). «Убрать позицию» → removes. "
    "Вызови функцию patch_entities ровно один раз."
)


async def clarify_entities(
    entities: list[dict[str, Any]], text: str, model_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Возвращает (новые entities, diff). Бросает ValueError при сбое AI."""
    brief = [
        {k: e.get(k) for k in ("object_name", "sbts_code", "sbts_table",
                               "x_value", "x_unit", "quantity", "sections",
                               "category", "deleted")}
        for e in entities
    ]
    user = (
        "ТЕКУЩИЕ ПОЗИЦИИ (index = порядковый номер с 0):\n"
        + json.dumps(brief, ensure_ascii=False, indent=1)
        + "\n\nУТОЧНЕНИЕ МЕНЕДЖЕРА:\n" + text.strip()
    )
    payload = {
        "model": model_id,
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "tools": [CLARIFY_TOOL],
    }
    async with httpx.AsyncClient(timeout=180) as http:
        resp = await http.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://ib-pir-calculator.ru",
                "X-Title": "IB PIR Calculator",
            },
        )
    if not resp.is_success:
        raise ValueError(f"OpenRouter {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    tcs = data.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
    if not tcs:
        raise ValueError("Модель не вернула patch_entities — переформулируйте уточнение")
    try:
        patch = json.loads(tcs[0]["function"]["arguments"])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный патч от модели: {exc}") from exc

    new_entities = copy.deepcopy(entities)
    changes: list[dict[str, Any]] = []
    for u in patch.get("updates") or []:
        i = u.get("index")
        if not isinstance(i, int) or not (0 <= i < len(new_entities)):
            continue
        field = u.get("field")
        if field not in ("x_value", "x_unit", "quantity", "sections",
                         "object_name", "category", "deleted",
                         "pd_sections_pct", "rd_sections_pct"):
            continue
        old = new_entities[i].get(field)
        new_entities[i][field] = u.get("value")
        changes.append({"type": "update", "index": i,
                        "object_name": new_entities[i].get("object_name", ""),
                        "field": field, "old": old, "new": u.get("value"),
                        "reason": u.get("reason", "")})
    for i in sorted({i for i in (patch.get("removes") or [])
                     if isinstance(i, int) and 0 <= i < len(new_entities)},
                    reverse=True):
        changes.append({"type": "remove", "index": i,
                        "object_name": new_entities[i].get("object_name", "")})
        new_entities[i]["deleted"] = True
    for add in patch.get("adds") or []:
        if isinstance(add, dict) and add.get("object_name"):
            add.setdefault("category", "new_construction")
            add.setdefault("quantity", 1)
            add.setdefault("coefficients", [])
            add.setdefault("address", "")
            add.setdefault("object_type", add.get("object_name", ""))
            new_entities.append(add)
            changes.append({"type": "add",
                            "object_name": add.get("object_name", "")})

    diff = {"summary": patch.get("summary", ""), "changes": changes}
    return new_entities, diff


def get_setting(db, key: str, default: str = "") -> str:
    from app.models import AppSetting
    rec = db.query(AppSetting).filter(AppSetting.key == key).first()
    return rec.value if rec else default

"""Parse СБЦП/СБЦ PDF into reference_rows via Claude vision."""
import base64
import json
import re
from pathlib import Path
from typing import Any, Callable

import anthropic

from app.config import settings

DEFAULT_PARSE_PROMPT = """Ты извлекаешь данные из страницы справочника базовых цен (СБЦП/СБЦ) на проектные или изыскательские работы.

На странице могут быть:
1. Заголовок таблицы с её номером (например "Таблица N 1", "ТАБЛИЦА 9")
2. Строки с ценами в формате: N п/п | Наименование | Единица | a | b
3. Методические пояснения (текст без таблицы цен) — пропусти их

Верни JSON строго в формате:
{
  "table_num": <номер таблицы (целое) или null если таблица не началась>,
  "official_name": "<официальное наименование документа если видно на этой странице, иначе null>",
  "rows": [
    {
      "row_num": "п.1",
      "description": "Полное описание позиции включая диапазон X",
      "x_min": <число или null>,
      "x_max": <число или null>,
      "x_unit": "тыс. м³/сут",
      "a": <число>,
      "b": <число или null>
    }
  ]
}

Правила:
- Если на странице нет строк с числами a и b — верни "rows": []
- x_min/x_max: извлекай из фраз "до X", "свыше X до Y", "от X до Y"
  Пример: "свыше 100 до 200" → x_min=100, x_max=200
  Пример: "до 70" → x_min=null, x_max=70
  Пример: "свыше 2100" → x_min=2100, x_max=null
- x_unit: единица измерения из колонки 3 (тыс. м³/сут, м³/ч, км, м, т/сут и т.д.)
  Если единица повторяется (обозначена как ") — подставь предыдущую
- a и b — числа из колонок 4 и 5. b может быть дробным (0,15 → 0.15)
- row_num: "п.1", "п.2", ... по порядку в таблице
- Запятые в числах заменяй на точки: 3 790 180 → 3790180, 17 130 → 17130
- Если таблица продолжается со страницы — table_num равен номеру продолжающейся таблицы
- Верни ТОЛЬКО JSON, без markdown и пояснений"""


def parse_reference_pdf(
    pdf_path: str,
    parse_prompt: str | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Parse PDF page by page via Claude vision.
    Returns list of row dicts ready for DB insert.
    on_progress(page_num, total_pages, status_message)
    """
    from pdf2image import convert_from_path

    prompt = parse_prompt or DEFAULT_PARSE_PROMPT
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    images = convert_from_path(pdf_path, dpi=150, fmt="jpeg")
    total = len(images)
    all_rows: list[dict[str, Any]] = []
    current_table_num: int | None = None
    official_name: str | None = None

    for i, img in enumerate(images):
        page_num = i + 1
        if on_progress:
            on_progress(page_num, total, f"Страница {page_num}/{total}")

        # Convert image to base64
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.standard_b64encode(buf.getvalue()).decode()

        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)
        except Exception:
            continue  # skip unparseable pages

        if data.get("official_name") and not official_name:
            official_name = data["official_name"]

        if data.get("table_num") is not None:
            current_table_num = int(data["table_num"])

        if not current_table_num:
            continue

        for row in data.get("rows", []):
            try:
                all_rows.append(
                    {
                        "table_num": current_table_num,
                        "row_num": str(row.get("row_num", "")).strip() or None,
                        "description": str(row.get("description", "")).strip() or None,
                        "x_min": float(row["x_min"]) if row.get("x_min") is not None else None,
                        "x_max": float(row["x_max"]) if row.get("x_max") is not None else None,
                        "x_unit": str(row.get("x_unit", "")).strip() or None,
                        "a": float(row["a"]),
                        "b": float(row["b"]) if row.get("b") is not None else None,
                        "notes": None,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue

    return all_rows, official_name

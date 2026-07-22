"""Parse СБЦП/СБЦ PDF into reference_rows via Claude vision."""
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_RANGE_ONLY = re.compile(r'^(до|свыше|от)\s+[\d,]', re.IGNORECASE)
_STRIP_TRAILING_RANGE = re.compile(r'\s+(от|свыше)\s+[\d,].*$', re.IGNORECASE)
_STRIP_TYPE_SUFFIX = re.compile(
    r'\s+(производительностью|мощностью|объёмом|длиной|протяженностью)'
    r'(\s*[\(,по].*)?$',
    re.IGNORECASE,
)
_STRIP_RANGE_COLON = re.compile(r'[,:]?\s*(до|свыше|от)\s+[\d,].*$', re.IGNORECASE)
# Values Claude sometimes returns instead of real data
_NULL_LIKE = frozenset({'none', 'null', 'nan', '-', '—', '"', "'"})


def _derive_type_name(description: str | None) -> str | None:
    """Extract the structure type name from a full description, stripping range and unit parts."""
    if not description:
        return None
    name = _STRIP_RANGE_COLON.sub('', description).strip()
    name = _STRIP_TYPE_SUFFIX.sub('', name).strip().rstrip(',:').strip()
    return name if name and name.lower() not in _NULL_LIKE else None


def rebuild_object_types(db, book_version_id: int) -> int:
    """
    Derive unique object types from reference_row descriptions, populate book_object_types,
    and set object_type_id FK on every reference_row. Idempotent — clears previous types first.
    Returns number of distinct types created.
    """
    from app.models import BookObjectType, ReferenceRow

    rows = (
        db.query(ReferenceRow)
        .filter(ReferenceRow.book_version_id == book_version_id)
        .order_by(ReferenceRow.table_num, ReferenceRow.id)
        .all()
    )

    db.query(BookObjectType).filter(BookObjectType.book_version_id == book_version_id).delete()
    db.flush()

    seen: dict[tuple[int, str], BookObjectType] = {}

    for row in rows:
        type_name = _derive_type_name(row.description)
        if not type_name:
            row.object_type_id = None
            continue
        key = (row.table_num, type_name)
        if key not in seen:
            bot = BookObjectType(
                book_version_id=book_version_id,
                name=type_name,
                table_num=row.table_num,
            )
            db.add(bot)
            db.flush()
            seen[key] = bot
        row.object_type_id = seen[key].id

    db.commit()
    return len(seen)


def _fix_continuation_descriptions(rows: list[dict]) -> list[dict]:
    """Prepend parent type prefix to range-only descriptions (cross-page propagation)."""
    type_prefix: dict[int, str] = {}  # table_num -> last known type name

    for row in rows:
        tnum = row.get('table_num')
        desc = (row.get('description') or '').strip()
        if not desc or tnum is None or desc.lower() in _NULL_LIKE:
            continue

        if _RANGE_ONLY.match(desc):
            prefix = type_prefix.get(tnum)
            if prefix:
                x_unit = (row.get('x_unit') or '').strip()
                # Skip ditto marks and null-like units; avoid duplicating units already in prefix
                real_unit = x_unit if x_unit and x_unit.lower() not in _NULL_LIKE else ''
                unit_suffix = f' {real_unit}' if real_unit and real_unit not in prefix else ''
                row['description'] = f'{prefix} {desc}{unit_suffix}'.strip()
        else:
            # Strip trailing range to get the type-name prefix for subsequent rows.
            # Only update if this is a genuinely different (non-null-like) description.
            prefix = _STRIP_TRAILING_RANGE.sub('', desc).strip().rstrip(',:').strip()
            if prefix and prefix.lower() not in _NULL_LIKE:
                type_prefix[tnum] = prefix

    return rows


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
      "row_num": "п.6",
      "description": "Полное описание позиции включая тип объекта и диапазон X",
      "x_min": <число или null>,
      "x_max": <число или null>,
      "x_unit": "тыс. м³/сут",
      "a": <число>,
      "b": <число или null>
    }
  ]
}

Правила:

row_num — ОБЯЗАТЕЛЬНО берётся из колонки 1 таблицы PDF. Это число из документа.
  Формат: "п." + число из колонки 1. Пример: столбец 1 показывает "6" → row_num="п.6".
  НИКОГДА не нумеруй строки сам. Если таблица продолжается со страницы —
  числа в колонке 1 продолжают ряд предыдущей страницы (например, начинаются с 11, 12, ...).

x_min/x_max — извлекай из фраз "до X", "свыше X до Y", "от X до Y":
  "свыше 100 до 200" → x_min=100, x_max=200
  "до 70"            → x_min=null, x_max=70
  "свыше 2100"       → x_min=2100, x_max=null

x_unit — единица измерения из колонки 3 (тыс. м³/сут, м³/ч, км, м, т/сут, т/г., шт. и т.д.)
  Если в колонке 3 стоит знак " или то же самое (диттометка "повторить") —
  ОБЯЗАТЕЛЬНО подставь единицу из предыдущей строки той же таблицы.
  НИКОГДА не возвращай символ " или пустую строку в поле x_unit — только реальную единицу.

a и b — числа из колонок 4 и 5. b может быть дробным (0,15 → 0.15).
  Запятые в числах заменяй на точки, пробелы убирай: 3 790 180 → 3790180.

Если таблица продолжается со страницы — table_num равен номеру продолжающейся таблицы.
Если на странице нет строк с числами a и b — верни "rows": [].

ВАЖНО — поле description должно быть ПОЛНЫМ для каждой строки:
В таблицах СБЦП часто бывают группы строк: первая строка содержит название типа объекта
и первый диапазон, последующие строки — только диапазон ("свыше 100 до 200").
Для КАЖДОЙ строки группы в поле description укажи ПОЛНОЕ описание с названием типа объекта.

Пример таблицы в PDF:
  6  "Сооружения мех. обезвоживания осадка, до 1 т/сут"       т/сут   450000  120000
  7  "свыше 1 до 5"                                            "       680000  95000
  8  "свыше 5 до 10"                                           "       910000  72000

Правильный вывод:
  {"row_num":"п.6","description":"Сооружения мех. обезвоживания осадка производительностью, т/сут: до 1","x_min":null,"x_max":1,"x_unit":"т/сут","a":450000,"b":120000}
  {"row_num":"п.7","description":"Сооружения мех. обезвоживания осадка производительностью, т/сут: свыше 1 до 5","x_min":1,"x_max":5,"x_unit":"т/сут","a":680000,"b":95000}
  {"row_num":"п.8","description":"Сооружения мех. обезвоживания осадка производительностью, т/сут: свыше 5 до 10","x_min":5,"x_max":10,"x_unit":"т/сут","a":910000,"b":72000}

Никогда не возвращай в description только диапазон без названия типа объекта.
Верни ТОЛЬКО JSON, без markdown и пояснений."""


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
    last_x_unit: str | None = None  # cross-page ditto-mark resolution

    for i, img in enumerate(images):
        page_num = i + 1
        if on_progress:
            on_progress(page_num, total, f"Страница {page_num}/{total}")

        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.standard_b64encode(buf.getvalue()).decode()

        try:
            resp = client.messages.create(
                temperature=0,
                model=settings.extraction_model,
                max_tokens=4096,
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
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            # Extract just the JSON object — Claude sometimes adds trailing text
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1:
                raw = raw[start : end + 1]

            data = json.loads(raw)
        except Exception:
            logger.exception("Failed to parse page %d/%d of %s", page_num, total, pdf_path)
            continue

        if data.get("official_name") and not official_name:
            official_name = data["official_name"]

        if data.get("table_num") is not None:
            current_table_num = int(data["table_num"])

        if not current_table_num:
            continue

        for row in data.get("rows", []):
            try:
                # Resolve x_unit: ditto marks → inherit from last real unit
                raw_unit = (row.get("x_unit") or "")
                raw_unit = raw_unit if isinstance(raw_unit, str) else ""
                raw_unit = raw_unit.strip()
                if raw_unit and raw_unit not in ('"', "'", '“', '”'):
                    last_x_unit = raw_unit
                    resolved_unit: str | None = raw_unit
                else:
                    resolved_unit = last_x_unit  # ditto: use previous

                # Avoid storing "None" string from str(None)
                raw_desc = row.get("description")
                description = raw_desc.strip() if isinstance(raw_desc, str) else None

                all_rows.append(
                    {
                        "table_num": current_table_num,
                        "row_num": str(row.get("row_num", "")).strip() or None,
                        "description": description or None,
                        "x_min": float(row["x_min"]) if row.get("x_min") is not None else None,
                        "x_max": float(row["x_max"]) if row.get("x_max") is not None else None,
                        "x_unit": resolved_unit,
                        "a": float(row["a"]),
                        "b": float(row["b"]) if row.get("b") is not None else None,
                        "notes": None,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue

    return _fix_continuation_descriptions(all_rows), official_name

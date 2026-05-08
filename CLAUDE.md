# ИБ Калькулятор ПИР

## Obsidian

Все задачи и лог — через Obsidian vault13.
Проект: `01 Actions/Projects/Project - IB AI Calculator PIR.md`
Каждое изменение кода требует задачи в vault. Команда: `obsidian vault=vault13 ...`

## Архитектура

> При изменении архитектуры — вносить правки в эту секцию.

**Стек**: Next.js 14 (App Router) + FastAPI + PostgreSQL + Claude API (claude-sonnet-4-6)
**Дизайн**: `design/DESIGN_SYSTEM.md`

### Поток данных

```
Upload ТЗ файлы в проект
  → POST /api/projects/{id}/calculate
  → document_parser: PDF/DOCX → plain text
  → entity_extractor: Claude API → ExtractionResult
  → Экран /entities: таблица для валидации (Категория / Тип / Адрес / X / Коэф.)
  → [Фаза 2] confirm → calculator → results → export 2ПС ИР
```

### Data models (PostgreSQL)

- `reference_books` — СБЦП/МРР версии (requires_validation → consistent → archived)
- `book_object_types` — типы объектов из справочника (КНС, Водовод, ...), извлекаются при парсинге
- `reference_rows` — строки справочника (table_num, x_min, x_max, a, b)
- `price_indices` — квартальные индексы Минстроя (Прил.3 п.1 = проектные работы)
- `users` — role: admin|user, can_calculate=false по умолчанию
- `projects` — контейнер файлов ТЗ per user
- `project_files` — загруженные файлы ТЗ (pdf_path, extracted_text)
- `calculations` — хранит book_version_id (FK, зафиксирован), extracted_entities JSONB
- `audit_logs`

### Классификация объекта (AI извлекает из ТЗ)

- **Категория**: new_construction | reconstruction | overhaul
- **Тип объекта**: из `book_object_types` активного справочника
- **Адрес/регион**: влияет на сейсмику, МРР и другие коэффициенты

### Формула расчёта

```
(a + b×X) × коэф. × индекс × стадия_фактор × (1 + НДС)
```

Экстраполяция (МУ №620 Прил.1): `a + b × (0.4 × X_гран + 0.6 × X_задан)`

### Admin panel

Кастомная `/admin` секция в Next.js. Не Payload CMS, не react-admin.

Функции:
- Пользователи: toggle can_calculate, роли
- Справочники: загрузить PDF → parse → скачать Excel → загрузить Excel → активировать/откатить
- Каждый справочник имеет `parse_prompt` (кастомизируется в admin)
- Индексы Минстроя: добавить вручную per квартал

### Claude API (entity extraction)

```python
# backend/app/services/entity_extractor.py
import anthropic

client = anthropic.Anthropic()  # читает ANTHROPIC_API_KEY из env

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    system=EXTRACTION_SYSTEM_PROMPT,  # с prompt caching
    messages=[{"role": "user", "content": combined_text}],
    tools=[extraction_tool_schema]    # tool_use для structured output
)
```

`ANTHROPIC_API_KEY` — в `.env`, не в коде.

### Roadmap (не реализуем сейчас)

- `chapter_coefficients` — раздело-специфичные коэф. (пример: ×1.2 к разделу КР за прогрессирующее обрушение)
- МРР (Москва) — добавить как отдельный справочник после MVP

## Лог

### 2026-05-08
- Составлен план, утверждена архитектура
- Начало реализации: Docker, DB schema, auth, frontend skeleton, entity extractor
